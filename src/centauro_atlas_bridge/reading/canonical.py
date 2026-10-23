"""Reconstruct only ledger-selected documents and verify the exact opened snapshot."""

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from bson import ObjectId

from centauro_atlas_bridge.application.connections import explicit_atlas_client
from centauro_atlas_bridge.application.models import Profile, Request
from centauro_atlas_bridge.ingestion.identity import (
    build_extraction_id,
    calculate_payload_hash,
)
from centauro_atlas_bridge.ingestion.integrity import verify_evidence


class ReadingError(ValueError):
    """Only a stable, locally authored diagnostic code; no raw content in errors."""

    def __init__(self, code="invalid_evidence"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: int | float
    high: int | float
    low: int | float
    close: int | float
    volume: int | float
    pages: tuple[int, ...]


@dataclass(frozen=True)
class Capture:
    page: int
    payload_hash: str
    document_ids: tuple[str, ...]
    captured_at: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalDataset:
    extraction_id: str
    request: Request
    destination_fingerprint: str
    bars: tuple[Bar, ...]
    captures: tuple[Capture, ...]
    exact_duplicates: int
    read_at: str
    snapshot_id: str
    provider: str = "massive"

    @property
    def bar_count(self):
        return len(self.bars)


def validate_selection(profile: Profile, job: dict) -> Request:
    """Run before creating a connection or issuing any database query."""
    try:
        request = Request(**job["request"])
        expected = build_extraction_id(**request.public())
        if job["profile"] != profile.public() or job["extraction_id"] != expected:
            raise ReadingError("selection_mismatch")
        return request
    except (KeyError, TypeError, ValueError):
        raise ReadingError("selection_mismatch") from None


def _bar(record: dict, page: int) -> Bar:
    try:
        if not isinstance(record, dict) or type(record.get("t")) is not int:
            raise ReadingError("invalid_bar")
        timestamp = datetime.fromtimestamp(record["t"] / 1000, tz=UTC)
        values = [record[key] for key in ("o", "h", "l", "c", "v")]
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in values
        ):
            raise ReadingError("invalid_bar")
        opened, high, low, close, volume = values
        if (
            volume < 0
            or low > min(opened, close)
            or high < max(opened, close)
            or high < low
        ):
            raise ReadingError("invalid_bar")
        return Bar(timestamp, opened, high, low, close, volume, (page,))
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        raise ReadingError("invalid_bar") from None


def reconstruct(
    profile: Profile, job: dict, run: dict | None, ledgers: list, documents: list
) -> CanonicalDataset:
    """Pure reconstruction. No writes, config imports, clients or shared caches."""
    request = validate_selection(profile, job)
    extraction_id = job["extraction_id"]
    expected_parameters = request.public() | {"sort": "asc", "limit": 50000}
    endpoint = f"/v2/aggs/ticker/{request.ticker}/range/1/day/{request.start_date}/{request.end_date}"
    try:
        if (
            not run
            or run.get("source") != "massive"
            or run.get("endpoint") != endpoint
            or run.get("parameters") != expected_parameters
        ):
            raise ReadingError("provenance_mismatch")
        if run.get("verification_status") == "invalid":
            raise ReadingError("invalid_evidence")
        ids = []
        for ledger in ledgers:
            page_ids = ledger.get("canonical_document_ids")
            if (
                type(ledger.get("page_number")) is not int
                or not isinstance(page_ids, list)
                or not page_ids
            ):
                raise ReadingError()
            if any(not isinstance(value, str) or not value for value in page_ids):
                raise ReadingError()
            ids.extend(page_ids)
        canonical_ids = set(ids)
        if len(ids) != len(canonical_ids):
            raise ReadingError()
        # Caller may supply alternate captures; never reconstruct or return them.
        selected = [
            document
            for document in documents
            if str(document.get("_id")) in canonical_ids
        ]
        if len(selected) != len(ids):
            raise ReadingError("missing_fragment")
        for document in selected:
            pagination = document.get("pagination", {})
            if (
                type(pagination.get("page_number")) is not int
                or type(pagination.get("chunk_number")) is not int
                or type(pagination.get("total_chunks")) is not int
            ):
                raise ReadingError()
            metadata = document.get("payload", {})
            if "ticker" in metadata and metadata["ticker"] != request.ticker:
                raise ReadingError("provenance_mismatch")
        selected.sort(
            key=lambda doc: (
                doc["pagination"]["page_number"],
                doc["pagination"]["chunk_number"],
            )
        )
        verification = verify_evidence(extraction_id, run, ledgers, selected)
        if verification["verified"] is not True:
            raise ReadingError("invalid_evidence")
        by_time = {}
        duplicates = 0
        for document in selected:
            page = document["pagination"]["page_number"]
            for record in document["payload"]["results"]:
                bar = _bar(record, page)
                previous = by_time.get(bar.timestamp)
                if previous is not None:
                    # Equality covers all OHLCV values; source pages are provenance.
                    if replace(previous, pages=bar.pages) != bar:
                        raise ReadingError("bar_conflict")
                    duplicates += 1
                    bar = replace(
                        bar, pages=tuple(sorted(set(previous.pages + bar.pages)))
                    )
                by_time[bar.timestamp] = bar
        captures = []
        for ledger in sorted(ledgers, key=lambda item: item["page_number"]):
            page_documents = [
                doc
                for doc in selected
                if doc["pagination"]["page_number"] == ledger["page_number"]
            ]
            times = tuple(
                sorted(
                    {
                        doc["extracted_at"].replace(tzinfo=UTC).isoformat()
                        if doc["extracted_at"].tzinfo is None
                        else doc["extracted_at"].astimezone(UTC).isoformat()
                        for doc in page_documents
                        if isinstance(doc.get("extracted_at"), datetime)
                    }
                )
            )
            captures.append(
                Capture(
                    ledger["page_number"],
                    ledger["canonical_payload_hash"],
                    tuple(ledger["canonical_document_ids"]),
                    times,
                )
            )
        return CanonicalDataset(
            extraction_id,
            request,
            profile.public()["destination_fingerprint"],
            tuple(by_time[key] for key in sorted(by_time)),
            tuple(captures),
            duplicates,
            datetime.now(UTC).isoformat(),
            calculate_payload_hash(
                [
                    {
                        "page": capture.page,
                        "hash": capture.payload_hash,
                        "ids": capture.document_ids,
                    }
                    for capture in captures
                ]
            ),
        )
    except ReadingError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        raise ReadingError("invalid_evidence") from None


def read_extraction(profile: Profile, job: dict) -> CanonicalDataset:
    validate_selection(profile, job)
    extraction_id = job["extraction_id"]
    try:
        with explicit_atlas_client(profile) as client:
            database = client[profile.database]
            run = database["ingestion_runs"].find_one({"extraction_id": extraction_id})
            ledgers = list(
                database["ingestion_page_ledger"]
                .find({"extraction_id": extraction_id})
                .sort("page_number", 1)
            )
            ids = [
                value
                for ledger in ledgers
                for value in ledger.get("canonical_document_ids", [])
            ]
            if any(not isinstance(value, str) for value in ids):
                raise ReadingError()
            # Original IDs are BSON ObjectIds serialized by the engine, or legacy string IDs.
            mongo_ids = [
                ObjectId(value) if ObjectId.is_valid(value) else value for value in ids
            ]
            documents = list(
                database["raw_ingestion"].find(
                    {
                        "_id": {"$in": mongo_ids},
                        "pagination.extraction_id": extraction_id,
                    }
                )
            )
            dataset = reconstruct(profile, job, run, ledgers, documents)
            latest_run = database["ingestion_runs"].find_one(
                {"extraction_id": extraction_id}
            )
            latest_ledgers = list(
                database["ingestion_page_ledger"]
                .find({"extraction_id": extraction_id})
                .sort("page_number", 1)
            )
            if run != latest_run or ledgers != latest_ledgers:
                raise ReadingError("evidence_changed")
            return dataset
    except ReadingError:
        raise
    except Exception:  # noqa: BLE001 -- connection/driver messages may include credentials
        raise ReadingError("read_failed") from None

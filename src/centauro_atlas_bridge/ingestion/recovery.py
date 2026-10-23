"""Recovery helpers for interrupted Centauro ingestions."""

from datetime import UTC, datetime
from typing import Any

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.page_ledger import (
    PAGE_LEDGER_COLLECTION,
    calculate_page_content_hash,
)
from centauro_atlas_bridge.ingestion.raw import (
    RAW_COLLECTION,
    calculate_ingestion_key,
    calculate_payload_hash,
)
from centauro_atlas_bridge.ingestion.runs import get_run

CHUNK_PAGINATION_FIELDS = {
    "chunk_number",
    "total_chunks",
    "storage_mode",
}


def _base_pagination(
    pagination: dict[str, Any],
) -> dict[str, Any]:
    """Return pagination without chunk-storage fields."""
    return {
        key: value
        for key, value in pagination.items()
        if key not in CHUNK_PAGINATION_FIELDS
    }


def _reconstruct_capture(
    documents: list[dict[str, Any]],
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
    extraction_id: str,
    page_number: int,
    original_payload_hash: str,
) -> dict[str, Any] | None:
    """Reconstruct and validate one interrupted raw capture."""
    if not documents:
        return None

    chunks_by_number: dict[int, dict[str, Any]] = {}
    total_chunks_values: set[int] = set()
    first_metadata: dict[str, Any] | None = None
    first_base_pagination: dict[str, Any] | None = None

    for document in documents:
        if (
            document.get("source") != source
            or document.get("endpoint") != endpoint
            or document.get("parameters") != parameters
            or document.get("original_payload_hash")
            != original_payload_hash
        ):
            return None

        pagination = document.get("pagination")

        if not isinstance(pagination, dict):
            return None

        if (
            pagination.get("extraction_id") != extraction_id
            or pagination.get("page_number") != page_number
        ):
            return None

        chunk_number = pagination.get("chunk_number")
        total_chunks = pagination.get("total_chunks")

        if (
            not isinstance(chunk_number, int)
            or isinstance(chunk_number, bool)
            or chunk_number < 1
            or not isinstance(total_chunks, int)
            or isinstance(total_chunks, bool)
            or total_chunks < 1
            or chunk_number in chunks_by_number
        ):
            return None

        payload = document.get("payload")

        if not isinstance(payload, dict):
            return None

        results = payload.get("results")

        if not isinstance(results, list):
            return None

        if document.get("payload_hash") != calculate_payload_hash(
            payload
        ):
            return None

        base_pagination = _base_pagination(
            pagination
        )

        expected_ingestion_key = calculate_ingestion_key(
            source=source,
            endpoint=endpoint,
            parameters=parameters,
            payload_hash=original_payload_hash,
            pagination=base_pagination,
            fragment=f"chunk:{chunk_number}",
        )

        if (
            document.get("ingestion_key")
            != expected_ingestion_key
        ):
            return None

        metadata = {
            key: value
            for key, value in payload.items()
            if key != "results"
        }

        if first_metadata is None:
            first_metadata = metadata

        elif metadata != first_metadata:
            return None

        if first_base_pagination is None:
            first_base_pagination = (
                base_pagination
            )

        elif (
            base_pagination
            != first_base_pagination
        ):
            return None

        total_chunks_values.add(
            total_chunks
        )

        chunks_by_number[
            chunk_number
        ] = payload

    if len(total_chunks_values) != 1:
        return None

    total_chunks = next(
        iter(total_chunks_values)
    )

    expected_chunk_numbers = set(
        range(
            1,
            total_chunks + 1,
        )
    )

    if (
        set(chunks_by_number)
        != expected_chunk_numbers
    ):
        return None

    reconstructed_results: list[Any] = []

    for chunk_number in range(
        1,
        total_chunks + 1,
    ):
        reconstructed_results.extend(
            chunks_by_number[
                chunk_number
            ]["results"]
        )

    reconstructed_payload = {
        **(first_metadata or {}),
        "results": reconstructed_results,
    }

    if (
        calculate_payload_hash(
            reconstructed_payload
        )
        != original_payload_hash
    ):
        return None

    return reconstructed_payload


def reconcile_equivalent_raw_captures(
    extraction_id: str,
) -> int:
    """Register equivalent interrupted captures as observed evidence."""
    run = get_run(
        extraction_id
    )

    if run is None:
        raise RuntimeError(
            "Cannot reconcile raw captures without a run"
        )

    if (
        run.get("extraction_id")
        != extraction_id
        or not isinstance(
            run.get("source"),
            str,
        )
        or not isinstance(
            run.get("endpoint"),
            str,
        )
        or not isinstance(
            run.get("parameters"),
            dict,
        )
    ):
        raise RuntimeError(
            "Cannot reconcile raw captures "
            "with incomplete run identity"
        )

    source = run["source"]
    endpoint = run["endpoint"]
    parameters = run["parameters"]

    client = create_atlas_client()

    try:
        database = client[
            get_database_name()
        ]

        ledger_collection = database[
            PAGE_LEDGER_COLLECTION
        ]

        raw_collection = database[
            RAW_COLLECTION
        ]

        ledgers = list(
            ledger_collection.find(
                {
                    "extraction_id":
                        extraction_id,
                }
            )
        )

        reconciled = 0

        for ledger in ledgers:
            page_number = ledger.get(
                "page_number"
            )

            if (
                not isinstance(
                    page_number,
                    int,
                )
                or isinstance(
                    page_number,
                    bool,
                )
                or page_number < 1
            ):
                continue

            if (
                ledger.get("source")
                != source
                or ledger.get("endpoint")
                != endpoint
            ):
                raise RuntimeError(
                    "Page ledger provenance "
                    "conflicts with run identity"
                )

            canonical_content_hash = (
                ledger.get(
                    "canonical_content_hash"
                )
            )

            observed_payload_hashes = (
                ledger.get(
                    "observed_payload_hashes",
                    [],
                )
            )

            if (
                not isinstance(
                    canonical_content_hash,
                    str,
                )
                or not isinstance(
                    observed_payload_hashes,
                    list,
                )
            ):
                continue

            observed_hashes = set(
                observed_payload_hashes
            )

            raw_documents = list(
                raw_collection.find(
                    {
                        "pagination.extraction_id":
                            extraction_id,
                        "pagination.page_number":
                            page_number,
                    }
                )
            )

            captures: dict[
                str,
                list[dict[str, Any]],
            ] = {}

            for document in raw_documents:
                original_payload_hash = (
                    document.get(
                        "original_payload_hash"
                    )
                )

                if not isinstance(
                    original_payload_hash,
                    str,
                ):
                    continue

                captures.setdefault(
                    original_payload_hash,
                    [],
                ).append(
                    document
                )

            for (
                original_payload_hash,
                capture_documents,
            ) in captures.items():
                if (
                    original_payload_hash
                    in observed_hashes
                ):
                    continue

                reconstructed_payload = (
                    _reconstruct_capture(
                        documents=(
                            capture_documents
                        ),
                        source=source,
                        endpoint=endpoint,
                        parameters=parameters,
                        extraction_id=(
                            extraction_id
                        ),
                        page_number=(
                            page_number
                        ),
                        original_payload_hash=(
                            original_payload_hash
                        ),
                    )
                )

                if (
                    reconstructed_payload
                    is None
                ):
                    continue

                content_hash = (
                    calculate_page_content_hash(
                        reconstructed_payload
                    )
                )

                if (
                    content_hash
                    != canonical_content_hash
                ):
                    continue

                result = (
                    ledger_collection.update_one(
                        {
                            "extraction_id":
                                extraction_id,
                            "page_number":
                                page_number,
                            "observed_payload_hashes": {
                                "$ne":
                                    original_payload_hash,
                            },
                        },
                        {
                            "$addToSet": {
                                "observed_payload_hashes":
                                    original_payload_hash,
                                "observed_content_hashes":
                                    content_hash,
                            },
                            "$inc": {
                                "capture_count":
                                    1,
                            },
                            "$set": {
                                "updated_at":
                                    datetime.now(
                                        UTC
                                    ),
                            },
                        },
                    )
                )

                if (
                    result.modified_count
                    == 1
                ):
                    reconciled += 1

                    observed_hashes.add(
                        original_payload_hash
                    )

        return reconciled

    finally:
        client.close()


def validate_resume_frontier(
    verification: dict[str, Any],
    last_page: int,
) -> str:
    """Validate whether checkpoint and verified pages can resume safely."""
    if (
        not isinstance(
            last_page,
            int,
        )
        or isinstance(
            last_page,
            bool,
        )
        or last_page < 1
    ):
        raise RuntimeError(
            "Checkpoint last_page is invalid"
        )

    errors = set(
        verification.get(
            "verification_errors",
            [],
        )
    )

    if errors != {
        "execution_not_completed"
    }:
        raise RuntimeError(
            "Incomplete extraction failed "
            "recovery verification"
        )

    ledger_pages = verification.get(
        "ledger_page_numbers"
    )

    canonical_pages = verification.get(
        "canonical_page_numbers"
    )

    if (
        not isinstance(
            ledger_pages,
            list,
        )
        or not isinstance(
            canonical_pages,
            list,
        )
    ):
        raise TypeError(
            "Recovery verification "
            "does not contain page evidence"
        )

    committed_pages = list(
        range(
            1,
            last_page + 1,
        )
    )

    if (
        ledger_pages
        == committed_pages
        and canonical_pages
        == committed_pages
    ):
        return "aligned"

    replay_pages = list(
        range(
            1,
            last_page + 2,
        )
    )

    if (
        ledger_pages
        == replay_pages
        and canonical_pages
        == replay_pages
    ):
        return "replay_required"

    raise RuntimeError(
        "Checkpoint and verified evidence disagree"
    )

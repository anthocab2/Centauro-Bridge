"""Tests for interrupted ingestion recovery."""

from copy import deepcopy

import pytest

from centauro_atlas_bridge.ingestion import recovery
from centauro_atlas_bridge.ingestion.raw import (
    calculate_ingestion_key,
    calculate_payload_hash,
)


class FakeUpdateResult:
    """Minimal MongoDB update result."""

    def __init__(
        self,
        modified_count: int,
    ):
        self.modified_count = (
            modified_count
        )


class FakeLedgerCollection:
    """In-memory ledger collection."""

    def __init__(
        self,
        ledgers,
    ):
        self.ledgers = ledgers

    def find(
        self,
        query,
    ):
        extraction_id = query.get(
            "extraction_id"
        )

        return [
            ledger
            for ledger in self.ledgers
            if ledger.get(
                "extraction_id"
            )
            == extraction_id
        ]

    def update_one(
        self,
        query,
        update,
    ):
        for ledger in self.ledgers:
            if (
                ledger.get(
                    "extraction_id"
                )
                != query.get(
                    "extraction_id"
                )
                or ledger.get(
                    "page_number"
                )
                != query.get(
                    "page_number"
                )
            ):
                continue

            payload_hash = query[
                "observed_payload_hashes"
            ]["$ne"]

            observed_payload_hashes = (
                ledger.setdefault(
                    "observed_payload_hashes",
                    [],
                )
            )

            if (
                payload_hash
                in observed_payload_hashes
            ):
                return FakeUpdateResult(
                    0
                )

            observed_payload_hashes.append(
                payload_hash
            )

            content_hash = update[
                "$addToSet"
            ][
                "observed_content_hashes"
            ]

            observed_content_hashes = (
                ledger.setdefault(
                    "observed_content_hashes",
                    [],
                )
            )

            if (
                content_hash
                not in observed_content_hashes
            ):
                observed_content_hashes.append(
                    content_hash
                )

            ledger["capture_count"] = (
                ledger.get(
                    "capture_count",
                    0,
                )
                + update[
                    "$inc"
                ][
                    "capture_count"
                ]
            )

            return FakeUpdateResult(
                1
            )

        return FakeUpdateResult(
            0
        )


class FakeRawCollection:
    """In-memory raw collection."""

    def __init__(
        self,
        documents,
    ):
        self.documents = documents

    def find(
        self,
        query,
    ):
        extraction_id = query.get(
            "pagination.extraction_id"
        )

        page_number = query.get(
            "pagination.page_number"
        )

        return [
            document
            for document in self.documents
            if document.get(
                "pagination",
                {},
            ).get(
                "extraction_id"
            )
            == extraction_id
            and document.get(
                "pagination",
                {},
            ).get(
                "page_number"
            )
            == page_number
        ]


class FakeDatabase:
    """Minimal database wrapper."""

    def __init__(
        self,
        collections,
    ):
        self.collections = (
            collections
        )

    def __getitem__(
        self,
        name,
    ):
        return self.collections[
            name
        ]


class FakeClient:
    """Minimal MongoDB client."""

    def __init__(
        self,
        database,
    ):
        self.database = database

    def __getitem__(
        self,
        name,
    ):
        return self.database

    def close(
        self,
    ):
        return None


def build_raw_capture(
    extraction_id,
    page_number,
    request_id,
    result_groups,
):
    """Build one realistic chunked raw capture."""
    source = "massive"

    endpoint = (
        "/v3/reference/tickers"
    )

    parameters = {
        "market": "stocks",
    }

    full_results = [
        result
        for group in result_groups
        for result in group
    ]

    full_payload = {
        "status": "OK",
        "request_id":
            request_id,
        "results": deepcopy(
            full_results
        ),
    }

    original_payload_hash = (
        calculate_payload_hash(
            full_payload
        )
    )

    documents = []

    total_chunks = len(
        result_groups
    )

    for (
        chunk_number,
        results,
    ) in enumerate(
        result_groups,
        start=1,
    ):
        payload = {
            "status": "OK",
            "request_id":
                request_id,
            "results": deepcopy(
                results
            ),
        }

        base_pagination = {
            "extraction_id":
                extraction_id,
            "page_number":
                page_number,
        }

        pagination = {
            **base_pagination,
            "chunk_number":
                chunk_number,
            "total_chunks":
                total_chunks,
            "storage_mode": (
                "chunked"
                if total_chunks > 1
                else "single"
            ),
        }

        documents.append(
            {
                "source":
                    source,
                "endpoint":
                    endpoint,
                "parameters":
                    parameters,
                "payload":
                    payload,
                "payload_hash":
                    calculate_payload_hash(
                        payload
                    ),
                "original_payload_hash":
                    original_payload_hash,
                "ingestion_key":
                    calculate_ingestion_key(
                        source=source,
                        endpoint=endpoint,
                        parameters=(
                            parameters
                        ),
                        payload_hash=(
                            original_payload_hash
                        ),
                        pagination=(
                            base_pagination
                        ),
                        fragment=(
                            f"chunk:{chunk_number}"
                        ),
                    ),
                "pagination":
                    pagination,
            }
        )

    return (
        original_payload_hash,
        full_payload,
        documents,
    )


def install_environment(
    monkeypatch,
    ledger,
    raw_documents,
):
    """Install fake Atlas state."""
    ledger_collection = (
        FakeLedgerCollection(
            [
                ledger
            ]
        )
    )

    raw_collection = (
        FakeRawCollection(
            raw_documents
        )
    )

    database = FakeDatabase(
        {
            recovery.PAGE_LEDGER_COLLECTION:
                ledger_collection,
            recovery.RAW_COLLECTION:
                raw_collection,
        }
    )

    client = FakeClient(
        database
    )

    monkeypatch.setattr(
        recovery,
        "create_atlas_client",
        lambda: client,
    )

    monkeypatch.setattr(
        recovery,
        "get_database_name",
        lambda: "centauro_test",
    )

    monkeypatch.setattr(
        recovery,
        "get_run",
        lambda extraction_id: {
            "extraction_id":
                extraction_id,
            "source":
                "massive",
            "endpoint":
                "/v3/reference/tickers",
            "parameters": {
                "market": "stocks",
            },
            "status":
                "started",
        },
    )

    return ledger


def test_equivalent_orphan_capture_is_reconciled(
    monkeypatch,
):
    """Equivalent interrupted capture becomes observed evidence."""
    extraction_id = (
        "recovery-test"
    )

    page_number = 2

    results = [
        {
            "ticker": "AVMV",
        },
        {
            "ticker": "CAST",
        },
    ]

    (
        canonical_hash,
        canonical_payload,
        _,
    ) = build_raw_capture(
        extraction_id=(
            extraction_id
        ),
        page_number=(
            page_number
        ),
        request_id=(
            "canonical-request"
        ),
        result_groups=[
            results
        ],
    )

    (
        orphan_hash,
        _,
        orphan_documents,
    ) = build_raw_capture(
        extraction_id=(
            extraction_id
        ),
        page_number=(
            page_number
        ),
        request_id=(
            "orphan-request"
        ),
        result_groups=[
            results
        ],
    )

    canonical_content_hash = (
        recovery
        .calculate_page_content_hash(
            canonical_payload
        )
    )

    ledger = {
        "extraction_id":
            extraction_id,
        "page_number":
            page_number,
        "source":
            "massive",
        "endpoint":
            "/v3/reference/tickers",
        "canonical_content_hash":
            canonical_content_hash,
        "observed_payload_hashes": [
            canonical_hash,
        ],
        "observed_content_hashes": [
            canonical_content_hash,
        ],
        "capture_count":
            1,
    }

    install_environment(
        monkeypatch,
        ledger,
        orphan_documents,
    )

    reconciled = (
        recovery
        .reconcile_equivalent_raw_captures(
            extraction_id
        )
    )

    assert reconciled == 1

    assert (
        orphan_hash
        in ledger[
            "observed_payload_hashes"
        ]
    )

    assert (
        ledger[
            "capture_count"
        ]
        == 2
    )


def test_conflicting_orphan_capture_is_not_reconciled(
    monkeypatch,
):
    """Different logical page content remains blocked."""
    extraction_id = (
        "recovery-test"
    )

    page_number = 2

    (
        canonical_hash,
        canonical_payload,
        _,
    ) = build_raw_capture(
        extraction_id=(
            extraction_id
        ),
        page_number=(
            page_number
        ),
        request_id=(
            "canonical-request"
        ),
        result_groups=[
            [
                {
                    "ticker": "AVMV",
                },
                {
                    "ticker": "CAST",
                },
            ]
        ],
    )

    (
        conflict_hash,
        _,
        conflict_documents,
    ) = build_raw_capture(
        extraction_id=(
            extraction_id
        ),
        page_number=(
            page_number
        ),
        request_id=(
            "conflict-request"
        ),
        result_groups=[
            [
                {
                    "ticker": "WRONG",
                }
            ]
        ],
    )

    canonical_content_hash = (
        recovery
        .calculate_page_content_hash(
            canonical_payload
        )
    )

    ledger = {
        "extraction_id":
            extraction_id,
        "page_number":
            page_number,
        "source":
            "massive",
        "endpoint":
            "/v3/reference/tickers",
        "canonical_content_hash":
            canonical_content_hash,
        "observed_payload_hashes": [
            canonical_hash,
        ],
        "observed_content_hashes": [
            canonical_content_hash,
        ],
        "capture_count":
            1,
    }

    install_environment(
        monkeypatch,
        ledger,
        conflict_documents,
    )

    reconciled = (
        recovery
        .reconcile_equivalent_raw_captures(
            extraction_id
        )
    )

    assert reconciled == 0

    assert (
        conflict_hash
        not in ledger[
            "observed_payload_hashes"
        ]
    )

    assert (
        ledger[
            "capture_count"
        ]
        == 1
    )


def test_equivalent_chunked_capture_is_reconciled(
    monkeypatch,
):
    """Equivalent multi-chunk capture is reconstructed safely."""
    extraction_id = (
        "recovery-test"
    )

    page_number = 2

    first_group = [
        {
            "ticker": "AVMV",
        }
    ]

    second_group = [
        {
            "ticker": "CAST",
        }
    ]

    (
        canonical_hash,
        canonical_payload,
        _,
    ) = build_raw_capture(
        extraction_id=(
            extraction_id
        ),
        page_number=(
            page_number
        ),
        request_id=(
            "canonical-request"
        ),
        result_groups=[
            first_group,
            second_group,
        ],
    )

    (
        orphan_hash,
        _,
        orphan_documents,
    ) = build_raw_capture(
        extraction_id=(
            extraction_id
        ),
        page_number=(
            page_number
        ),
        request_id=(
            "orphan-request"
        ),
        result_groups=[
            first_group,
            second_group,
        ],
    )

    canonical_content_hash = (
        recovery
        .calculate_page_content_hash(
            canonical_payload
        )
    )

    ledger = {
        "extraction_id":
            extraction_id,
        "page_number":
            page_number,
        "source":
            "massive",
        "endpoint":
            "/v3/reference/tickers",
        "canonical_content_hash":
            canonical_content_hash,
        "observed_payload_hashes": [
            canonical_hash,
        ],
        "observed_content_hashes": [
            canonical_content_hash,
        ],
        "capture_count":
            1,
    }

    install_environment(
        monkeypatch,
        ledger,
        orphan_documents,
    )

    reconciled = (
        recovery
        .reconcile_equivalent_raw_captures(
            extraction_id
        )
    )

    assert reconciled == 1

    assert (
        orphan_hash
        in ledger[
            "observed_payload_hashes"
        ]
    )


def build_verification(
    pages,
    errors=None,
):
    """Build resume verification evidence."""
    return {
        "verification_errors": (
            errors
            if errors is not None
            else [
                "execution_not_completed"
            ]
        ),
        "ledger_page_numbers":
            list(pages),
        "canonical_page_numbers":
            list(pages),
    }


def test_aligned_resume_frontier_is_accepted():
    """Checkpoint and evidence may be exactly aligned."""
    result = (
        recovery
        .validate_resume_frontier(
            verification=(
                build_verification(
                    [1, 2, 3]
                )
            ),
            last_page=3,
        )
    )

    assert result == "aligned"


def test_one_page_ahead_requires_replay():
    """One committed page ahead is recoverable by replay."""
    result = (
        recovery
        .validate_resume_frontier(
            verification=(
                build_verification(
                    [1, 2, 3, 4]
                )
            ),
            last_page=3,
        )
    )

    assert (
        result
        == "replay_required"
    )


def test_checkpoint_ahead_is_rejected():
    """Checkpoint must never be ahead of verified evidence."""
    with pytest.raises(
        RuntimeError,
        match=(
            "Checkpoint and "
            "verified evidence disagree"
        ),
    ):
        recovery.validate_resume_frontier(
            verification=(
                build_verification(
                    [1, 2]
                )
            ),
            last_page=3,
        )


def test_multiple_pages_ahead_are_rejected():
    """More than one evidence page ahead is unsafe."""
    with pytest.raises(
        RuntimeError,
        match=(
            "Checkpoint and "
            "verified evidence disagree"
        ),
    ):
        recovery.validate_resume_frontier(
            verification=(
                build_verification(
                    [1, 2, 3, 4, 5]
                )
            ),
            last_page=3,
        )


def test_integrity_error_blocks_resume():
    """Resume is blocked when evidence has another integrity error."""
    with pytest.raises(
        RuntimeError,
        match=(
            "Incomplete extraction failed "
            "recovery verification"
        ),
    ):
        recovery.validate_resume_frontier(
            verification=(
                build_verification(
                    [1, 2, 3],
                    errors=[
                        "execution_not_completed",
                        "page_2_content_conflict",
                    ],
                )
            ),
            last_page=3,
        )

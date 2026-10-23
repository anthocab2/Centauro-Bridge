"""Unit tests for ingestion integrity verification."""

from copy import deepcopy

from centauro_atlas_bridge.ingestion import verification
from centauro_atlas_bridge.ingestion.page_ledger import (
    PAGE_LEDGER_COLLECTION,
)
from centauro_atlas_bridge.ingestion.raw import (
    RAW_COLLECTION,
    build_raw_document,
    calculate_ingestion_key,
    calculate_payload_hash,
)

SOURCE = "massive"
ENDPOINT = "/test"
PARAMETERS = {
    "ticker": "AAPL",
}


class FakeCursor:
    """Small MongoDB cursor replacement."""

    def __init__(
        self,
        documents,
    ):
        self.documents = documents

    def sort(
        self,
        fields,
    ):
        return self

    def __iter__(
        self,
    ):
        return iter(
            self.documents
        )


class FakeCollection:
    """Small MongoDB collection replacement."""

    def __init__(
        self,
        documents,
    ):
        self.documents = documents

    def find(
        self,
        query,
        projection=None,
    ):
        return FakeCursor(
            self.documents
        )


class FakeDatabase:
    """Fake database exposing separate raw and ledger collections."""

    def __init__(
        self,
        raw_documents,
        ledger_documents,
    ):
        self.raw_documents = raw_documents
        self.ledger_documents = ledger_documents

    def __getitem__(
        self,
        name,
    ):
        if name == RAW_COLLECTION:
            return FakeCollection(
                self.raw_documents
            )

        if name == PAGE_LEDGER_COLLECTION:
            return FakeCollection(
                self.ledger_documents
            )

        raise KeyError(
            f"Unexpected collection: {name}"
        )


class FakeClient:
    """Small MongoDB client replacement."""

    def __init__(
        self,
        raw_documents,
        ledger_documents,
    ):
        self.raw_documents = raw_documents
        self.ledger_documents = ledger_documents

    def __getitem__(
        self,
        name,
    ):
        return FakeDatabase(
            raw_documents=self.raw_documents,
            ledger_documents=self.ledger_documents,
        )

    def close(
        self,
    ):
        pass


def build_page_fixture(
    extraction_id: str,
    page_number: int,
    chunk_results: list[list],
) -> tuple[
    list[dict],
    dict,
]:
    """Build valid raw chunks and their canonical ledger entry."""
    all_results = [
        result
        for chunk in chunk_results
        for result in chunk
    ]

    original_payload = {
        "status": "OK",
        "resultsCount": len(
            all_results
        ),
        "results": all_results,
    }

    original_payload_hash = (
        calculate_payload_hash(
            original_payload
        )
    )

    content_hash = (
        calculate_payload_hash(
            all_results
        )
    )

    base_pagination = {
        "extraction_id":
            extraction_id,
        "page_number":
            page_number,
    }

    raw_documents = []
    canonical_document_ids = []

    total_chunks = len(
        chunk_results
    )

    for (
        chunk_number,
        results,
    ) in enumerate(
        chunk_results,
        start=1,
    ):
        chunk_payload = {
            "status": "OK",
            "resultsCount": len(
                all_results
            ),
            "results": results,
        }

        chunk_pagination = {
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

        document = (
            build_raw_document(
                source=SOURCE,
                endpoint=ENDPOINT,
                parameters=PARAMETERS,
                payload=chunk_payload,
                pagination=(
                    chunk_pagination
                ),
            )
        )

        document[
            "original_payload_hash"
        ] = original_payload_hash

        document[
            "ingestion_key"
        ] = calculate_ingestion_key(
            source=SOURCE,
            endpoint=ENDPOINT,
            parameters=PARAMETERS,
            payload_hash=(
                original_payload_hash
            ),
            pagination=base_pagination,
            fragment=(
                f"chunk:{chunk_number}"
            ),
        )

        document_id = (
            f"raw_{page_number}_{chunk_number}"
        )

        document["_id"] = document_id

        canonical_document_ids.append(
            document_id
        )

        raw_documents.append(
            document
        )

    ledger = {
        "extraction_id":
            extraction_id,
        "page_number":
            page_number,
        "source":
            SOURCE,
        "endpoint":
            ENDPOINT,
        "canonical_payload_hash":
            original_payload_hash,
        "canonical_content_hash":
            content_hash,
        "canonical_document_ids":
            canonical_document_ids,
        "canonical_chunk_count":
            total_chunks,
        "canonical_record_count":
            len(
                all_results
            ),
        "capture_count":
            1,
        "observed_payload_hashes": [
            original_payload_hash,
        ],
        "observed_content_hashes": [
            content_hash,
        ],
    }

    return (
        raw_documents,
        ledger,
    )


def build_run(
    extraction_id: str,
    status: str = "completed",
    pages_stored: int = 1,
) -> dict:
    """Build a realistic persisted ingestion run."""
    return {
        "extraction_id":
            extraction_id,
        "source":
            SOURCE,
        "endpoint":
            ENDPOINT,
        "parameters":
            deepcopy(
                PARAMETERS
            ),
        "status":
            status,
        "pages_stored":
            pages_stored,
    }


def install_fake_environment(
    monkeypatch,
    raw_documents,
    ledger_documents,
    run,
):
    """Install fake Atlas collections and run state."""
    captured = {}

    monkeypatch.setattr(
        verification,
        "create_atlas_client",
        lambda: FakeClient(
            raw_documents=raw_documents,
            ledger_documents=ledger_documents,
        ),
    )

    monkeypatch.setattr(
        verification,
        "get_database_name",
        lambda: "test_database",
    )

    monkeypatch.setattr(
        verification,
        "get_run",
        lambda extraction_id: run,
    )

    def fake_set_verification_result(
        extraction_id,
        verified,
        errors,
    ):
        captured[
            "extraction_id"
        ] = extraction_id

        captured[
            "verified"
        ] = verified

        captured[
            "errors"
        ] = errors

        return {
            "verification_status": (
                "verified"
                if verified
                else "invalid"
            )
        }

    monkeypatch.setattr(
        verification,
        "set_verification_result",
        fake_set_verification_result,
    )

    return captured


def test_valid_extraction_is_verified(
    monkeypatch,
):
    """A complete intact canonical extraction must verify."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1, 2, 3],
            [4, 5],
        ],
    )

    captured = (
        install_fake_environment(
            monkeypatch,
            raw_documents=raw_documents,
            ledger_documents=[
                ledger
            ],
            run=build_run(
                extraction_id
            ),
        )
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result[
            "execution_completed"
        ]
        is True
    )

    assert (
        result["verified"]
        is True
    )

    assert (
        result[
            "verification_status"
        ]
        == "verified"
    )

    assert (
        result[
            "verification_errors"
        ]
        == []
    )

    assert (
        result[
            "total_results"
        ]
        == 5
    )

    assert (
        result[
            "observed_pages"
        ]
        == 1
    )

    assert (
        result[
            "canonical_raw_documents"
        ]
        == 2
    )

    assert (
        result[
            "noncanonical_raw_documents"
        ]
        == 0
    )

    assert (
        captured[
            "verified"
        ]
        is True
    )


def test_completed_run_without_raw_data_is_invalid(
    monkeypatch,
):
    """Completed execution without its canonical data must fail."""
    extraction_id = (
        "test_extraction"
    )

    (
        _,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1],
        ],
    )

    captured = (
        install_fake_environment(
            monkeypatch,
            raw_documents=[],
            ledger_documents=[
                ledger
            ],
            run=build_run(
                extraction_id
            ),
        )
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result[
            "execution_completed"
        ]
        is True
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "no_raw_documents"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "canonical_page_set_mismatch"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_missing"
        in result[
            "verification_errors"
        ]
    )

    assert (
        captured[
            "verified"
        ]
        is False
    )


def test_tampered_payload_is_detected(
    monkeypatch,
):
    """Changing stored data without updating hashes must be detected."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [
                {
                    "close": 100,
                }
            ]
        ],
    )

    raw_documents[0][
        "payload"
    ][
        "results"
    ][0][
        "close"
    ] = 999

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert any(
        "payload_hash_mismatch"
        in error
        for error
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_reconstructed_hash_mismatch"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_content_hash_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_missing_chunk_is_detected(
    monkeypatch,
):
    """A canonical page missing one expected chunk must be invalid."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1, 2],
            [3, 4],
        ],
    )

    raw_documents = (
        raw_documents[:1]
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "page_1_missing_or_extra_chunks"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_ledger_chunk_count_mismatch"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_canonical_document_set_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_duplicate_logical_chunk_position_is_detected(
    monkeypatch,
):
    """Two canonical documents in the same chunk position are invalid."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1, 2],
        ],
    )

    duplicate = deepcopy(
        raw_documents[0]
    )

    duplicate["_id"] = (
        "duplicate_document"
    )

    duplicate[
        "ingestion_key"
    ] = (
        "different_capture_key"
    )

    raw_documents.append(
        duplicate
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "page_1_duplicate_chunk_position"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_chunk_count_mismatch"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_canonical_document_set_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_noncanonical_retry_capture_is_not_double_counted(
    monkeypatch,
):
    """Metadata-only retry RAW evidence must not count twice."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [
                {
                    "close": 100,
                }
            ]
        ],
    )

    alternative = deepcopy(
        raw_documents[0]
    )

    alternative["_id"] = (
        "retry_capture"
    )

    alternative[
        "payload"
    ][
        "request_id"
    ] = "request_B"

    alternative[
        "payload_hash"
    ] = calculate_payload_hash(
        alternative[
            "payload"
        ]
    )

    alternative_payload = {
        "status": "OK",
        "resultsCount": 1,
        "results": [
            {
                "close": 100,
            }
        ],
        "request_id":
            "request_B",
    }

    alternative_original_hash = (
        calculate_payload_hash(
            alternative_payload
        )
    )

    alternative[
        "original_payload_hash"
    ] = alternative_original_hash

    alternative[
        "ingestion_key"
    ] = calculate_ingestion_key(
        source=SOURCE,
        endpoint=ENDPOINT,
        parameters=PARAMETERS,
        payload_hash=(
            alternative_original_hash
        ),
        pagination={
            "extraction_id":
                extraction_id,
            "page_number":
                1,
        },
        fragment="chunk:1",
    )

    raw_documents.append(
        alternative
    )

    ledger[
        "capture_count"
    ] = 2

    ledger[
        "observed_payload_hashes"
    ].append(
        alternative_original_hash
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is True
    )

    assert (
        result[
            "total_results"
        ]
        == 1
    )

    assert (
        result[
            "canonical_raw_documents"
        ]
        == 1
    )

    assert (
        result[
            "noncanonical_raw_documents"
        ]
        == 1
    )

    assert (
        result[
            "alternate_payload_variants"
        ]
        == 1
    )


def test_content_conflict_is_invalid(
    monkeypatch,
):
    """Two different logical contents for one page must invalidate it."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1],
        ],
    )

    conflicting_hash = (
        calculate_payload_hash(
            [999]
        )
    )

    ledger[
        "observed_content_hashes"
    ].append(
        conflicting_hash
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "page_1_content_conflict"
        in result[
            "verification_errors"
        ]
    )


def test_missing_page_ledger_is_invalid(
    monkeypatch,
):
    """Raw evidence without a canonical ledger must not verify."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        _,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1],
        ],
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[],
        run=build_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "no_page_ledger"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_raw_without_ledger"
        in result[
            "verification_errors"
        ]
    )


def test_incomplete_execution_cannot_be_verified(
    monkeypatch,
):
    """An unfinished execution cannot pass verification."""
    extraction_id = (
        "test_extraction"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1],
        ],
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_run(
            extraction_id=extraction_id,
            status="started",
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result[
            "execution_completed"
        ]
        is False
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "execution_not_completed"
        in result[
            "verification_errors"
        ]
    )

"""Unit tests for raw ingestion provenance and identity."""

from centauro_atlas_bridge.ingestion.raw import (
    build_raw_document,
    calculate_ingestion_key,
    calculate_payload_hash,
)


def test_payload_hash_is_deterministic():
    """Equivalent payloads must produce the same hash."""
    first = {
        "ticker": "AAPL",
        "value": 100,
    }

    second = {
        "value": 100,
        "ticker": "AAPL",
    }

    assert (
        calculate_payload_hash(first)
        == calculate_payload_hash(second)
    )


def test_changed_payload_produces_different_hash():
    """Changed raw data must produce a different hash."""
    first = {
        "value": 100,
    }

    second = {
        "value": 101,
    }

    assert (
        calculate_payload_hash(first)
        != calculate_payload_hash(second)
    )


def test_raw_document_preserves_provenance():
    """Raw documents must preserve transport provenance."""
    payload = {
        "results": [
            {
                "value": 100,
            }
        ]
    }

    parameters = {
        "ticker": "AAPL",
    }

    pagination = {
        "extraction_id": "extraction_123",
        "page_number": 1,
    }

    document = build_raw_document(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload=payload,
        pagination=pagination,
    )

    assert document["source"] == "massive"
    assert document["endpoint"] == "/test"
    assert document["parameters"] == parameters
    assert document["payload"] == payload
    assert document["pagination"] == pagination

    assert (
        document["payload_hash"]
        == calculate_payload_hash(payload)
    )

    assert document["ingestion_key"]
    assert document["extracted_at"]


def test_same_page_produces_same_ingestion_key():
    """Identical page identity must remain idempotent."""
    parameters = {
        "ticker": "AAPL",
    }

    pagination = {
        "extraction_id": "run_123",
        "page_number": 1,
    }

    first = calculate_ingestion_key(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload_hash="payload_hash",
        pagination=pagination,
        fragment="chunk:1",
    )

    second = calculate_ingestion_key(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload_hash="payload_hash",
        pagination=pagination,
        fragment="chunk:1",
    )

    assert first == second


def test_identical_payload_on_different_pages_has_different_identity():
    """Different source pages must never collapse into one document."""
    parameters = {
        "ticker": "AAPL",
    }

    first_page = calculate_ingestion_key(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload_hash="same_payload_hash",
        pagination={
            "extraction_id": "run_123",
            "page_number": 1,
        },
        fragment="chunk:1",
    )

    second_page = calculate_ingestion_key(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload_hash="same_payload_hash",
        pagination={
            "extraction_id": "run_123",
            "page_number": 2,
        },
        fragment="chunk:1",
    )

    assert first_page != second_page


def test_same_page_in_different_extractions_has_different_identity():
    """Separate extraction runs must remain independently traceable."""
    parameters = {
        "ticker": "AAPL",
    }

    first_run = calculate_ingestion_key(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload_hash="same_payload_hash",
        pagination={
            "extraction_id": "run_123",
            "page_number": 1,
        },
        fragment="chunk:1",
    )

    second_run = calculate_ingestion_key(
        source="massive",
        endpoint="/test",
        parameters=parameters,
        payload_hash="same_payload_hash",
        pagination={
            "extraction_id": "run_456",
            "page_number": 1,
        },
        fragment="chunk:1",
    )

    assert first_run != second_run

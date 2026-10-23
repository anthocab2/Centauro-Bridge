"""Unit tests for BSON-safe payload chunking."""

from centauro_atlas_bridge.ingestion.chunking import (
    chunk_payload,
    estimate_payload_size,
)


def test_small_payload_is_not_chunked():
    """Small payloads should remain intact."""
    payload = {
        "results": [
            {"value": 1},
            {"value": 2},
        ]
    }

    chunks = chunk_payload(
        payload,
        max_bytes=1000,
    )

    assert len(chunks) == 1
    assert chunks[0] == payload


def test_large_payload_is_split_without_losing_results():
    """Large payloads must preserve every original result."""
    results = [
        {
            "id": number,
            "data": "x" * 100,
        }
        for number in range(100)
    ]

    payload = {
        "status": "OK",
        "results": results,
    }

    chunks = chunk_payload(
        payload,
        max_bytes=1000,
    )

    assert len(chunks) > 1

    reconstructed_results = [
        result
        for chunk in chunks
        for result in chunk["results"]
    ]

    assert reconstructed_results == results

    for chunk in chunks:
        assert chunk["status"] == "OK"
        assert estimate_payload_size(chunk) <= 1000


def test_large_result_set_preserves_order_and_count():
    """Large result sets must survive chunking without loss."""
    results = [
        {
            "id": number,
            "data": "x" * 200,
        }
        for number in range(5000)
    ]

    payload = {
        "status": "OK",
        "results": results,
    }

    chunks = chunk_payload(
        payload,
        max_bytes=100_000,
    )

    reconstructed = [
        result
        for chunk in chunks
        for result in chunk["results"]
    ]

    assert len(chunks) > 1
    assert len(reconstructed) == 5000
    assert reconstructed == results

    for chunk in chunks:
        assert estimate_payload_size(chunk) <= 100_000

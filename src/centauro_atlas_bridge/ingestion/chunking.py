"""Safe payload chunking for MongoDB Atlas storage."""

from typing import Any

from bson import BSON

DEFAULT_MAX_PAYLOAD_BYTES = 8_000_000


def estimate_payload_size(payload: Any) -> int:
    """Estimate the BSON size of a JSON-compatible payload."""
    return len(BSON.encode({"payload": payload}))


def _split_results(
    metadata: dict[str, Any],
    results: list[Any],
    max_bytes: int,
) -> list[dict[str, Any]]:
    """Recursively split results until every chunk is BSON-safe."""
    candidate = {
        **metadata,
        "results": results,
    }

    if estimate_payload_size(candidate) <= max_bytes:
        return [candidate]

    if len(results) <= 1:
        raise ValueError(
            "A single result or payload metadata exceeds "
            "the safe payload size"
        )

    midpoint = len(results) // 2

    left = _split_results(
        metadata=metadata,
        results=results[:midpoint],
        max_bytes=max_bytes,
    )

    right = _split_results(
        metadata=metadata,
        results=results[midpoint:],
        max_bytes=max_bytes,
    )

    return left + right


def chunk_payload(
    payload: Any,
    max_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> list[Any]:
    """Split a large results payload into BSON-safe chunks."""
    if estimate_payload_size(payload) <= max_bytes:
        return [payload]

    if not isinstance(payload, dict):
        raise TypeError("Large payload is not chunkable")

    results = payload.get("results")

    if not isinstance(results, list):
        raise TypeError(
            "Large payload does not contain a chunkable results list"
        )

    if not results:
        raise ValueError(
            "Payload metadata exceeds the safe BSON size"
        )

    metadata = {
        key: value
        for key, value in payload.items()
        if key != "results"
    }

    return _split_results(
        metadata=metadata,
        results=results,
        max_bytes=max_bytes,
    )

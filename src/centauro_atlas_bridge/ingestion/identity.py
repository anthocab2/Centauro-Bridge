"""Pure identity/hash contracts. No environment, connection or persistence."""

import hashlib
import json
from typing import Any


def calculate_payload_hash(payload: Any) -> str:
    """Create a deterministic SHA-256 hash for a payload."""
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def calculate_ingestion_key(
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
    payload_hash: str,
    pagination: dict[str, Any] | None = None,
    fragment: str | None = None,
) -> str:
    """Create a deterministic identity for one raw ingestion payload."""
    identity = {
        "source": source,
        "endpoint": endpoint,
        "parameters": parameters,
        "payload_hash": payload_hash,
        "pagination": pagination,
        "fragment": fragment,
    }

    serialized = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def calculate_page_content_hash(
    payload: Any,
) -> str:
    """Hash only the source records that form one logical page."""
    if not isinstance(payload, dict):
        raise TypeError(
            "Page payload must be a dictionary"
        )

    results = payload.get("results")

    if not isinstance(results, list):
        raise TypeError(
            "Page payload must contain a results list"
        )

    return calculate_payload_hash(
        results
    )


def build_extraction_id(
    ticker: str,
    start_date: str,
    end_date: str,
    adjusted: bool,
) -> str:
    """Create a deterministic ID for one Massive extraction request."""
    identity = {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "adjusted": adjusted,
    }

    serialized = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()

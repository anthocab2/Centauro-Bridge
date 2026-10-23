"""Extraction pipeline from HTTP sources to MongoDB Atlas."""

from typing import Any

from centauro_atlas_bridge.ingestion.http_client import fetch_json
from centauro_atlas_bridge.ingestion.raw import store_raw_payload


def extract_and_store_json(
    url: str,
    source: str,
    endpoint: str,
    request_parameters: dict[str, Any] | None = None,
    provenance_parameters: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    pagination: dict[str, Any] | None = None,
) -> str:
    """Fetch JSON from a source and store the raw response in Atlas."""
    payload = fetch_json(
        url=url,
        parameters=request_parameters,
        headers=headers,
    )

    return store_raw_payload(
        source=source,
        endpoint=endpoint,
        parameters=provenance_parameters or {},
        payload=payload,
        pagination=pagination,
    )

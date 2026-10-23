"""Integrity verification for completed Centauro ingestions."""

from typing import Any

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.integrity import verify_evidence
from centauro_atlas_bridge.ingestion.page_ledger import (
    PAGE_LEDGER_COLLECTION,
)
from centauro_atlas_bridge.ingestion.raw import (
    RAW_COLLECTION,
)
from centauro_atlas_bridge.ingestion.runs import (
    get_run,
    set_verification_result,
)


def verify_extraction(extraction_id: str) -> dict[str, Any]:
    """Legacy Atlas wrapper: read evidence, verify with the pure core and persist status."""
    client = create_atlas_client()
    try:
        database = client[get_database_name()]
        raw_collection = database[RAW_COLLECTION]
        ledger_collection = database[PAGE_LEDGER_COLLECTION]
        run = get_run(extraction_id)
        ledger_cursor = (
            ledger_collection.find(
                {
                    "extraction_id":
                        extraction_id,
                }
            )
            .sort(
                [
                    (
                        "page_number",
                        1,
                    )
                ]
            )
        )

        raw_cursor = (
            raw_collection.find(
                {
                    "pagination.extraction_id":
                        extraction_id,
                },
                {
                    "_id": 1,
                    "ingestion_key": 1,
                    "source": 1,
                    "endpoint": 1,
                    "parameters": 1,
                    "payload_hash": 1,
                    "original_payload_hash": 1,
                    "pagination": 1,
                    "payload": 1,
                },
            )
            .sort(
                [
                    (
                        "pagination.page_number",
                        1,
                    ),
                    (
                        "pagination.chunk_number",
                        1,
                    ),
                ]
            )
        )

        result = verify_evidence(extraction_id, run, ledger_cursor, raw_cursor)
        if run is not None:
            set_verification_result(extraction_id=extraction_id, verified=result["verified"], errors=result["verification_errors"])
        return result
    finally:
        client.close()

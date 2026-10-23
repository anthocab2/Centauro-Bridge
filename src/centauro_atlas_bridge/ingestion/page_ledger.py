"""Canonical source-page ledger for Centauro ingestions."""

from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.identity import (
    calculate_page_content_hash,
)

PAGE_LEDGER_COLLECTION = "ingestion_page_ledger"

__all__ = ["PAGE_LEDGER_COLLECTION", "calculate_page_content_hash", "register_canonical_page"]


def register_canonical_page(
    source: str,
    endpoint: str,
    extraction_id: str,
    page_number: int,
    payload_hash: str,
    content_hash: str,
    document_ids: list[str],
    record_count: int,
) -> dict[str, Any]:
    """Register one raw capture against its logical source page."""
    if page_number < 1:
        raise ValueError(
            "page_number must be greater than zero"
        )

    if not document_ids:
        raise ValueError(
            "A canonical page must reference stored documents"
        )

    if record_count < 0:
        raise ValueError(
            "record_count cannot be negative"
        )

    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[PAGE_LEDGER_COLLECTION]

        collection.create_index(
            [
                ("extraction_id", 1),
                ("page_number", 1),
            ],
            unique=True,
        )

        now = datetime.now(UTC)

        identity = {
            "extraction_id": extraction_id,
            "page_number": page_number,
        }

        update = {
            "$setOnInsert": {
                "extraction_id": extraction_id,
                "page_number": page_number,
                "source": source,
                "endpoint": endpoint,
                "canonical_payload_hash": (
                    payload_hash
                ),
                "canonical_content_hash": (
                    content_hash
                ),
                "canonical_document_ids": (
                    list(document_ids)
                ),
                "canonical_chunk_count": len(
                    document_ids
                ),
                "canonical_record_count": (
                    record_count
                ),
                "created_at": now,
            },
            "$set": {
                "updated_at": now,
            },
            "$inc": {
                "capture_count": 1,
            },
            "$addToSet": {
                "observed_payload_hashes": (
                    payload_hash
                ),
                "observed_content_hashes": (
                    content_hash
                ),
            },
        }

        try:
            ledger = collection.find_one_and_update(
                identity,
                update,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )

        except DuplicateKeyError:
            ledger = collection.find_one_and_update(
                identity,
                {
                    "$set": update["$set"],
                    "$inc": update["$inc"],
                    "$addToSet": update[
                        "$addToSet"
                    ],
                },
                upsert=False,
                return_document=ReturnDocument.AFTER,
            )

        if ledger is None:
            raise RuntimeError(
                "Atlas did not return the page ledger"
            )

        if (
            ledger.get("source") != source
            or ledger.get("endpoint") != endpoint
        ):
            raise RuntimeError(
                "Page ledger provenance conflicts "
                "with the current extraction"
            )

        return ledger

    finally:
        client.close()

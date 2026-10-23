"""Extraction checkpoints for Centauro data ingestion."""

from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name

CHECKPOINTS_COLLECTION = "ingestion_checkpoints"


def save_checkpoint(
    source: str,
    endpoint: str,
    extraction_id: str,
    cursor: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or update the progress of one extraction."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[CHECKPOINTS_COLLECTION]

        collection.create_index(
            [
                ("source", 1),
                ("endpoint", 1),
                ("extraction_id", 1),
            ],
            unique=True,
        )

        checkpoint = collection.find_one_and_update(
            {
                "source": source,
                "endpoint": endpoint,
                "extraction_id": extraction_id,
            },
            {
                "$set": {
                    "cursor": cursor,
                    "metadata": metadata or {},
                    "updated_at": datetime.now(UTC),
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        return checkpoint

    finally:
        client.close()


def get_checkpoint(
    source: str,
    endpoint: str,
    extraction_id: str,
) -> dict[str, Any] | None:
    """Return the last saved progress for one extraction."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[CHECKPOINTS_COLLECTION]

        return collection.find_one(
            {
                "source": source,
                "endpoint": endpoint,
                "extraction_id": extraction_id,
            }
        )

    finally:
        client.close()

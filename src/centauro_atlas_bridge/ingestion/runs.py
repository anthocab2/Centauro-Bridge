"""Track ingestion run and verification state in MongoDB Atlas."""

from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name

INGESTION_RUNS_COLLECTION = "ingestion_runs"


def start_run(
    extraction_id: str,
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Create or resume an ingestion run."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[INGESTION_RUNS_COLLECTION]

        collection.create_index(
            "extraction_id",
            unique=True,
        )

        now = datetime.now(UTC)

        return collection.find_one_and_update(
            {
                "extraction_id": extraction_id,
            },
            {
                "$setOnInsert": {
                    "extraction_id": extraction_id,
                    "source": source,
                    "endpoint": endpoint,
                    "parameters": parameters,
                    "started_at": now,
                },
                "$set": {
                    "status": "started",
                    "updated_at": now,
                    "error": None,
                    "verification_status": "not_verified",
                    "verification_errors": [],
                    "verification_checked_at": None,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    finally:
        client.close()


def complete_run(
    extraction_id: str,
    pages_stored: int,
) -> dict[str, Any] | None:
    """Mark transport as completed but not yet integrity-verified."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[INGESTION_RUNS_COLLECTION]

        now = datetime.now(UTC)

        return collection.find_one_and_update(
            {
                "extraction_id": extraction_id,
            },
            {
                "$set": {
                    "status": "completed",
                    "pages_stored": pages_stored,
                    "completed_at": now,
                    "updated_at": now,
                    "error": None,
                    "verification_status": "not_verified",
                    "verification_errors": [],
                    "verification_checked_at": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    finally:
        client.close()


def fail_run(
    extraction_id: str,
    error: str,
) -> dict[str, Any] | None:
    """Mark an ingestion run as failed."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[INGESTION_RUNS_COLLECTION]

        return collection.find_one_and_update(
            {
                "extraction_id": extraction_id,
            },
            {
                "$set": {
                    "status": "failed",
                    "error": error,
                    "updated_at": datetime.now(UTC),
                    "verification_status": "not_verified",
                    "verification_errors": [],
                    "verification_checked_at": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    finally:
        client.close()


def set_verification_result(
    extraction_id: str,
    verified: bool,
    errors: list[str],
) -> dict[str, Any] | None:
    """Persist the integrity-verification result for one run."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[INGESTION_RUNS_COLLECTION]

        return collection.find_one_and_update(
            {
                "extraction_id": extraction_id,
            },
            {
                "$set": {
                    "verification_status": (
                        "verified"
                        if verified
                        else "invalid"
                    ),
                    "verification_errors": errors,
                    "verification_checked_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    finally:
        client.close()


def get_run(
    extraction_id: str,
) -> dict[str, Any] | None:
    """Retrieve an ingestion run."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]

        return database[
            INGESTION_RUNS_COLLECTION
        ].find_one(
            {
                "extraction_id": extraction_id,
            }
        )

    finally:
        client.close()

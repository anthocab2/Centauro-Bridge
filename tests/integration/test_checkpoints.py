"""Integration tests for ingestion checkpoints."""

from uuid import uuid4

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.checkpoints import (
    CHECKPOINTS_COLLECTION,
    get_checkpoint,
    save_checkpoint,
)


def test_checkpoint_can_be_saved_and_updated():
    """Verify that extraction progress survives in Atlas."""
    extraction_id = f"test_{uuid4()}"

    try:
        first = save_checkpoint(
            source="test_source",
            endpoint="/test",
            extraction_id=extraction_id,
            cursor="page_2",
        )

        assert first["cursor"] == "page_2"

        second = save_checkpoint(
            source="test_source",
            endpoint="/test",
            extraction_id=extraction_id,
            cursor="page_3",
        )

        assert second["cursor"] == "page_3"

        stored = get_checkpoint(
            source="test_source",
            endpoint="/test",
            extraction_id=extraction_id,
        )

        assert stored is not None
        assert stored["cursor"] == "page_3"

    finally:
        client = create_atlas_client()

        try:
            database = client[get_database_name()]
            database[CHECKPOINTS_COLLECTION].delete_one(
                {"extraction_id": extraction_id}
            )
        finally:
            client.close()

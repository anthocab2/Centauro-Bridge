"""Integration tests for Atlas read and write operations."""

from uuid import uuid4

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.atlas.store import find_document, insert_document
from centauro_atlas_bridge.config import get_database_name


def test_insert_and_find_document():
    """Verify that a document can be stored and retrieved from Atlas."""
    collection_name = "bridge_smoke_tests"
    test_id = str(uuid4())

    document = {
        "type": "bridge_smoke_test",
        "test_id": test_id,
        "message": "Centauro Atlas Bridge",
    }

    inserted_id = insert_document(collection_name, document)

    assert inserted_id

    stored_document = find_document(
        collection_name,
        {"test_id": test_id},
    )

    assert stored_document is not None
    assert stored_document["test_id"] == test_id
    assert stored_document["message"] == "Centauro Atlas Bridge"

    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        database[collection_name].delete_one({"test_id": test_id})
    finally:
        client.close()

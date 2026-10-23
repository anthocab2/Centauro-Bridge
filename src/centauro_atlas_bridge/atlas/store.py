"""Read and write operations for MongoDB Atlas."""

from typing import Any

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name


def insert_document(collection_name: str, document: dict[str, Any]) -> str:
    """Insert a document into an Atlas collection and return its ID."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[collection_name]

        result = collection.insert_one(document)

        return str(result.inserted_id)
    finally:
        client.close()


def find_document(
    collection_name: str,
    query: dict[str, Any],
) -> dict[str, Any] | None:
    """Find and return one document from an Atlas collection."""
    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[collection_name]

        return collection.find_one(query)
    finally:
        client.close()

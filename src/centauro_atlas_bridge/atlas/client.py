"""MongoDB Atlas client for Centauro."""

from pymongo import MongoClient
from pymongo.server_api import ServerApi

from centauro_atlas_bridge.config import get_mongodb_uri

SERVER_SELECTION_TIMEOUT_MS = 15000
CONNECT_TIMEOUT_MS = 10000


def create_atlas_client() -> MongoClient:
    """Create and return a configured MongoDB Atlas client."""
    uri = get_mongodb_uri()

    return MongoClient(
        uri,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=CONNECT_TIMEOUT_MS,
        retryReads=True,
        retryWrites=True,
        appname="centauro-atlas-bridge",
    )


def ping_atlas() -> bool:
    """Verify that MongoDB Atlas is reachable."""
    client = create_atlas_client()

    try:
        client.admin.command("ping")
        return True

    finally:
        client.close()

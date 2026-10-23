"""Integration tests for idempotent raw data ingestion."""

from uuid import uuid4

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.raw import (
    RAW_COLLECTION,
    build_raw_document,
    store_raw_payload,
)


def test_identical_raw_payload_is_not_duplicated():
    """Verify that repeating the same ingestion does not create duplicates."""
    request_id = str(uuid4())

    parameters = {
        "ticker": "TEST",
        "request_id": request_id,
    }

    payload = {
        "results": [
            {
                "close": 100.0,
                "volume": 1000,
            }
        ]
    }

    document = build_raw_document(
        source="test_source",
        endpoint="/test",
        parameters=parameters,
        payload=payload,
    )

    ingestion_key = document["ingestion_key"]

    try:
        first_id = store_raw_payload(
            source="test_source",
            endpoint="/test",
            parameters=parameters,
            payload=payload,
        )

        second_id = store_raw_payload(
            source="test_source",
            endpoint="/test",
            parameters=parameters,
            payload=payload,
        )

        assert first_id == second_id

        client = create_atlas_client()

        try:
            database = client[get_database_name()]

            count = database[RAW_COLLECTION].count_documents(
                {"ingestion_key": ingestion_key}
            )

            assert count == 1
        finally:
            client.close()

    finally:
        client = create_atlas_client()

        try:
            database = client[get_database_name()]
            database[RAW_COLLECTION].delete_one(
                {"ingestion_key": ingestion_key}
            )
        finally:
            client.close()

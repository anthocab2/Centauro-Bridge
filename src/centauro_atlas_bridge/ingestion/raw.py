"""Raw data ingestion with provenance and idempotency."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument, UpdateOne

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.chunking import chunk_payload

RAW_COLLECTION = "raw_ingestion"


def calculate_payload_hash(payload: Any) -> str:
    """Create a deterministic SHA-256 hash for a payload."""
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def calculate_ingestion_key(
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
    payload_hash: str,
    pagination: dict[str, Any] | None = None,
    fragment: str | None = None,
) -> str:
    """Create a deterministic identity for one raw ingestion payload."""
    identity = {
        "source": source,
        "endpoint": endpoint,
        "parameters": parameters,
        "payload_hash": payload_hash,
        "pagination": pagination,
        "fragment": fragment,
    }

    serialized = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def build_raw_document(
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
    payload: Any,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a traceable raw-ingestion document."""
    payload_hash = calculate_payload_hash(payload)

    ingestion_key = calculate_ingestion_key(
        source=source,
        endpoint=endpoint,
        parameters=parameters,
        payload_hash=payload_hash,
        pagination=pagination,
    )

    return {
        "ingestion_key": ingestion_key,
        "source": source,
        "endpoint": endpoint,
        "parameters": parameters,
        "extracted_at": datetime.now(UTC),
        "payload_hash": payload_hash,
        "pagination": pagination,
        "payload": payload,
    }


def store_raw_payload(
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
    payload: Any,
    pagination: dict[str, Any] | None = None,
) -> str:
    """Store one raw payload idempotently in MongoDB Atlas."""
    document = build_raw_document(
        source=source,
        endpoint=endpoint,
        parameters=parameters,
        payload=payload,
        pagination=pagination,
    )

    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[RAW_COLLECTION]

        collection.create_index(
            "ingestion_key",
            unique=True,
        )

        stored = collection.find_one_and_update(
            {
                "ingestion_key": document["ingestion_key"],
            },
            {
                "$setOnInsert": document,
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        if stored is None:
            raise RuntimeError(
                "Atlas did not return the stored raw document"
            )

        return str(stored["_id"])

    finally:
        client.close()


def store_raw_payload_chunks(
    source: str,
    endpoint: str,
    parameters: dict[str, Any],
    payload: Any,
    pagination: dict[str, Any] | None = None,
) -> list[str]:
    """Store BSON-safe chunks using efficient bulk upserts."""
    chunks = chunk_payload(payload)

    original_payload_hash = calculate_payload_hash(
        payload
    )

    documents = []

    for chunk_number, chunk in enumerate(
        chunks,
        start=1,
    ):
        chunk_pagination = {
            **(pagination or {}),
            "chunk_number": chunk_number,
            "total_chunks": len(chunks),
            "storage_mode": (
                "chunked"
                if len(chunks) > 1
                else "single"
            ),
        }

        document = build_raw_document(
            source=source,
            endpoint=endpoint,
            parameters=parameters,
            payload=chunk,
            pagination=chunk_pagination,
        )

        document["original_payload_hash"] = (
            original_payload_hash
        )

        document["ingestion_key"] = (
            calculate_ingestion_key(
                source=source,
                endpoint=endpoint,
                parameters=parameters,
                payload_hash=original_payload_hash,
                pagination=pagination,
                fragment=f"chunk:{chunk_number}",
            )
        )

        documents.append(document)

    ingestion_keys = [
        document["ingestion_key"]
        for document in documents
    ]

    client = create_atlas_client()

    try:
        database = client[get_database_name()]
        collection = database[RAW_COLLECTION]

        collection.create_index(
            "ingestion_key",
            unique=True,
        )

        collection.create_index(
            [
                ("pagination.extraction_id", 1),
                ("pagination.page_number", 1),
                ("pagination.chunk_number", 1),
            ]
        )

        existing_documents = list(
            collection.find(
                {
                    "ingestion_key": {
                        "$in": ingestion_keys,
                    }
                },
                {
                    "_id": 1,
                    "ingestion_key": 1,
                },
            )
        )

        existing_keys = {
            document["ingestion_key"]
            for document in existing_documents
        }

        missing_documents = [
            document
            for document in documents
            if document["ingestion_key"]
            not in existing_keys
        ]

        if missing_documents:
            operations = [
                UpdateOne(
                    {
                        "ingestion_key": document[
                            "ingestion_key"
                        ]
                    },
                    {
                        "$setOnInsert": document,
                    },
                    upsert=True,
                )
                for document in missing_documents
            ]

            collection.bulk_write(
                operations,
                ordered=False,
            )

        stored_documents = list(
            collection.find(
                {
                    "ingestion_key": {
                        "$in": ingestion_keys,
                    }
                },
                {
                    "_id": 1,
                    "ingestion_key": 1,
                },
            )
        )

        stored_by_key = {
            document["ingestion_key"]: str(
                document["_id"]
            )
            for document in stored_documents
        }

        missing_keys = [
            key
            for key in ingestion_keys
            if key not in stored_by_key
        ]

        if missing_keys:
            raise RuntimeError(
                "Atlas did not persist every raw chunk"
            )

        return [
            stored_by_key[key]
            for key in ingestion_keys
        ]

    finally:
        client.close()

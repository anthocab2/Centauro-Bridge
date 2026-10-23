"""Explicit synthetic evidence for a local UI walkthrough; never writes or extracts."""

from datetime import UTC, datetime, timedelta

from centauro_atlas_bridge.application.models import Profile, Request
from centauro_atlas_bridge.ingestion.identity import (
    build_extraction_id,
    calculate_ingestion_key,
    calculate_payload_hash,
)
from centauro_atlas_bridge.reading.canonical import reconstruct


def demo_evidence():
    profile = Profile(
        "ejemplo-local",
        "atlas-simulado",
        "ejemplo",
        "unused-demo",
        "mongodb://example.invalid",
    )
    request = Request("DEMO", "2026-10-01", "2026-10-14")
    extraction_id = build_extraction_id(**request.public())
    endpoint = "/v2/aggs/ticker/DEMO/range/1/day/2026-10-01/2026-10-14"
    parameters = request.public() | {"sort": "asc", "limit": 50000}
    start = datetime(2026, 10, 1, 13, 30, tzinfo=UTC)
    closes = [101.2, 102.6, 101.9, 104.3, 105.1, 104.6, 106.8, 108.1, 107.5, 109.4]
    days = [
        start + timedelta(days=i)
        for i in range(14)
        if (start + timedelta(days=i)).weekday() < 5
    ]
    rows = []
    for i, (day, close) in enumerate(zip(days, closes, strict=True)):
        opened = 100.4 if i == 0 else closes[i - 1]
        rows.append(
            {
                "t": int(day.timestamp() * 1000),
                "o": opened,
                "h": round(max(opened, close) + 1.2, 2),
                "l": round(min(opened, close) - 0.8, 2),
                "c": close,
                "v": 185000 + i * 17200,
            }
        )
    payload = {
        "status": "OK",
        "ticker": "DEMO",
        "resultsCount": len(rows),
        "results": rows,
    }
    original_hash = calculate_payload_hash(payload)
    base_pagination = {"extraction_id": extraction_id, "page_number": 1}
    documents = []
    for number, chunk in enumerate((rows[:5], rows[5:]), 1):
        part = payload | {"results": chunk}
        documents.append(
            {
                "_id": f"demo-chunk-{number}",
                "source": "massive",
                "endpoint": endpoint,
                "parameters": parameters,
                "payload": part,
                "payload_hash": calculate_payload_hash(part),
                "original_payload_hash": original_hash,
                "pagination": base_pagination
                | {
                    "chunk_number": number,
                    "total_chunks": 2,
                    "storage_mode": "chunked",
                },
                "ingestion_key": calculate_ingestion_key(
                    "massive",
                    endpoint,
                    parameters,
                    original_hash,
                    base_pagination,
                    f"chunk:{number}",
                ),
                "extracted_at": datetime(2026, 10, 15, 12, tzinfo=UTC),
            }
        )
    ledger = {
        "extraction_id": extraction_id,
        "page_number": 1,
        "source": "massive",
        "endpoint": endpoint,
        "canonical_payload_hash": original_hash,
        "canonical_content_hash": calculate_payload_hash(rows),
        "canonical_document_ids": [doc["_id"] for doc in documents],
        "canonical_chunk_count": 2,
        "canonical_record_count": len(rows),
        "observed_payload_hashes": [original_hash],
        "observed_content_hashes": [calculate_payload_hash(rows)],
    }
    run = {
        "extraction_id": extraction_id,
        "source": "massive",
        "endpoint": endpoint,
        "parameters": parameters,
        "status": "completed",
        "pages_stored": 1,
        "verification_status": "verified",
    }
    job = {
        "job_id": "ejemplo-local",
        "extraction_id": extraction_id,
        "profile": profile.public(),
        "request": request.public(),
    }
    return profile, job, run, [ledger], documents


def demo_dataset():
    return reconstruct(*demo_evidence())

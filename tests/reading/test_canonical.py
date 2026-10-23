import copy
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime

import mongomock
import pytest
from bson import ObjectId

from centauro_atlas_bridge.application.models import Profile, Request
from centauro_atlas_bridge.ingestion.identity import (
    build_extraction_id,
    calculate_ingestion_key,
    calculate_payload_hash,
)
from centauro_atlas_bridge.ingestion.raw import build_raw_document
from centauro_atlas_bridge.reading import canonical
from centauro_atlas_bridge.reading.canonical import (
    ReadingError,
    read_extraction,
    reconstruct,
)


def row(day=2, close=102):
    return {
        "t": int(datetime(2025, 1, day, 14, 30, tzinfo=UTC).timestamp() * 1000),
        "o": 100,
        "h": max(105, close),
        "l": 99,
        "c": close,
        "v": 1000,
    }


def evidence(pages=None):
    """Use legacy raw document builder and identity contracts as fixture oracle."""
    pages = [[[row(3)], [row(2)]]] if pages is None else pages
    profile = Profile(
        "mvp",
        "atlas-mvp",
        "mvp_test",
        "secret-api",
        "mongodb://user:secret-uri@localhost",
    )
    request = Request("AAPL", "2025-01-02", "2025-01-04")
    extraction_id = build_extraction_id(**request.public())
    parameters = request.public() | {"sort": "asc", "limit": 50000}
    endpoint = "/v2/aggs/ticker/AAPL/range/1/day/2025-01-02/2025-01-04"
    docs, ledgers = [], []
    for page, chunks in enumerate(pages, 1):
        results = [record for chunk in chunks for record in chunk]
        payload = {
            "status": "OK",
            "ticker": "AAPL",
            "resultsCount": len(results),
            "results": results,
        }
        payload_hash = calculate_payload_hash(payload)
        base = {"extraction_id": extraction_id, "page_number": page}
        page_docs = []
        for number, chunk in enumerate(chunks, 1):
            pagination = base | {
                "chunk_number": number,
                "total_chunks": len(chunks),
                "storage_mode": "chunked" if len(chunks) > 1 else "single",
            }
            document = build_raw_document(
                "massive",
                endpoint,
                parameters,
                payload | {"results": chunk},
                pagination,
            )
            document.update(
                _id=ObjectId(),
                original_payload_hash=payload_hash,
                ingestion_key=calculate_ingestion_key(
                    "massive",
                    endpoint,
                    parameters,
                    payload_hash,
                    base,
                    f"chunk:{number}",
                ),
            )
            page_docs.append(document)
        docs.extend(page_docs)
        ledgers.append(
            {
                "extraction_id": extraction_id,
                "source": "massive",
                "endpoint": endpoint,
                "page_number": page,
                "canonical_payload_hash": payload_hash,
                "canonical_content_hash": calculate_payload_hash(results),
                "canonical_document_ids": [str(doc["_id"]) for doc in page_docs],
                "canonical_chunk_count": len(chunks),
                "canonical_record_count": len(results),
                "observed_payload_hashes": [payload_hash],
                "observed_content_hashes": [calculate_payload_hash(results)],
            }
        )
    run = {
        "extraction_id": extraction_id,
        "source": "massive",
        "endpoint": endpoint,
        "parameters": parameters,
        "status": "completed",
        "pages_stored": len(pages),
        "verification_status": "verified",
    }
    job = {
        "job_id": "historical-job",
        "profile": profile.public(),
        "request": request.public(),
        "extraction_id": extraction_id,
        "state": "verified",
        "result": {"bar_count": None},
    }
    return profile, job, run, ledgers, docs


def test_multiple_chunks_sorted_counted_with_provenance():
    profile, job, run, ledgers, docs = evidence()
    dataset = reconstruct(profile, job, run, ledgers, list(reversed(docs)))
    assert dataset.bar_count == 2
    assert [bar.timestamp.day for bar in dataset.bars] == [2, 3]
    assert all(bar.timestamp.tzinfo == UTC for bar in dataset.bars)
    assert dataset.request.ticker == "AAPL" and dataset.provider == "massive"
    assert dataset.request.adjusted is True
    assert len(dataset.captures[0].document_ids) == 2
    assert dataset.captures[0].captured_at
    assert job["result"]["bar_count"] is None


def test_noncanonical_capture_excluded_even_when_supplied():
    profile, job, run, ledgers, docs = evidence()
    alternate = copy.deepcopy(docs[0])
    alternate["_id"] = ObjectId()
    alternate["payload"]["results"] = [row(4, close=200)]
    dataset = reconstruct(profile, job, run, ledgers, docs + [alternate])
    assert dataset.bar_count == 2
    assert all(bar.close == 102 for bar in dataset.bars)


def test_empty_canonical_extraction():
    dataset = reconstruct(*evidence([[[]]]))
    assert dataset.bars == () and dataset.bar_count == 0
    assert len(dataset.captures) == 1


def test_exact_duplicates_coalesce_with_all_source_pages():
    dataset = reconstruct(*evidence([[[row(2), row(3)]], [[row(2)]]]))
    assert dataset.bar_count == 2
    assert dataset.exact_duplicates == 1
    assert dataset.bars[0].pages == (1, 2)


def test_incompatible_same_timestamp_is_conflict():
    with pytest.raises(ReadingError, match="bar_conflict"):
        reconstruct(*evidence([[[row(2)]], [[row(2, close=103)]]]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("o", True),
        ("h", "105"),
        ("c", float("nan")),
        ("c", float("inf")),
        ("v", -1),
        ("t", True),
        ("t", 10**30),
        ("l", 110),
    ],
)
def test_invalid_ohlcv_rejected_even_if_hashes_match(field, value):
    bad = row() | {field: value}
    with pytest.raises(ReadingError, match="invalid_bar"):
        reconstruct(*evidence([[[bad]]]))


@pytest.mark.parametrize(
    "mutation",
    [
        "payload",
        "missing",
        "conflict",
        "source",
        "parameters",
        "run_invalid",
        "run_failed",
        "chunk_number",
        "boolean_page",
        "hash",
        "duplicate_ids",
    ],
)
def test_corruption_blocks_historically_verified_job(mutation):
    profile, job, run, ledgers, docs = evidence()
    if mutation == "payload":
        docs[0]["payload"]["results"][0]["c"] += 1
    elif mutation == "missing":
        docs.pop()
    elif mutation == "conflict":
        ledgers[0]["observed_content_hashes"].append("different-content")
    elif mutation == "source":
        docs[0]["source"] = "other"
    elif mutation == "parameters":
        run["parameters"] = run["parameters"] | {"adjusted": False}
    elif mutation == "run_invalid":
        run["verification_status"] = "invalid"
    elif mutation == "run_failed":
        run["status"] = "failed"
    elif mutation == "chunk_number":
        docs[0]["pagination"]["chunk_number"] = 2
    elif mutation == "boolean_page":
        docs[0]["pagination"]["page_number"] = True
    elif mutation == "hash":
        ledgers[0]["canonical_payload_hash"] = "changed"
    else:
        ledgers[0]["canonical_document_ids"].append(
            ledgers[0]["canonical_document_ids"][0]
        )
    with pytest.raises(ReadingError):
        reconstruct(profile, job, run, ledgers, docs)


@pytest.mark.parametrize(
    "change", ["profile", "database", "cluster", "extraction", "request", "provider"]
)
def test_selection_validated_before_creating_client(monkeypatch, change):
    profile, job, *_ = evidence()
    if change == "profile":
        profile = replace(profile, profile_id="other")
    elif change == "database":
        profile = replace(profile, database="other")
    elif change == "cluster":
        profile = replace(profile, mongodb_uri="mongodb://other-cluster")
    elif change == "extraction":
        job["extraction_id"] = "unrelated"
    elif change == "request":
        job["request"]["ticker"] = "MSFT"
    else:
        job["profile"]["provider"] = "other"

    def forbidden(_):
        raise AssertionError("Database access before selection validation")

    monkeypatch.setattr(canonical, "explicit_atlas_client", forbidden)
    with pytest.raises(ReadingError, match="selection_mismatch"):
        read_extraction(profile, job)


def test_explicit_reader_uses_canonical_ids_and_never_writes(monkeypatch):
    profile, job, run, ledgers, docs = evidence()
    client = mongomock.MongoClient(tz_aware=True)
    db = client[profile.database]
    db.ingestion_runs.insert_one(run)
    db.ingestion_page_ledger.insert_many(ledgers)
    db.raw_ingestion.insert_many(docs)
    alternate = copy.deepcopy(docs[0])
    alternate["_id"] = ObjectId()
    alternate["payload"]["results"] = [row(4)]
    db.raw_ingestion.insert_one(alternate)
    before = {name: list(db[name].find()) for name in db.list_collection_names()}
    env = dict(os.environ)
    monkeypatch.setattr(
        canonical,
        "explicit_atlas_client",
        lambda actual: client if actual == profile else None,
    )
    result = read_extraction(profile, job)
    assert result.bar_count == 2
    assert dict(os.environ) == env
    assert before == {
        name: list(db[name].find()) for name in db.list_collection_names()
    }
    assert job["result"]["bar_count"] is None


def test_reader_driver_failure_is_secret_safe(monkeypatch):
    profile, job, *_ = evidence()

    def fail(_):
        raise RuntimeError(profile.mongodb_uri)

    monkeypatch.setattr(canonical, "explicit_atlas_client", fail)
    with pytest.raises(ReadingError) as caught:
        read_extraction(profile, job)
    assert str(caught.value) == "read_failed"
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("collection", ["ingestion_runs", "ingestion_page_ledger"])
def test_changed_evidence_during_read_is_rejected(monkeypatch, collection):
    profile, job, run, ledgers, docs = evidence()
    client = mongomock.MongoClient(tz_aware=True)
    db = client[profile.database]
    db.ingestion_runs.insert_one(run)
    db.ingestion_page_ledger.insert_many(ledgers)
    db.raw_ingestion.insert_many(docs)
    original = canonical.reconstruct

    def concurrent_change(*args):
        dataset = original(*args)
        db[collection].update_one({}, {"$set": {"changed_during_read": True}})
        return dataset

    monkeypatch.setattr(canonical, "explicit_atlas_client", lambda _: client)
    monkeypatch.setattr(canonical, "reconstruct", concurrent_change)
    with pytest.raises(ReadingError, match="evidence_changed"):
        read_extraction(profile, job)


def test_pure_reader_import_has_no_legacy_configuration():
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import centauro_atlas_bridge.reading.canonical; "
                "assert 'centauro_atlas_bridge.config' not in sys.modules; "
                "assert 'centauro_atlas_bridge.sources.massive' not in sys.modules"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

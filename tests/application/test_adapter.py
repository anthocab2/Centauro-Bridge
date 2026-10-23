"""Offline integration: real extractor, hashes, checkpoints and verifier on mocked I/O."""

from copy import deepcopy

import httpx
import mongomock
import pytest
from pymongo.errors import ConnectionFailure, OperationFailure

from centauro_atlas_bridge.application.adapter import MassiveAtlasAdapter
from centauro_atlas_bridge.application.diagnostics import (
    VerificationFailed,
    classify_error,
)
from centauro_atlas_bridge.application.models import Request
from centauro_atlas_bridge.ingestion import (
    checkpoints,
    http_client,
    page_ledger,
    raw,
    runs,
    verification,
)
from centauro_atlas_bridge.sources import massive


@pytest.fixture
def engine(monkeypatch):
    # mongomock 4.3 lacks PyMongo's optional sort=None bulk argument. The engine
    # does not use sorting; reject any non-default value rather than simulate it.
    original_add_update = mongomock.collection.BulkOperationBuilder.add_update

    def compatible_add_update(self, *args, sort=None, **kwargs):
        assert sort is None
        return original_add_update(self, *args, **kwargs)

    monkeypatch.setattr(
        mongomock.collection.BulkOperationBuilder, "add_update", compatible_add_update
    )
    client = mongomock.MongoClient()
    for module in (checkpoints, page_ledger, raw, runs, verification):
        monkeypatch.setattr(module, "create_atlas_client", lambda: client)
        monkeypatch.setattr(module, "get_database_name", lambda: "mvp_test")
    monkeypatch.setattr(massive, "get_massive_api_key", lambda: "secret-sentinel")
    monkeypatch.setattr(http_client.time, "sleep", lambda _: None)
    return MassiveAtlasAdapter(), client["mvp_test"]


def request():
    return Request("AAPL", "2025-01-02", "2025-01-03")


def respond(monkeypatch, payload, status=200):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status, json=deepcopy(payload), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(http_client.httpx, "get", get)
    return calls


def payload(results=None):
    results = (
        [{"t": 1, "o": 10, "h": 12, "l": 9, "c": 11, "v": 50}]
        if results is None
        else results
    )
    return {"status": "OK", "resultsCount": len(results), "results": results}


def test_actual_engine_new_then_reuse_without_duplicate_storage(engine, monkeypatch):
    adapter, database = engine
    calls = respond(monkeypatch, payload())
    events = []
    first = adapter.execute(request(), lambda **change: events.append(change))
    before = list(database[raw.RAW_COLLECTION].find())
    second = adapter.execute(request(), lambda **change: None)
    assert first["mode"] == "new"
    assert first["verified"] is True
    assert second["mode"] == "reused"
    assert second["verified"] is True
    assert (
        second["capability"]["status"] == "unknown"
    )  # No current provider request on reuse.
    assert list(database[raw.RAW_COLLECTION].find()) == before
    assert len(calls) == 1
    assert first["bar_count"] is None and second["bar_count"] is None
    assert [event["state"] for event in events] == ["executing", "verifying"]
    assert adapter.extraction_id(request()) == massive.build_extraction_id(
        **request().public()
    )


def test_valid_empty_payload_is_verified_empty(engine, monkeypatch):
    adapter, _ = engine
    respond(monkeypatch, payload([]))
    result = adapter.execute(request(), lambda **change: None)
    assert result["verified"] is True
    assert result["data_status"] == "empty"
    assert result["bar_count"] is None


@pytest.mark.parametrize(
    "status, expected",
    [(401, "credentials"), (403, "access_restricted"), (429, "rate_limited")],
)
def test_controlled_http_responses_through_real_extractor(
    engine, monkeypatch, status, expected
):
    adapter, database = engine
    calls = respond(monkeypatch, {"error": "secret-sentinel"}, status)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        adapter.execute(request(), lambda **change: None)
    result = classify_error(caught.value)
    assert result["code"] == expected
    assert result["http_status"] == status
    assert "secret-sentinel" not in str(result)
    assert "plan" not in str(result)
    assert database[raw.RAW_COLLECTION].count_documents({}) == 0
    assert database[runs.INGESTION_RUNS_COLLECTION].find_one()["status"] == "failed"
    assert len(calls) == (5 if status == 429 else 1)


def test_verifier_rejection_cannot_mark_stored_extraction_verified(engine, monkeypatch):
    adapter, database = engine
    respond(monkeypatch, payload())
    original = verification.verify_extraction

    def corrupted(extraction_id):
        database[raw.RAW_COLLECTION].update_one(
            {}, {"$set": {"payload.results.0.c": -1}}
        )
        return original(extraction_id)

    monkeypatch.setattr(verification, "verify_extraction", corrupted)
    events = []
    with pytest.raises(VerificationFailed):
        adapter.execute(request(), lambda **change: events.append(change))
    assert events[-2]["storage_status"] == "completed"
    assert events[-1]["verification_status"] == "invalid"


def test_final_checkpoint_gap_is_recovered(engine, monkeypatch):
    adapter, _ = engine
    calls = respond(monkeypatch, payload())
    original = massive.complete_run

    def fail(**kwargs):
        raise ConnectionFailure("secret-sentinel")

    monkeypatch.setattr(massive, "complete_run", fail)
    with pytest.raises(ConnectionFailure):
        adapter.execute(request(), lambda **change: None)
    monkeypatch.setattr(massive, "complete_run", original)
    result = adapter.execute(request(), lambda **change: None)
    assert result["mode"] == "recovered"
    assert result["verified"] is True
    assert len(calls) == 1


def test_page_interruption_resumes_same_identity(engine, monkeypatch):
    adapter, _ = engine
    first = payload()
    first["next_url"] = "https://api.massive.com/v2/next?cursor=page2"
    count = 0

    def get(url, **kwargs):
        nonlocal count
        count += 1
        if count > 1:
            raise httpx.ConnectError("secret-sentinel")
        return httpx.Response(200, json=first, request=httpx.Request("GET", url))

    monkeypatch.setattr(http_client.httpx, "get", get)
    with pytest.raises(httpx.ConnectError):
        adapter.execute(request(), lambda **change: None)
    calls = respond(monkeypatch, payload([{"t": 2, "c": 12}]))
    result = adapter.execute(request(), lambda **change: None)
    assert result["mode"] == "resumed" and result["verified"]
    assert result["observed_pages"] == 2
    assert len(calls) == 1 and "cursor=page2" in calls[0][0]


@pytest.mark.parametrize(
    "error, code",
    [
        (httpx.ConnectError("secret-sentinel"), "connection"),
        (ConnectionFailure("secret-sentinel"), "connection"),
        (OperationFailure("secret-sentinel", code=18), "credentials"),
        (OperationFailure("secret-sentinel", code=13), "access_restricted"),
        (RuntimeError("403 secret-sentinel"), "engine_failed"),
    ],
)
def test_diagnostics_use_observed_type_not_error_text(error, code):
    result = classify_error(error)
    assert result["code"] == code
    assert "secret-sentinel" not in str(result)

"""Unit tests for the HTTP-to-Atlas ingestion pipeline."""

from centauro_atlas_bridge.ingestion import pipeline


def test_extract_and_store_json(monkeypatch):
    """Verify that fetched JSON is passed unchanged to raw storage."""
    payload = {
        "results": [
            {"value": 123},
        ]
    }

    captured = {}

    def fake_fetch_json(url, parameters=None, headers=None):
        captured["url"] = url
        captured["request_parameters"] = parameters
        return payload

    def fake_store_raw_payload(
        source,
        endpoint,
        parameters,
        payload,
        pagination=None,
    ):
        captured["source"] = source
        captured["endpoint"] = endpoint
        captured["provenance_parameters"] = parameters
        captured["payload"] = payload
        captured["pagination"] = pagination

        return "mongo_test_id"

    monkeypatch.setattr(pipeline, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(pipeline, "store_raw_payload", fake_store_raw_payload)

    result = pipeline.extract_and_store_json(
        url="https://example.com/data",
        source="test_source",
        endpoint="/data",
        request_parameters={
            "ticker": "TEST",
            "api_key": "secret",
        },
        provenance_parameters={
            "ticker": "TEST",
        },
        headers={"Authorization": "secret"},
        pagination={"page": 1},
    )

    assert result == "mongo_test_id"

    assert captured["payload"] == payload
    assert captured["source"] == "test_source"
    assert captured["endpoint"] == "/data"

    assert captured["request_parameters"]["api_key"] == "secret"

    assert captured["provenance_parameters"] == {
        "ticker": "TEST"
    }

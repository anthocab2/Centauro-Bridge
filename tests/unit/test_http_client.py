"""Unit tests for HTTP extraction."""

import httpx
import pytest

from centauro_atlas_bridge.ingestion import http_client


def build_response(
    status_code,
    *,
    headers=None,
    json=None,
):
    """Build an HTTPX response suitable for unit tests."""
    request = httpx.Request(
        "GET",
        "https://example.com/data",
    )

    return httpx.Response(
        status_code=status_code,
        request=request,
        headers=headers,
        json=json,
    )


def test_fetch_json_returns_payload(
    monkeypatch,
):
    """Verify that JSON responses are returned correctly."""

    def fake_get(
        *args,
        **kwargs,
    ):
        return build_response(
            200,
            json={
                "results": [
                    {
                        "value": 123,
                    }
                ]
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    payload = http_client.fetch_json(
        "https://example.com/data"
    )

    assert payload == {
        "results": [
            {
                "value": 123,
            }
        ]
    }


def test_fetch_json_retries_retryable_error(
    monkeypatch,
):
    """Verify exponential backoff for temporary HTTP failures."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] < 3:
            return build_response(
                503
            )

        return build_response(
            200,
            json={
                "status": "ok",
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    payload = http_client.fetch_json(
        "https://example.com/data",
        max_retries=3,
    )

    assert payload == {
        "status": "ok",
    }

    assert calls["count"] == 3

    assert sleeps == [
        1.0,
        2.0,
    ]


def test_fetch_json_raises_after_retry_limit(
    monkeypatch,
):
    """Verify that persistent failures are eventually raised."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        return build_response(
            503
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    with pytest.raises(
        httpx.HTTPStatusError
    ):
        http_client.fetch_json(
            "https://example.com/data",
            max_retries=2,
        )

    assert calls["count"] == 3

    assert sleeps == [
        1.0,
        2.0,
    ]


def test_fetch_json_does_not_retry_non_retryable_error(
    monkeypatch,
):
    """Verify that permanent client errors are raised immediately."""
    calls = {
        "count": 0,
    }

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        return build_response(
            404
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    with pytest.raises(
        httpx.HTTPStatusError
    ):
        http_client.fetch_json(
            "https://example.com/data"
        )

    assert calls["count"] == 1


def test_fetch_json_honors_retry_after(
    monkeypatch,
):
    """Verify that a 429 Retry-After header controls the wait."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            return build_response(
                429,
                headers={
                    "Retry-After": "12",
                },
            )

        return build_response(
            200,
            json={
                "status": "ok",
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    payload = http_client.fetch_json(
        "https://example.com/data"
    )

    assert payload == {
        "status": "ok",
    }

    assert calls["count"] == 2

    assert sleeps == [
        12.0,
    ]


def test_fetch_json_honors_long_retry_after(
    monkeypatch,
):
    """Verify provider delays are not shortened by local backoff limits."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            return build_response(
                429,
                headers={
                    "Retry-After": "120",
                },
            )

        return build_response(
            200,
            json={
                "status": "ok",
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    payload = http_client.fetch_json(
        "https://example.com/data"
    )

    assert payload == {
        "status": "ok",
    }

    assert sleeps == [
        120.0,
    ]


def test_fetch_json_honors_retry_after_on_503(
    monkeypatch,
):
    """Verify Retry-After is respected for service unavailability."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            return build_response(
                503,
                headers={
                    "Retry-After": "120",
                },
            )

        return build_response(
            200,
            json={
                "status": "ok",
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    payload = http_client.fetch_json(
        "https://example.com/data"
    )

    assert payload == {
        "status": "ok",
    }

    assert sleeps == [
        120.0,
    ]


def test_fetch_json_uses_rate_limit_fallback(
    monkeypatch,
):
    """Verify safe fallback when a 429 has no Retry-After header."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            return build_response(
                429
            )

        return build_response(
            200,
            json={
                "status": "ok",
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    payload = http_client.fetch_json(
        "https://example.com/data"
    )

    assert payload == {
        "status": "ok",
    }

    assert calls["count"] == 2

    assert sleeps == [
        15.0,
    ]


def test_fetch_json_invalid_retry_after_uses_fallback(
    monkeypatch,
):
    """Verify malformed Retry-After values cannot break retries."""
    calls = {
        "count": 0,
    }

    sleeps = []

    def fake_get(
        *args,
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            return build_response(
                429,
                headers={
                    "Retry-After":
                        "not-a-valid-value",
                },
            )

        return build_response(
            200,
            json={
                "status": "ok",
            },
        )

    monkeypatch.setattr(
        http_client.httpx,
        "get",
        fake_get,
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        sleeps.append,
    )

    payload = http_client.fetch_json(
        "https://example.com/data"
    )

    assert payload == {
        "status": "ok",
    }

    assert sleeps == [
        15.0,
    ]


def test_fetch_json_rejects_negative_max_retries():
    """Verify invalid retry configuration is rejected."""
    with pytest.raises(
        ValueError,
        match="max_retries cannot be negative",
    ):
        http_client.fetch_json(
            "https://example.com/data",
            max_retries=-1,
        )


def test_fetch_json_rejects_negative_retry_delay():
    """Verify invalid retry delays are rejected."""
    with pytest.raises(
        ValueError,
        match="retry_delay cannot be negative",
    ):
        http_client.fetch_json(
            "https://example.com/data",
            retry_delay=-1,
        )

"""Security tests for the Massive source adapter."""

import pytest

from centauro_atlas_bridge.sources import massive


def test_validate_massive_url_accepts_official_https_host():
    """Official Massive HTTPS URLs must be accepted."""
    url = (
        "https://api.massive.com/"
        "v2/aggs/ticker/AAPL"
    )

    assert (
        massive.validate_massive_url(
            url
        )
        == url
    )


def test_validate_massive_url_rejects_http():
    """Authentication must never be sent over plain HTTP."""
    with pytest.raises(
        ValueError,
        match="must use HTTPS",
    ):
        massive.validate_massive_url(
            "http://api.massive.com/test"
        )


def test_validate_massive_url_rejects_foreign_host():
    """Authenticated pagination must never follow another domain."""
    with pytest.raises(
        ValueError,
        match="unauthorized host",
    ):
        massive.validate_massive_url(
            "https://evil.example/steal"
        )


def test_validate_massive_url_rejects_host_suffix_attack():
    """A hostname merely ending with the provider name is not trusted."""
    with pytest.raises(
        ValueError,
        match="unauthorized host",
    ):
        massive.validate_massive_url(
            "https://api.massive.com.evil.example/steal"
        )


def test_validate_massive_url_rejects_userinfo():
    """Provider URLs must not contain embedded user credentials."""
    with pytest.raises(
        ValueError,
        match="must not contain user credentials",
    ):
        massive.validate_massive_url(
            "https://user:password@api.massive.com/test"
        )


def test_validate_massive_url_rejects_non_https_port():
    """Authenticated requests must not use an unexpected port."""
    with pytest.raises(
        ValueError,
        match="HTTPS port",
    ):
        massive.validate_massive_url(
            "https://api.massive.com:8443/test"
        )


def test_sanitize_payload_removes_api_key_from_next_url():
    """Stored provider payloads must not retain pagination credentials."""
    original = {
        "status": "OK",
        "results": [
            {
                "c": 100.0,
            }
        ],
        "next_url": (
            "https://api.massive.com/v3/test"
            "?cursor=abc123&apiKey=secret-value"
        ),
    }

    safe = (
        massive.sanitize_payload_for_storage(
            original
        )
    )

    assert (
        "secret-value"
        not in safe["next_url"]
    )

    assert (
        "apiKey"
        not in safe["next_url"]
    )

    assert (
        "cursor=abc123"
        in safe["next_url"]
    )

    assert (
        "secret-value"
        in original["next_url"]
    )


def test_foreign_next_url_is_rejected_before_storage(
    monkeypatch,
):
    """A hostile next_url must fail before storage or a second request."""
    captured = {
        "fetches": [],
    }

    monkeypatch.setattr(
        massive,
        "get_massive_api_key",
        lambda: "secret-test-key",
    )

    monkeypatch.setattr(
        massive,
        "get_checkpoint",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        massive,
        "start_run",
        lambda **kwargs: kwargs,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        lambda **kwargs: kwargs,
    )

    def fake_fetch_json(
        url,
        parameters=None,
        headers=None,
        **kwargs,
    ):
        captured[
            "fetches"
        ].append(
            {
                "url": url,
                "headers": headers,
            }
        )

        return {
            "status": "OK",
            "results": [
                {
                    "c": 100.0,
                }
            ],
            "next_url": (
                "https://evil.example/"
                "collect"
            ),
        }

    def fake_store_raw_payload_chunks(
        **kwargs,
    ):
        captured[
            "stored"
        ] = True

        return [
            "document_id"
        ]

    monkeypatch.setattr(
        massive,
        "fetch_json",
        fake_fetch_json,
    )

    monkeypatch.setattr(
        massive,
        "store_raw_payload_chunks",
        fake_store_raw_payload_chunks,
    )

    with pytest.raises(
        ValueError,
        match="unauthorized host",
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )

    assert (
        len(
            captured[
                "fetches"
            ]
        )
        == 1
    )

    assert (
        captured[
            "fetches"
        ][0][
            "url"
        ].startswith(
            "https://api.massive.com/"
        )
    )

    assert (
        captured[
            "fetches"
        ][0][
            "headers"
        ][
            "Authorization"
        ]
        == "Bearer secret-test-key"
    )

    assert (
        "stored"
        not in captured
    )


def test_checkpoint_foreign_url_is_rejected_before_fetch(
    monkeypatch,
):
    """A corrupted checkpoint must never receive the API token."""
    captured = {
        "fetch_called": False,
    }

    monkeypatch.setattr(
        massive,
        "get_massive_api_key",
        lambda: "secret-test-key",
    )

    monkeypatch.setattr(
        massive,
        "get_checkpoint",
        lambda **kwargs: {
            "cursor": (
                "https://evil.example/"
                "resume"
            ),
            "metadata": {
                "completed": False,
                "last_page": 1,
            },
        },
    )

    monkeypatch.setattr(
        massive,
        "start_run",
        lambda **kwargs: kwargs,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        lambda **kwargs: kwargs,
    )

    def fake_fetch_json(
        **kwargs,
    ):
        captured[
            "fetch_called"
        ] = True

        return {
            "results": [],
        }

    monkeypatch.setattr(
        massive,
        "fetch_json",
        fake_fetch_json,
    )

    with pytest.raises(
        ValueError,
        match="unauthorized host",
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2020-01-01",
            end_date="2026-01-01",
        )

    assert (
        captured[
            "fetch_called"
        ]
        is False
    )

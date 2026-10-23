import os
from unittest.mock import MagicMock

import httpx
import pytest

from centauro_atlas_bridge.application import connections
from centauro_atlas_bridge.application.models import Request
from tests.reading.test_canonical import evidence


def test_atlas_ping_does_not_claim_write_permissions(monkeypatch):
    profile, *_ = evidence()
    client = MagicMock()
    client.__enter__.return_value = client
    monkeypatch.setattr(connections, "explicit_atlas_client", lambda actual: client)
    before = dict(os.environ)
    result = connections.probe_atlas(profile)
    client.admin.command.assert_called_once_with("ping")
    assert result["status"] == "confirmed" and result["write_access"] == "unknown"
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "status,code",
    [(401, "credentials"), (403, "access_restricted"), (429, "rate_limited")],
)
def test_massive_probe_is_one_bounded_request_and_safe(monkeypatch, status, code):
    profile, *_ = evidence()
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(
            status, json={"error": "secret-api"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(connections.httpx, "get", get)
    result = connections.probe_massive(
        profile, Request("AAPL", "2025-01-02", "2025-01-02")
    )
    assert result["diagnostic"]["code"] == code
    assert result["exact_plan"] == "unknown"
    assert "secret-api" not in str(result)
    assert len(calls) == 1 and calls[0]["params"]["limit"] == 1
    assert calls[0]["follow_redirects"] is False


def test_valid_empty_probe_confirms_only_its_request(monkeypatch):
    profile, *_ = evidence()
    monkeypatch.setattr(
        connections.httpx,
        "get",
        lambda url, **kwargs: httpx.Response(
            200,
            json={"status": "OK", "results": [], "resultsCount": 0},
            request=httpx.Request("GET", url),
        ),
    )
    result = connections.probe_massive(
        profile, Request("AAPL", "2025-01-02", "2025-01-02")
    )
    assert result["status"] == "confirmed" and result["data_status"] == "empty"
    assert result["request"]["start_date"] == result["request"]["end_date"]
    assert result["exact_plan"] == "unknown"

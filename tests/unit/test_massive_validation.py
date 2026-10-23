"""Tests for Massive response-content validation."""

import pytest

from centauro_atlas_bridge.sources import massive


def test_valid_massive_payload_is_accepted():
    """A normal successful aggregate response must pass validation."""
    payload = {
        "status": "OK",
        "request_id": "request_123",
        "resultsCount": 1,
        "results": [
            {
                "c": 100.0,
            }
        ],
    }

    assert (
        massive.validate_massive_payload(
            payload
        )
        is payload
    )


def test_empty_successful_results_are_valid():
    """A successful response may legitimately contain zero records."""
    payload = {
        "status": "OK",
        "resultsCount": 0,
        "results": [],
    }

    massive.validate_massive_payload(
        payload
    )


def test_error_status_is_rejected():
    """HTTP success must not hide a logical Massive error."""
    payload = {
        "status": "ERROR",
        "error": "simulated provider error",
    }

    with pytest.raises(
        massive.MassiveResponseError,
        match="status is not OK",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_missing_status_is_rejected():
    """A response without Massive success status is not a valid page."""
    payload = {
        "results": [],
    }

    with pytest.raises(
        massive.MassiveResponseError,
        match="status is not OK",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_missing_results_is_rejected():
    """A successful aggregate page must contain results."""
    payload = {
        "status": "OK",
    }

    with pytest.raises(
        massive.MassiveResponseError,
        match="does not contain results",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_non_list_results_are_rejected():
    """Aggregate results must have the expected collection type."""
    payload = {
        "status": "OK",
        "results": {
            "c": 100.0,
        },
    }

    with pytest.raises(
        TypeError,
        match="results must be a list",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_results_count_must_match_results():
    """Provider metadata must agree with the records received."""
    payload = {
        "status": "OK",
        "resultsCount": 2,
        "results": [
            {
                "c": 100.0,
            }
        ],
    }

    with pytest.raises(
        massive.MassiveResponseError,
        match="does not match results",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_results_count_must_be_integer():
    """Malformed result-count metadata must be rejected."""
    payload = {
        "status": "OK",
        "resultsCount": "1",
        "results": [
            {
                "c": 100.0,
            }
        ],
    }

    with pytest.raises(
        TypeError,
        match="resultsCount must be an integer",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_invalid_next_url_type_is_rejected():
    """Pagination metadata must have the expected type."""
    payload = {
        "status": "OK",
        "results": [],
        "next_url": {
            "cursor": "abc123",
        },
    }

    with pytest.raises(
        TypeError,
        match="next_url must be a string",
    ):
        massive.validate_massive_payload(
            payload
        )


def test_error_payload_never_reaches_storage_or_checkpoint(
    monkeypatch,
):
    """Logical provider errors must stop before persistence."""
    captured = {
        "stored": False,
        "checkpoint": False,
        "completed": False,
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
        "fetch_json",
        lambda **kwargs: {
            "status": "ERROR",
            "error": "simulated provider failure",
        },
    )

    def fake_store(
        **kwargs,
    ):
        captured[
            "stored"
        ] = True

        return [
            "unexpected_document"
        ]

    def fake_checkpoint(
        **kwargs,
    ):
        captured[
            "checkpoint"
        ] = True

        return kwargs

    def fake_complete(
        **kwargs,
    ):
        captured[
            "completed"
        ] = True

        return kwargs

    def fake_fail(
        **kwargs,
    ):
        captured[
            "failure"
        ] = kwargs

        return kwargs

    monkeypatch.setattr(
        massive,
        "store_raw_payload_chunks",
        fake_store,
    )

    monkeypatch.setattr(
        massive,
        "save_checkpoint",
        fake_checkpoint,
    )

    monkeypatch.setattr(
        massive,
        "complete_run",
        fake_complete,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        fake_fail,
    )

    with pytest.raises(
        massive.MassiveResponseError,
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )

    assert (
        captured[
            "stored"
        ]
        is False
    )

    assert (
        captured[
            "checkpoint"
        ]
        is False
    )

    assert (
        captured[
            "completed"
        ]
        is False
    )

    assert (
        captured[
            "failure"
        ][
            "error"
        ]
        == "MassiveResponseError"
    )

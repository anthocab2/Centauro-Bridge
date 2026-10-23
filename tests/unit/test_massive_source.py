"""Unit tests for the Massive source adapter."""

import pytest

from centauro_atlas_bridge.ingestion.page_ledger import (
    calculate_page_content_hash,
)
from centauro_atlas_bridge.sources import massive


def test_extract_daily_aggs_builds_safe_request(
    monkeypatch,
):
    """Verify extraction stores one canonical source page."""
    captured = {}

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

    def fake_start_run(
        **kwargs,
    ):
        captured[
            "started"
        ] = kwargs
        return kwargs

    def fake_fetch_json(
        url,
        parameters=None,
        headers=None,
        **kwargs,
    ):
        captured[
            "url"
        ] = url

        captured[
            "request_parameters"
        ] = parameters

        captured[
            "headers"
        ] = headers

        return {
            "status": "OK",
            "request_id": "request_A",
            "results": [
                {
                    "c": 100.0,
                }
            ],
        }

    def fake_store_raw_payload_chunks(
        source,
        endpoint,
        parameters,
        payload,
        pagination=None,
    ):
        captured[
            "source"
        ] = source

        captured[
            "endpoint"
        ] = endpoint

        captured[
            "provenance_parameters"
        ] = parameters

        captured[
            "payload"
        ] = payload

        captured[
            "pagination"
        ] = pagination

        return [
            "mongo_test_id"
        ]

    def fake_register_canonical_page(
        **kwargs,
    ):
        captured[
            "ledger"
        ] = kwargs

        return {
            "canonical_content_hash":
                kwargs[
                    "content_hash"
                ],
            "canonical_payload_hash":
                kwargs[
                    "payload_hash"
                ],
            "canonical_document_ids":
                kwargs[
                    "document_ids"
                ],
        }

    def fake_save_checkpoint(
        **kwargs,
    ):
        captured[
            "checkpoint"
        ] = kwargs
        return kwargs

    def fake_complete_run(
        **kwargs,
    ):
        captured[
            "completed"
        ] = kwargs
        return kwargs

    def fake_fail_run(
        **kwargs,
    ):
        captured[
            "failed"
        ] = kwargs
        return kwargs

    monkeypatch.setattr(
        massive,
        "start_run",
        fake_start_run,
    )

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

    monkeypatch.setattr(
        massive,
        "register_canonical_page",
        fake_register_canonical_page,
    )

    monkeypatch.setattr(
        massive,
        "save_checkpoint",
        fake_save_checkpoint,
    )

    monkeypatch.setattr(
        massive,
        "complete_run",
        fake_complete_run,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        fake_fail_run,
    )

    result = (
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )
    )

    assert result == [
        "mongo_test_id"
    ]

    assert (
        captured[
            "headers"
        ][
            "Authorization"
        ]
        == "Bearer secret-test-key"
    )

    assert (
        "secret-test-key"
        not in str(
            captured[
                "provenance_parameters"
            ]
        )
    )

    assert (
        captured[
            "ledger"
        ][
            "page_number"
        ]
        == 1
    )

    assert (
        captured[
            "ledger"
        ][
            "record_count"
        ]
        == 1
    )

    assert (
        captured[
            "completed"
        ][
            "pages_stored"
        ]
        == 1
    )

    assert (
        "failed"
        not in captured
    )


def test_retry_with_changed_metadata_uses_canonical_documents(
    monkeypatch,
):
    """A metadata-only retry must not become a second logical page."""
    captured = {}

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

    payload = {
        "status": "OK",
        "request_id": "NEW_REQUEST_ID",
        "results": [
            {
                "c": 100.0,
            }
        ],
    }

    monkeypatch.setattr(
        massive,
        "fetch_json",
        lambda **kwargs: payload,
    )

    monkeypatch.setattr(
        massive,
        "store_raw_payload_chunks",
        lambda **kwargs: [
            "new_raw_capture",
        ],
    )

    current_content_hash = (
        calculate_page_content_hash(
            payload
        )
    )

    monkeypatch.setattr(
        massive,
        "register_canonical_page",
        lambda **kwargs: {
            "canonical_content_hash":
                current_content_hash,
            "canonical_payload_hash":
                "older_payload_hash",
            "canonical_document_ids": [
                "original_canonical_document",
            ],
        },
    )

    def fake_save_checkpoint(
        **kwargs,
    ):
        captured[
            "checkpoint"
        ] = kwargs
        return kwargs

    monkeypatch.setattr(
        massive,
        "save_checkpoint",
        fake_save_checkpoint,
    )

    monkeypatch.setattr(
        massive,
        "complete_run",
        lambda **kwargs: kwargs,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        lambda **kwargs: kwargs,
    )

    result = (
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )
    )

    assert result == [
        "original_canonical_document"
    ]

    assert (
        captured[
            "checkpoint"
        ][
            "metadata"
        ][
            "last_page"
        ]
        == 1
    )


def test_changed_page_content_fails_before_checkpoint(
    monkeypatch,
):
    """Different records on a retry must stop the extraction."""
    captured = {}

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

    payload = {
        "status": "OK",
        "request_id": "request_B",
        "results": [
            {
                "c": 101.0,
            }
        ],
    }

    monkeypatch.setattr(
        massive,
        "fetch_json",
        lambda **kwargs: payload,
    )

    monkeypatch.setattr(
        massive,
        "store_raw_payload_chunks",
        lambda **kwargs: [
            "new_capture",
        ],
    )

    old_content_hash = (
        calculate_page_content_hash(
            {
                "results": [
                    {
                        "c": 100.0,
                    }
                ]
            }
        )
    )

    monkeypatch.setattr(
        massive,
        "register_canonical_page",
        lambda **kwargs: {
            "canonical_content_hash":
                old_content_hash,
            "canonical_payload_hash":
                "old_payload",
            "canonical_document_ids": [
                "old_document",
            ],
        },
    )

    def fake_save_checkpoint(
        **kwargs,
    ):
        captured[
            "checkpoint_saved"
        ] = True
        return kwargs

    def fake_fail_run(
        **kwargs,
    ):
        captured[
            "failure"
        ] = kwargs
        return kwargs

    monkeypatch.setattr(
        massive,
        "save_checkpoint",
        fake_save_checkpoint,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        fake_fail_run,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Logical page content "
            "changed across retries"
        ),
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )

    assert (
        "checkpoint_saved"
        not in captured
    )

    assert (
        captured[
            "failure"
        ][
            "error"
        ]
        == "RuntimeError"
    )


def test_failed_extraction_marks_run_failed(
    monkeypatch,
):
    """Verify extraction failures update run state."""
    captured = {}

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

    def fake_fetch_json(
        **kwargs,
    ):
        raise RuntimeError(
            "simulated failure"
        )

    def fake_fail_run(
        **kwargs,
    ):
        captured.update(
            kwargs
        )
        return kwargs

    monkeypatch.setattr(
        massive,
        "fetch_json",
        fake_fetch_json,
    )

    monkeypatch.setattr(
        massive,
        "fail_run",
        fake_fail_run,
    )

    with pytest.raises(
        RuntimeError
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )

    assert (
        captured[
            "error"
        ]
        == "RuntimeError"
    )


def test_completed_checkpoint_without_run_is_rejected(
    monkeypatch,
):
    """Checkpoint completion alone must never fabricate completion."""
    monkeypatch.setattr(
        massive,
        "get_massive_api_key",
        lambda: "secret-test-key",
    )

    monkeypatch.setattr(
        massive,
        "get_checkpoint",
        lambda **kwargs: {
            "cursor": None,
            "metadata": {
                "completed": True,
                "last_page": 1,
            },
        },
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda extraction_id: None,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint "
            "exists without run state"
        ),
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )


def test_completed_checkpoint_with_incomplete_run_is_rejected(
    monkeypatch,
):
    """Conflicting completion state must be surfaced."""
    monkeypatch.setattr(
        massive,
        "get_massive_api_key",
        lambda: "secret-test-key",
    )

    monkeypatch.setattr(
        massive,
        "get_checkpoint",
        lambda **kwargs: {
            "cursor": None,
            "metadata": {
                "completed": True,
                "last_page": 1,
            },
        },
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda extraction_id: {
            "status": "failed",
        },
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint "
            "conflicts with run identity"
        ),
    ):
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2026-07-20",
            end_date="2026-07-24",
        )

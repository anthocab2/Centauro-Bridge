"""Unit tests for resumable Massive extraction."""

from centauro_atlas_bridge.sources import massive


def test_extraction_resumes_from_saved_checkpoint(
    monkeypatch,
):
    """Verify that an interrupted extraction resumes at the next page."""
    captured = {}

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
                "https://api.massive.com/"
                "next-page?cursor=abc123"
            ),
            "metadata": {
                "completed": False,
                "last_page": 1,
            },
        },
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
            "parameters"
        ] = parameters

        captured[
            "headers"
        ] = headers

        return {
            "status": "OK",
            "request_id": "resume_request",
            "resultsCount": 1,
            "results": [
                {
                    "c": 101.0,
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
            "pagination"
        ] = pagination

        captured[
            "payload"
        ] = payload

        return [
            "page_2_id"
        ]

    def fake_register_canonical_page(
        **kwargs,
    ):
        captured[
            "ledger"
        ] = kwargs

        return {
            "canonical_payload_hash": (
                kwargs[
                    "payload_hash"
                ]
            ),
            "canonical_content_hash": (
                kwargs[
                    "content_hash"
                ]
            ),
            "canonical_document_ids": [
                "page_2_id"
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

    result = (
        massive.extract_daily_aggs(
            ticker="AAPL",
            start_date="2020-01-01",
            end_date="2026-01-01",
        )
    )

    assert result == [
        "page_2_id"
    ]

    assert (
        captured[
            "url"
        ]
        == (
            "https://api.massive.com/"
            "next-page?cursor=abc123"
        )
    )

    assert (
        captured[
            "parameters"
        ]
        is None
    )

    assert (
        captured[
            "pagination"
        ][
            "page_number"
        ]
        == 2
    )

    assert (
        captured[
            "ledger"
        ][
            "page_number"
        ]
        == 2
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
            "checkpoint"
        ][
            "metadata"
        ][
            "last_page"
        ]
        == 2
    )

    assert (
        captured[
            "checkpoint"
        ][
            "metadata"
        ][
            "completed"
        ]
        is True
    )

    assert (
        captured[
            "completed"
        ][
            "pages_stored"
        ]
        == 2
    )

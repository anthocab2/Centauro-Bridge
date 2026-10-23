"""Regression tests for final checkpoint recovery."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import real_massive_pagination_test as script


def _verification(
    run: dict,
) -> dict:
    """Build verification evidence from the simulated run state."""
    completed = (
        run.get(
            "status"
        )
        == "completed"
    )

    return {
        "verified":
            completed,
        "verification_status":
            (
                "verified"
                if completed
                else "invalid"
            ),
        "verification_errors":
            (
                []
                if completed
                else [
                    "execution_not_completed",
                ]
            ),
        "ledger_page_numbers": [
            1,
        ],
        "canonical_page_numbers": [
            1,
        ],
        "total_results":
            1,
        "expected_pages":
            1,
        "observed_pages":
            1,
        "duplicate_ingestion_keys":
            0,
        "noncanonical_raw_documents":
            0,
        "unregistered_raw_documents":
            0,
        "alternate_payload_variants":
            0,
    }


def test_final_checkpoint_gap_recovers_without_refetch(
    monkeypatch,
):
    """A completed checkpoint can finish a failed run safely."""
    extraction_id = (
        "real_ticker_pagination_finalgap"
    )

    state = {
        "checkpoint":
            None,
        "run":
            {},
        "fetches":
            0,
        "key_reads":
            0,
        "completion_attempts":
            0,
        "final_results":
            [],
    }

    arguments = [
        SimpleNamespace(
            resume=None
        ),
        SimpleNamespace(
            resume=extraction_id
        ),
    ]

    monkeypatch.setattr(
        script,
        "parse_arguments",
        lambda: arguments.pop(
            0
        ),
    )

    monkeypatch.setattr(
        script,
        "uuid4",
        lambda: SimpleNamespace(
            hex="finalgap"
        ),
    )

    def fake_get_massive_api_key():
        state[
            "key_reads"
        ] += 1

        return "test-key"

    monkeypatch.setattr(
        script,
        "get_massive_api_key",
        fake_get_massive_api_key,
    )

    def fake_start_run(
        **kwargs,
    ):
        state[
            "run"
        ].clear()

        state[
            "run"
        ].update(
            kwargs
        )

        state[
            "run"
        ][
            "status"
        ] = "started"

    monkeypatch.setattr(
        script,
        "start_run",
        fake_start_run,
    )

    def fake_fetch_json(
        **kwargs,
    ):
        del kwargs

        state[
            "fetches"
        ] += 1

        return {
            "results": [
                {
                    "ticker":
                        "A",
                }
            ],
        }

    monkeypatch.setattr(
        script,
        "fetch_json",
        fake_fetch_json,
    )

    monkeypatch.setattr(
        script,
        "validate_massive_url",
        lambda url: None,
    )

    monkeypatch.setattr(
        script,
        "validate_massive_payload",
        lambda payload: None,
    )

    monkeypatch.setattr(
        script,
        "sanitize_payload_for_storage",
        lambda payload: payload,
    )

    monkeypatch.setattr(
        script,
        "store_raw_payload_chunks",
        lambda **kwargs: [
            "raw-1",
        ],
    )

    monkeypatch.setattr(
        script,
        "register_canonical_page",
        lambda **kwargs: {
            "canonical_content_hash":
                kwargs[
                    "content_hash"
                ],
            "canonical_document_ids":
                kwargs[
                    "document_ids"
                ],
        },
    )

    def fake_save_checkpoint(
        **kwargs,
    ):
        state[
            "checkpoint"
        ] = deepcopy(
            kwargs
        )

    monkeypatch.setattr(
        script,
        "save_checkpoint",
        fake_save_checkpoint,
    )

    monkeypatch.setattr(
        script,
        "load_existing_progress",
        lambda extraction_id,
        record_through_page=None: (
            1,
            1,
            1,
        ),
    )

    def fake_complete_run(
        **kwargs,
    ):
        state[
            "completion_attempts"
        ] += 1

        if (
            state[
                "completion_attempts"
            ]
            == 1
        ):
            raise RuntimeError(
                "simulated final "
                "run-write interruption"
            )

        state[
            "run"
        ].update(
            kwargs
        )

        state[
            "run"
        ][
            "status"
        ] = "completed"

    monkeypatch.setattr(
        script,
        "complete_run",
        fake_complete_run,
    )

    def fake_fail_run(
        **kwargs,
    ):
        state[
            "run"
        ].update(
            kwargs
        )

        state[
            "run"
        ][
            "status"
        ] = "failed"

    monkeypatch.setattr(
        script,
        "fail_run",
        fake_fail_run,
    )

    monkeypatch.setattr(
        script,
        "get_checkpoint",
        lambda **kwargs: (
            state[
                "checkpoint"
            ]
        ),
    )

    monkeypatch.setattr(
        script,
        "get_run",
        lambda current_id: (
            state[
                "run"
            ]
            if current_id
            == extraction_id
            else None
        ),
    )

    monkeypatch.setattr(
        script,
        "reconcile_equivalent_raw_captures",
        lambda current_id: 0,
    )

    monkeypatch.setattr(
        script,
        "verify_extraction",
        lambda current_id: (
            _verification(
                state[
                    "run"
                ]
            )
        ),
    )

    def fake_print_final_result(
        **kwargs,
    ):
        state[
            "final_results"
        ].append(
            kwargs
        )

    monkeypatch.setattr(
        script,
        "print_final_result",
        fake_print_final_result,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "simulated final "
            "run-write interruption"
        ),
    ):
        script.main()

    assert (
        state[
            "checkpoint"
        ][
            "metadata"
        ][
            "completed"
        ]
        is True
    )

    assert (
        state[
            "run"
        ][
            "status"
        ]
        == "failed"
    )

    assert state[
        "fetches"
    ] == 1

    script.main()

    assert (
        state[
            "run"
        ][
            "status"
        ]
        == "completed"
    )

    assert (
        state[
            "completion_attempts"
        ]
        == 2
    )

    assert state[
        "fetches"
    ] == 1

    assert state[
        "key_reads"
    ] == 1

    assert state[
        "final_results"
    ] == [
        {
            "extraction_id":
                extraction_id,
            "pages_stored":
                1,
            "total_results":
                1,
            "total_raw_documents":
                1,
        }
    ]


def test_completed_checkpoint_corruption_blocks_recovery(
    monkeypatch,
):
    """Corrupt final evidence must remain failed."""
    extraction_id = (
        "real_ticker_pagination_corrupt"
    )

    checkpoint = {
        "source":
            script.SOURCE,
        "endpoint":
            script.ENDPOINT,
        "extraction_id":
            extraction_id,
        "cursor":
            None,
        "metadata": {
            "completed":
                True,
            "last_page":
                1,
        },
    }

    run = {
        "extraction_id":
            extraction_id,
        "source":
            script.SOURCE,
        "endpoint":
            script.ENDPOINT,
        "parameters":
            script.PARAMETERS,
        "status":
            "failed",
    }

    completion_calls = []

    monkeypatch.setattr(
        script,
        "get_checkpoint",
        lambda **kwargs: checkpoint,
    )

    monkeypatch.setattr(
        script,
        "get_run",
        lambda current_id: run,
    )

    monkeypatch.setattr(
        script,
        "reconcile_equivalent_raw_captures",
        lambda current_id: 0,
    )

    monkeypatch.setattr(
        script,
        "verify_extraction",
        lambda current_id: {
            "verified":
                False,
            "verification_errors": [
                "execution_not_completed",
                "page_1_content_conflict",
            ],
            "ledger_page_numbers": [
                1,
            ],
            "canonical_page_numbers": [
                1,
            ],
            "total_results":
                1,
        },
    )

    monkeypatch.setattr(
        script,
        "complete_run",
        lambda **kwargs: (
            completion_calls.append(
                kwargs
            )
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint evidence "
            "failed recovery verification"
        ),
    ):
        script.prepare_resume(
            extraction_id
        )

    assert completion_calls == []
    assert run[
        "status"
    ] == "failed"

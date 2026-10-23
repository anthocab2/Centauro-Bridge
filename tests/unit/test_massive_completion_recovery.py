"""Tests for recovery after interrupted Massive completion."""

import pytest

from centauro_atlas_bridge.sources import massive

TICKER = "AAPL"
START_DATE = "2026-08-03"
END_DATE = "2026-08-07"
ADJUSTED = True


def expected_identity():
    """Return the deterministic request identity used by recovery."""
    extraction_id = (
        massive.build_extraction_id(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )
    )

    endpoint = (
        f"/v2/aggs/ticker/{TICKER}/range/1/day/"
        f"{START_DATE}/{END_DATE}"
    )

    parameters = {
        "ticker": TICKER,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "adjusted": ADJUSTED,
        "sort": "asc",
        "limit": 50000,
    }

    return (
        extraction_id,
        endpoint,
        parameters,
    )


def install_completed_checkpoint(
    monkeypatch,
    last_page=1,
):
    """Install one completed checkpoint."""
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
                "last_page": last_page,
            },
        },
    )


def build_run(
    extraction_id,
    endpoint,
    parameters,
    status,
    pages_stored=None,
):
    """Build one realistic persisted Massive run."""
    run = {
        "extraction_id":
            extraction_id,
        "source":
            massive.SOURCE_NAME,
        "endpoint":
            endpoint,
        "parameters":
            parameters,
        "status":
            status,
    }

    if pages_stored is not None:
        run[
            "pages_stored"
        ] = pages_stored

    return run


def recovery_verification(
    page_numbers=None,
):
    """Build valid evidence for an incomplete run."""
    if page_numbers is None:
        page_numbers = [
            1
        ]

    return {
        "verified": False,
        "verification_errors": [
            "execution_not_completed",
        ],
        "ledger_page_numbers":
            page_numbers,
        "canonical_page_numbers":
            page_numbers,
    }


def completed_verification(
    page_numbers=None,
):
    """Build valid evidence for a completed run."""
    if page_numbers is None:
        page_numbers = [
            1
        ]

    return {
        "verified": True,
        "verification_errors": [],
        "ledger_page_numbers":
            page_numbers,
        "canonical_page_numbers":
            page_numbers,
    }


def test_failed_run_recovers_after_evidence_verification(
    monkeypatch,
):
    """A failed final transition must recover from intact evidence."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="failed",
        ),
    )

    verification_calls = {
        "count": 0,
    }

    def fake_verify_extraction(
        current_id,
    ):
        assert current_id == extraction_id

        verification_calls[
            "count"
        ] += 1

        if (
            verification_calls[
                "count"
            ]
            == 1
        ):
            return recovery_verification()

        return completed_verification()

    completed = {}

    def fake_complete_run(
        **kwargs,
    ):
        completed.update(
            kwargs
        )

        return {
            "status": "completed",
        }

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        fake_verify_extraction,
    )

    monkeypatch.setattr(
        massive,
        "complete_run",
        fake_complete_run,
    )

    monkeypatch.setattr(
        massive,
        "fetch_json",
        lambda **kwargs: pytest.fail(
            "Recovery must not fetch Massive again"
        ),
    )

    result = (
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )
    )

    assert result == []

    assert (
        verification_calls[
            "count"
        ]
        == 2
    )

    assert completed == {
        "extraction_id":
            extraction_id,
        "pages_stored":
            1,
    }


def test_started_run_can_recover_completed_checkpoint(
    monkeypatch,
):
    """A crash leaving started state must also be recoverable."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="started",
        ),
    )

    responses = iter(
        [
            recovery_verification(),
            completed_verification(),
        ]
    )

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        lambda current_id: next(
            responses
        ),
    )

    completed = {}

    monkeypatch.setattr(
        massive,
        "complete_run",
        lambda **kwargs: completed.update(
            kwargs
        ),
    )

    result = (
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )
    )

    assert result == []

    assert completed[
        "pages_stored"
    ] == 1


def test_corrupt_evidence_blocks_recovery(
    monkeypatch,
):
    """Recovery must refuse reconciliation when evidence is corrupt."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="failed",
        ),
    )

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        lambda current_id: {
            "verified": False,
            "verification_errors": [
                "execution_not_completed",
                "page_1_content_hash_mismatch",
            ],
            "ledger_page_numbers": [
                1
            ],
            "canonical_page_numbers": [
                1
            ],
        },
    )

    completed = {
        "called": False,
    }

    def fake_complete_run(
        **kwargs,
    ):
        completed[
            "called"
        ] = True

    monkeypatch.setattr(
        massive,
        "complete_run",
        fake_complete_run,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint evidence "
            "failed recovery verification"
        ),
    ):
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )

    assert (
        completed[
            "called"
        ]
        is False
    )


def test_completed_run_is_reverified(
    monkeypatch,
):
    """A completed checkpoint and run must still pass integrity checks."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="completed",
            pages_stored=1,
        ),
    )

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        lambda current_id: (
            completed_verification()
        ),
    )

    result = (
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )
    )

    assert result == []


def test_completed_run_with_invalid_evidence_is_rejected(
    monkeypatch,
):
    """A completed status cannot override failed integrity checks."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="completed",
            pages_stored=1,
        ),
    )

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        lambda current_id: {
            "verified": False,
            "verification_errors": [
                "page_1_missing",
            ],
            "ledger_page_numbers": [
                1
            ],
            "canonical_page_numbers": [],
        },
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed extraction failed "
            "integrity verification"
        ),
    ):
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )


def test_incomplete_run_without_identity_is_still_rejected(
    monkeypatch,
):
    """Recovery must not trust an incomplete run without request identity."""
    install_completed_checkpoint(
        monkeypatch
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: {
            "status": "failed",
        },
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint conflicts "
            "with run identity"
        ),
    ):
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )


def test_failed_run_rejects_checkpoint_page_count_mismatch(
    monkeypatch,
):
    """Recovery must reject a checkpoint claiming an extra page."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch,
        last_page=2,
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="failed",
        ),
    )

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        lambda current_id: (
            recovery_verification(
                page_numbers=[
                    1
                ]
            )
        ),
    )

    completed = {
        "called": False,
    }

    def fake_complete_run(
        **kwargs,
    ):
        completed[
            "called"
        ] = True

    monkeypatch.setattr(
        massive,
        "complete_run",
        fake_complete_run,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint page count "
            "conflicts with verified evidence"
        ),
    ):
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )

    assert (
        completed[
            "called"
        ]
        is False
    )


def test_completed_run_rejects_checkpoint_page_count_mismatch(
    monkeypatch,
):
    """Completed run count must agree with the completed checkpoint."""
    (
        extraction_id,
        endpoint,
        parameters,
    ) = expected_identity()

    install_completed_checkpoint(
        monkeypatch,
        last_page=2,
    )

    monkeypatch.setattr(
        massive,
        "get_run",
        lambda current_id: build_run(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            status="completed",
            pages_stored=1,
        ),
    )

    monkeypatch.setattr(
        massive,
        "verify_extraction",
        lambda current_id: pytest.fail(
            "Run/checkpoint mismatch must fail before verification"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Completed checkpoint page count "
            "conflicts with run state"
        ),
    ):
        massive.extract_daily_aggs(
            ticker=TICKER,
            start_date=START_DATE,
            end_date=END_DATE,
            adjusted=ADJUSTED,
        )

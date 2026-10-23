"""Tests for cross-layer ingestion provenance verification."""

from copy import deepcopy

from centauro_atlas_bridge.ingestion import verification
from tests.unit.test_verification import (
    ENDPOINT,
    PARAMETERS,
    SOURCE,
    build_page_fixture,
    install_fake_environment,
)


def build_complete_run(
    extraction_id: str,
) -> dict:
    """Build a complete run with persisted request identity."""
    return {
        "extraction_id":
            extraction_id,
        "source":
            SOURCE,
        "endpoint":
            ENDPOINT,
        "parameters":
            deepcopy(
                PARAMETERS
            ),
        "status":
            "completed",
        "pages_stored":
            1,
    }


def test_matching_run_ledger_and_raw_are_verified(
    monkeypatch,
):
    """Matching request provenance must remain valid."""
    extraction_id = (
        "provenance_valid"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [
                {
                    "close": 100,
                }
            ]
        ],
    )

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_complete_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is True
    )

    assert (
        result[
            "verification_errors"
        ]
        == []
    )


def test_run_parameter_mismatch_is_invalid(
    monkeypatch,
):
    """Changing the requested ticker must invalidate stored evidence."""
    extraction_id = (
        "provenance_run_parameters"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [
                {
                    "close": 100,
                }
            ]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    run[
        "parameters"
    ][
        "ticker"
    ] = "MSFT"

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "page_1_raw_parameters_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_ledger_endpoint_mismatch_is_invalid(
    monkeypatch,
):
    """Changing the canonical ledger endpoint must be detected."""
    extraction_id = (
        "provenance_ledger_endpoint"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [
                {
                    "close": 100,
                }
            ]
        ],
    )

    ledger[
        "endpoint"
    ] = "/tampered"

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=build_complete_run(
            extraction_id
        ),
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "page_1_ledger_endpoint_mismatch"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_raw_ledger_endpoint_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_run_source_mismatch_is_invalid(
    monkeypatch,
):
    """Changing the source registered by the run must be detected."""
    extraction_id = (
        "provenance_run_source"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    run[
        "source"
    ] = "other_provider"

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "page_1_ledger_source_mismatch"
        in result[
            "verification_errors"
        ]
    )

    assert (
        "page_1_raw_source_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_run_extraction_id_mismatch_is_invalid(
    monkeypatch,
):
    """Changing the run extraction identity must invalidate verification."""
    extraction_id = (
        "provenance_extraction_id"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    run[
        "extraction_id"
    ] = "different_extraction"

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "run_extraction_id_mismatch"
        in result[
            "verification_errors"
        ]
    )


def test_missing_run_source_is_invalid(
    monkeypatch,
):
    """A run without source must never verify."""
    extraction_id = (
        "provenance_missing_source"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    del run[
        "source"
    ]

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "missing_run_source"
        in result[
            "verification_errors"
        ]
    )


def test_missing_run_endpoint_is_invalid(
    monkeypatch,
):
    """A run without endpoint must never verify."""
    extraction_id = (
        "provenance_missing_endpoint"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    del run[
        "endpoint"
    ]

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "missing_run_endpoint"
        in result[
            "verification_errors"
        ]
    )


def test_missing_run_parameters_is_invalid(
    monkeypatch,
):
    """A run without parameters must never verify."""
    extraction_id = (
        "provenance_missing_parameters"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    del run[
        "parameters"
    ]

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "missing_run_parameters"
        in result[
            "verification_errors"
        ]
    )


def test_missing_run_extraction_id_is_invalid(
    monkeypatch,
):
    """A run without extraction identity must never verify."""
    extraction_id = (
        "provenance_missing_extraction_id"
    )

    (
        raw_documents,
        ledger,
    ) = build_page_fixture(
        extraction_id=extraction_id,
        page_number=1,
        chunk_results=[
            [1]
        ],
    )

    run = build_complete_run(
        extraction_id
    )

    del run[
        "extraction_id"
    ]

    install_fake_environment(
        monkeypatch,
        raw_documents=raw_documents,
        ledger_documents=[
            ledger
        ],
        run=run,
    )

    result = (
        verification.verify_extraction(
            extraction_id
        )
    )

    assert (
        result["verified"]
        is False
    )

    assert (
        "missing_run_extraction_id"
        in result[
            "verification_errors"
        ]
    )

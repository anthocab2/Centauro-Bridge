"""End-to-end recovery test for Massive ingestion through Atlas."""

from contextlib import suppress
from uuid import uuid4

import pytest
from pymongo.errors import ConnectionFailure, PyMongoError

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.checkpoints import (
    CHECKPOINTS_COLLECTION,
    get_checkpoint,
)
from centauro_atlas_bridge.ingestion.page_ledger import (
    PAGE_LEDGER_COLLECTION,
)
from centauro_atlas_bridge.ingestion.raw import RAW_COLLECTION
from centauro_atlas_bridge.ingestion.runs import (
    INGESTION_RUNS_COLLECTION,
    get_run,
)
from centauro_atlas_bridge.ingestion.verification import verify_extraction
from centauro_atlas_bridge.sources import massive


def cleanup_extraction(
    database,
    extraction_id: str,
) -> None:
    """Remove test evidence without masking an earlier test failure."""
    cleanup_targets = [
        (
            RAW_COLLECTION,
            {
                "pagination.extraction_id": extraction_id,
            },
        ),
        (
            PAGE_LEDGER_COLLECTION,
            {
                "extraction_id": extraction_id,
            },
        ),
        (
            CHECKPOINTS_COLLECTION,
            {
                "extraction_id": extraction_id,
            },
        ),
        (
            INGESTION_RUNS_COLLECTION,
            {
                "extraction_id": extraction_id,
            },
        ),
    ]

    for collection_name, query in cleanup_targets:
        with suppress(PyMongoError):
            database[
                collection_name
            ].delete_many(
                query
            )


def require_atlas(
    client,
) -> None:
    """Skip this external integration test when Atlas is unavailable."""
    try:
        client.admin.command(
            "ping"
        )

    except ConnectionFailure as exc:
        pytest.skip(
            "MongoDB Atlas integration dependency "
            f"is unavailable: {type(exc).__name__}"
        )


def test_massive_extraction_recovers_after_interruption(
    monkeypatch,
):
    """Store page one, fail, resume page two, and verify integrity."""
    unique_suffix = uuid4().hex[:12]

    ticker = (
        f"RECOVERY{unique_suffix}"
    )

    start_date = "2026-01-01"
    end_date = "2026-01-02"
    adjusted = True

    extraction_id = (
        massive.build_extraction_id(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            adjusted=adjusted,
        )
    )

    endpoint = (
        f"/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start_date}/{end_date}"
    )

    second_page_url = (
        "https://api.massive.com/"
        "v2/test-recovery"
        "?cursor=page2"
    )

    first_page = {
        "status": "OK",
        "request_id": "request_page_1",
        "resultsCount": 1,
        "results": [
            {
                "t": 1,
                "o": 100.0,
                "h": 101.0,
                "l": 99.0,
                "c": 100.5,
                "v": 1000,
            }
        ],
        "next_url": second_page_url,
    }

    second_page = {
        "status": "OK",
        "request_id": "request_page_2",
        "resultsCount": 1,
        "results": [
            {
                "t": 2,
                "o": 101.0,
                "h": 102.0,
                "l": 100.0,
                "c": 101.5,
                "v": 1100,
            }
        ],
    }

    monkeypatch.setattr(
        massive,
        "get_massive_api_key",
        lambda: "integration-test-key",
    )

    first_attempt_calls = {
        "count": 0,
    }

    def first_attempt_fetch(
        url,
        parameters=None,
        headers=None,
        **kwargs,
    ):
        first_attempt_calls[
            "count"
        ] += 1

        if (
            first_attempt_calls[
                "count"
            ]
            == 1
        ):
            return first_page

        raise RuntimeError(
            "simulated network interruption"
        )

    client = create_atlas_client()
    database = None

    try:
        require_atlas(
            client
        )

        database = client[
            get_database_name()
        ]

        raw_collection = database[
            RAW_COLLECTION
        ]

        ledger_collection = database[
            PAGE_LEDGER_COLLECTION
        ]

        monkeypatch.setattr(
            massive,
            "fetch_json",
            first_attempt_fetch,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated network interruption",
        ):
            massive.extract_daily_aggs(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                adjusted=adjusted,
            )

        failed_run = get_run(
            extraction_id
        )

        assert failed_run is not None

        assert (
            failed_run[
                "status"
            ]
            == "failed"
        )

        checkpoint = get_checkpoint(
            source=massive.SOURCE_NAME,
            endpoint=endpoint,
            extraction_id=extraction_id,
        )

        assert checkpoint is not None

        assert (
            checkpoint[
                "metadata"
            ][
                "completed"
            ]
            is False
        )

        assert (
            checkpoint[
                "metadata"
            ][
                "last_page"
            ]
            == 1
        )

        assert (
            checkpoint[
                "cursor"
            ]
            == second_page_url
        )

        page_one_raw_count = (
            raw_collection.count_documents(
                {
                    "pagination.extraction_id":
                        extraction_id,
                    "pagination.page_number":
                        1,
                }
            )
        )

        assert (
            page_one_raw_count
            >= 1
        )

        page_one_ledger_count = (
            ledger_collection.count_documents(
                {
                    "extraction_id":
                        extraction_id,
                    "page_number":
                        1,
                }
            )
        )

        assert (
            page_one_ledger_count
            == 1
        )

        resume_calls = []

        def resume_fetch(
            url,
            parameters=None,
            headers=None,
            **kwargs,
        ):
            resume_calls.append(
                {
                    "url": url,
                    "parameters": parameters,
                    "headers": headers,
                }
            )

            assert (
                url
                == second_page_url
            )

            return second_page

        monkeypatch.setattr(
            massive,
            "fetch_json",
            resume_fetch,
        )

        resumed_ids = (
            massive.extract_daily_aggs(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                adjusted=adjusted,
            )
        )

        assert resumed_ids

        assert (
            len(
                resume_calls
            )
            == 1
        )

        assert (
            resume_calls[
                0
            ][
                "parameters"
            ]
            is None
        )

        completed_run = get_run(
            extraction_id
        )

        assert completed_run is not None

        assert (
            completed_run[
                "status"
            ]
            == "completed"
        )

        assert (
            completed_run[
                "pages_stored"
            ]
            == 2
        )

        assert (
            completed_run[
                "verification_status"
            ]
            == "not_verified"
        )

        completed_checkpoint = (
            get_checkpoint(
                source=massive.SOURCE_NAME,
                endpoint=endpoint,
                extraction_id=extraction_id,
            )
        )

        assert (
            completed_checkpoint
            is not None
        )

        assert (
            completed_checkpoint[
                "metadata"
            ][
                "completed"
            ]
            is True
        )

        assert (
            completed_checkpoint[
                "metadata"
            ][
                "last_page"
            ]
            == 2
        )

        page_two_raw_count = (
            raw_collection.count_documents(
                {
                    "pagination.extraction_id":
                        extraction_id,
                    "pagination.page_number":
                        2,
                }
            )
        )

        assert (
            page_two_raw_count
            >= 1
        )

        page_two_ledger_count = (
            ledger_collection.count_documents(
                {
                    "extraction_id":
                        extraction_id,
                    "page_number":
                        2,
                }
            )
        )

        assert (
            page_two_ledger_count
            == 1
        )

        total_ledger_pages = (
            ledger_collection.count_documents(
                {
                    "extraction_id":
                        extraction_id,
                }
            )
        )

        assert (
            total_ledger_pages
            == 2
        )

        verification = (
            verify_extraction(
                extraction_id
            )
        )

        assert (
            verification[
                "execution_completed"
            ]
            is True
        )

        assert (
            verification[
                "execution_status"
            ]
            == "completed"
        )

        assert (
            verification[
                "verified"
            ]
            is True
        )

        assert (
            verification[
                "verification_status"
            ]
            == "verified"
        )

        assert (
            verification[
                "verification_errors"
            ]
            == []
        )

        assert (
            verification[
                "expected_pages"
            ]
            == 2
        )

        assert (
            verification[
                "observed_pages"
            ]
            == 2
        )

        assert (
            verification[
                "total_results"
            ]
            == 2
        )

        assert (
            verification[
                "duplicate_ingestion_keys"
            ]
            == 0
        )

        assert (
            verification[
                "unregistered_raw_documents"
            ]
            == 0
        )

        documents_before_repeat = (
            raw_collection.count_documents(
                {
                    "pagination.extraction_id":
                        extraction_id,
                }
            )
        )

        repeat_result = (
            massive.extract_daily_aggs(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                adjusted=adjusted,
            )
        )

        documents_after_repeat = (
            raw_collection.count_documents(
                {
                    "pagination.extraction_id":
                        extraction_id,
                }
            )
        )

        assert (
            repeat_result
            == []
        )

        assert (
            documents_after_repeat
            == documents_before_repeat
        )

    finally:
        if database is not None:
            cleanup_extraction(
                database,
                extraction_id,
            )

        client.close()

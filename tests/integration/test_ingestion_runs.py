"""Integration tests for ingestion run and verification state."""

from uuid import uuid4

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.runs import (
    INGESTION_RUNS_COLLECTION,
    complete_run,
    get_run,
    set_verification_result,
    start_run,
)


def test_ingestion_run_separates_completion_from_verification():
    """Completed transport must remain unverified until checked."""
    extraction_id = (
        f"test_{uuid4()}"
    )

    try:
        started = start_run(
            extraction_id=extraction_id,
            source="test_source",
            endpoint="/test",
            parameters={
                "limit": 100,
            },
        )

        assert (
            started["status"]
            == "started"
        )

        assert (
            started[
                "verification_status"
            ]
            == "not_verified"
        )

        completed = complete_run(
            extraction_id=extraction_id,
            pages_stored=10,
        )

        assert completed is not None

        assert (
            completed["status"]
            == "completed"
        )

        assert (
            completed[
                "pages_stored"
            ]
            == 10
        )

        assert (
            completed[
                "verification_status"
            ]
            == "not_verified"
        )

        verified = (
            set_verification_result(
                extraction_id=extraction_id,
                verified=True,
                errors=[],
            )
        )

        assert verified is not None

        assert (
            verified[
                "verification_status"
            ]
            == "verified"
        )

        stored = get_run(
            extraction_id
        )

        assert stored is not None

        assert (
            stored["status"]
            == "completed"
        )

        assert (
            stored[
                "verification_status"
            ]
            == "verified"
        )

    finally:
        client = (
            create_atlas_client()
        )

        try:
            database = client[
                get_database_name()
            ]

            database[
                INGESTION_RUNS_COLLECTION
            ].delete_one(
                {
                    "extraction_id":
                        extraction_id,
                }
            )

        finally:
            client.close()

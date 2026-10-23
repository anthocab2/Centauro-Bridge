"""Real Massive multi-page ingestion validation through Atlas."""

import argparse
from contextlib import suppress
from typing import Any
from uuid import uuid4

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import (
    get_database_name,
    get_massive_api_key,
)
from centauro_atlas_bridge.ingestion.checkpoints import (
    get_checkpoint,
    save_checkpoint,
)
from centauro_atlas_bridge.ingestion.http_client import fetch_json
from centauro_atlas_bridge.ingestion.page_ledger import (
    PAGE_LEDGER_COLLECTION,
    calculate_page_content_hash,
    register_canonical_page,
)
from centauro_atlas_bridge.ingestion.raw import (
    RAW_COLLECTION,
    calculate_payload_hash,
    store_raw_payload_chunks,
)
from centauro_atlas_bridge.ingestion.recovery import (
    reconcile_equivalent_raw_captures,
    validate_resume_frontier,
)
from centauro_atlas_bridge.ingestion.runs import (
    complete_run,
    fail_run,
    get_run,
    start_run,
)
from centauro_atlas_bridge.ingestion.verification import (
    verify_extraction,
)
from centauro_atlas_bridge.sources.massive import (
    sanitize_payload_for_storage,
    validate_massive_payload,
    validate_massive_url,
)

SOURCE = "massive"
ENDPOINT = "/v3/reference/tickers"
BASE_URL = f"https://api.massive.com{ENDPOINT}"

PARAMETERS = {
    "market": "stocks",
    "active": "true",
    "order": "asc",
    "limit": 1000,
    "sort": "ticker",
}


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate real Massive pagination "
            "through MongoDB Atlas."
        )
    )

    parser.add_argument(
        "--resume",
        metavar="EXTRACTION_ID",
        help=(
            "Resume or reconcile an existing "
            "Massive ticker extraction."
        ),
    )

    return parser.parse_args()


def load_existing_progress(
    extraction_id: str,
    record_through_page: int | None = None,
) -> tuple[int, int, int]:
    """Return existing page, record, and raw-document counts."""
    client = create_atlas_client()

    try:
        database = client[
            get_database_name()
        ]

        ledger_documents = list(
            database[
                PAGE_LEDGER_COLLECTION
            ].find(
                {
                    "extraction_id":
                        extraction_id,
                },
                {
                    "_id": 0,
                    "page_number": 1,
                    "canonical_record_count": 1,
                },
            ).sort(
                "page_number",
                1,
            )
        )

        page_numbers = [
            document.get(
                "page_number"
            )
            for document in ledger_documents
        ]

        expected_page_numbers = list(
            range(
                1,
                len(ledger_documents) + 1,
            )
        )

        if (
            page_numbers
            != expected_page_numbers
        ):
            raise RuntimeError(
                "Existing page ledger is not contiguous"
            )

        total_records = sum(
            document.get(
                "canonical_record_count",
                0,
            )
            for document in ledger_documents
            if (
                record_through_page
                is None
                or document.get(
                    "page_number"
                )
                <= record_through_page
            )
        )

        raw_documents = database[
            RAW_COLLECTION
        ].count_documents(
            {
                "pagination.extraction_id":
                    extraction_id,
            }
        )

        return (
            len(
                ledger_documents
            ),
            total_records,
            raw_documents,
        )

    finally:
        client.close()


def _run_identity_matches(
    run: dict[str, Any],
    extraction_id: str,
) -> bool:
    """Return whether a run belongs to this exact extraction."""
    return (
        run.get(
            "extraction_id"
        )
        == extraction_id
        and run.get(
            "source"
        )
        == SOURCE
        and run.get(
            "endpoint"
        )
        == ENDPOINT
        and run.get(
            "parameters"
        )
        == PARAMETERS
    )


def _verification_matches_checkpoint(
    verification: dict[str, Any],
    last_page: int,
) -> bool:
    """Return whether verified page evidence matches checkpoint."""
    expected_pages = list(
        range(
            1,
            last_page + 1,
        )
    )

    return (
        verification.get(
            "ledger_page_numbers"
        )
        == expected_pages
        and verification.get(
            "canonical_page_numbers"
        )
        == expected_pages
    )


def recover_completed_checkpoint(
    extraction_id: str,
    metadata: dict[str, Any],
) -> tuple[
    int,
    int,
    int,
    int,
]:
    """Recover a completed checkpoint whose run may be incomplete."""
    last_page = metadata.get(
        "last_page"
    )

    if (
        not isinstance(
            last_page,
            int,
        )
        or isinstance(
            last_page,
            bool,
        )
        or last_page < 1
    ):
        raise RuntimeError(
            "Completed checkpoint has invalid last_page"
        )

    run = get_run(
        extraction_id
    )

    if run is None:
        raise RuntimeError(
            "Completed checkpoint exists without run state"
        )

    if not _run_identity_matches(
        run=run,
        extraction_id=extraction_id,
    ):
        raise RuntimeError(
            "Completed checkpoint conflicts with run identity"
        )

    reconciled_captures = (
        reconcile_equivalent_raw_captures(
            extraction_id
        )
    )

    status = run.get(
        "status"
    )

    if status == "completed":
        pages_stored = run.get(
            "pages_stored"
        )

        if (
            not isinstance(
                pages_stored,
                int,
            )
            or isinstance(
                pages_stored,
                bool,
            )
            or pages_stored != last_page
        ):
            raise RuntimeError(
                "Completed checkpoint page count "
                "conflicts with run state"
            )

        final_verification = (
            verify_extraction(
                extraction_id
            )
        )

        if (
            final_verification.get(
                "verified"
            )
            is not True
        ):
            raise RuntimeError(
                "Completed extraction failed "
                "integrity verification"
            )

    elif status in {
        "started",
        "failed",
    }:
        recovery_verification = (
            verify_extraction(
                extraction_id
            )
        )

        recovery_errors = set(
            recovery_verification.get(
                "verification_errors",
                [],
            )
        )

        if recovery_errors != {
            "execution_not_completed"
        }:
            raise RuntimeError(
                "Completed checkpoint evidence "
                "failed recovery verification"
            )

        if not _verification_matches_checkpoint(
            verification=(
                recovery_verification
            ),
            last_page=last_page,
        ):
            raise RuntimeError(
                "Completed checkpoint page count "
                "conflicts with verified evidence"
            )

        complete_run(
            extraction_id=extraction_id,
            pages_stored=last_page,
        )

        final_verification = (
            verify_extraction(
                extraction_id
            )
        )

        if (
            final_verification.get(
                "verified"
            )
            is not True
        ):
            raise RuntimeError(
                "Recovered extraction failed "
                "final integrity verification"
            )

    else:
        raise RuntimeError(
            "Completed checkpoint has unsupported run state"
        )

    if not _verification_matches_checkpoint(
        verification=final_verification,
        last_page=last_page,
    ):
        raise RuntimeError(
            "Recovered extraction page count "
            "conflicts with verified evidence"
        )

    (
        ledger_pages,
        total_records,
        raw_documents,
    ) = load_existing_progress(
        extraction_id
    )

    if ledger_pages != last_page:
        raise RuntimeError(
            "Recovered ledger page count "
            "does not match checkpoint"
        )

    if (
        final_verification.get(
            "total_results"
        )
        != total_records
    ):
        raise RuntimeError(
            "Recovered record count "
            "does not match verified evidence"
        )

    return (
        last_page,
        total_records,
        raw_documents,
        reconciled_captures,
    )


def prepare_resume(
    extraction_id: str,
) -> tuple[
    str | None,
    int,
    int,
    int,
    str,
    int,
]:
    """Validate and prepare an extraction for safe recovery."""
    checkpoint = get_checkpoint(
        source=SOURCE,
        endpoint=ENDPOINT,
        extraction_id=extraction_id,
    )

    if checkpoint is None:
        raise RuntimeError(
            "No checkpoint exists for this extraction"
        )

    metadata = checkpoint.get(
        "metadata",
        {},
    )

    if not isinstance(
        metadata,
        dict,
    ):
        raise TypeError(
            "Checkpoint metadata is invalid"
        )

    if (
        metadata.get(
            "completed"
        )
        is True
    ):
        (
            last_page,
            total_records,
            raw_documents,
            reconciled_captures,
        ) = recover_completed_checkpoint(
            extraction_id=extraction_id,
            metadata=metadata,
        )

        return (
            None,
            last_page,
            total_records,
            raw_documents,
            "completed_recovered",
            reconciled_captures,
        )

    last_page = metadata.get(
        "last_page"
    )

    if (
        not isinstance(
            last_page,
            int,
        )
        or isinstance(
            last_page,
            bool,
        )
        or last_page < 1
    ):
        raise RuntimeError(
            "Checkpoint last_page is invalid"
        )

    cursor = checkpoint.get(
        "cursor"
    )

    if (
        not isinstance(
            cursor,
            str,
        )
        or not cursor
    ):
        raise RuntimeError(
            "Checkpoint does not contain a resumable cursor"
        )

    validate_massive_url(
        cursor
    )

    reconciled_captures = (
        reconcile_equivalent_raw_captures(
            extraction_id
        )
    )

    verification = verify_extraction(
        extraction_id
    )

    resume_mode = validate_resume_frontier(
        verification=verification,
        last_page=last_page,
    )

    (
        ledger_pages,
        total_records,
        raw_documents,
    ) = load_existing_progress(
        extraction_id=extraction_id,
        record_through_page=last_page,
    )

    if (
        resume_mode == "aligned"
        and ledger_pages != last_page
    ):
        raise RuntimeError(
            "Aligned resume page count is inconsistent"
        )

    if (
        resume_mode == "replay_required"
        and ledger_pages
        != last_page + 1
    ):
        raise RuntimeError(
            "Replay resume page count is inconsistent"
        )

    return (
        cursor,
        last_page,
        total_records,
        raw_documents,
        resume_mode,
        reconciled_captures,
    )


def print_final_result(
    extraction_id: str,
    pages_stored: int,
    total_results: int,
    total_raw_documents: int,
) -> None:
    """Verify and print the final extraction result."""
    verification = verify_extraction(
        extraction_id
    )

    print()
    print("FINAL RESULT")

    print(
        "extraction_id:",
        extraction_id,
    )

    print(
        "pages_stored:",
        pages_stored,
    )

    print(
        "records_received:",
        total_results,
    )

    print(
        "raw_documents:",
        total_raw_documents,
    )

    print(
        "verified:",
        verification[
            "verified"
        ],
    )

    print(
        "verification_status:",
        verification[
            "verification_status"
        ],
    )

    print(
        "verification_errors:",
        verification[
            "verification_errors"
        ],
    )

    print(
        "verified_total_results:",
        verification[
            "total_results"
        ],
    )

    print(
        "expected_pages:",
        verification[
            "expected_pages"
        ],
    )

    print(
        "observed_pages:",
        verification[
            "observed_pages"
        ],
    )

    print(
        "duplicate_ingestion_keys:",
        verification[
            "duplicate_ingestion_keys"
        ],
    )

    print(
        "noncanonical_raw_documents:",
        verification[
            "noncanonical_raw_documents"
        ],
    )

    print(
        "unregistered_raw_documents:",
        verification[
            "unregistered_raw_documents"
        ],
    )

    print(
        "alternate_payload_variants:",
        verification[
            "alternate_payload_variants"
        ],
    )

    if (
        verification[
            "verified"
        ]
        is not True
    ):
        raise RuntimeError(
            "Real Massive pagination verification failed"
        )

    if (
        verification[
            "total_results"
        ]
        != total_results
    ):
        raise RuntimeError(
            "Stored record count does not match "
            "received record count"
        )

    if (
        verification[
            "expected_pages"
        ]
        != pages_stored
    ):
        raise RuntimeError(
            "Expected page count does not match stored pages"
        )

    if (
        verification[
            "observed_pages"
        ]
        != pages_stored
    ):
        raise RuntimeError(
            "Observed page count does not match stored pages"
        )

    print()
    print("RESULT: PASS")


def main() -> None:
    """Run or resume real Massive pagination validation."""
    arguments = parse_arguments()

    request_parameters: (
        dict[str, Any] | None
    )

    if arguments.resume:
        extraction_id = (
            arguments.resume
        )

        (
            url,
            last_page,
            total_results,
            total_raw_documents,
            resume_mode,
            reconciled_captures,
        ) = prepare_resume(
            extraction_id
        )

        print(
            "Resuming extraction:",
            extraction_id,
        )

        print(
            "checkpoint_page:",
            last_page,
        )

        print(
            "resume_mode:",
            resume_mode,
        )

        print(
            "reconciled_raw_captures:",
            reconciled_captures,
        )

        print(
            "records_before_resume:",
            total_results,
        )

        if (
            resume_mode
            == "completed_recovered"
        ):
            print(
                "Recovery action: verified and "
                "finalized completed checkpoint."
            )

            print_final_result(
                extraction_id=extraction_id,
                pages_stored=last_page,
                total_results=total_results,
                total_raw_documents=(
                    total_raw_documents
                ),
            )

            return

        if url is None:
            raise RuntimeError(
                "Resume mode requires a valid cursor"
            )

        page_number = (
            last_page + 1
        )

        request_parameters = None

        print(
            "replay_or_next_page:",
            page_number,
        )

        if (
            resume_mode
            == "replay_required"
        ):
            print(
                "Recovery action: replaying "
                "the page already present "
                "ahead of the checkpoint."
            )

    else:
        extraction_id = (
            "real_ticker_pagination_"
            f"{uuid4().hex}"
        )

        url = BASE_URL

        request_parameters = (
            PARAMETERS.copy()
        )

        page_number = 1
        total_results = 0
        total_raw_documents = 0

        print(
            "Starting extraction:",
            extraction_id,
        )

    headers = {
        "Authorization": (
            f"Bearer {get_massive_api_key()}"
        ),
    }

    start_run(
        extraction_id=extraction_id,
        source=SOURCE,
        endpoint=ENDPOINT,
        parameters=PARAMETERS,
    )

    try:
        while url:
            validate_massive_url(
                url
            )

            payload = fetch_json(
                url=url,
                parameters=request_parameters,
                headers=headers,
            )

            validate_massive_payload(
                payload
            )

            storage_payload = (
                sanitize_payload_for_storage(
                    payload
                )
            )

            results = storage_payload[
                "results"
            ]

            next_url = (
                storage_payload.get(
                    "next_url"
                )
            )

            if next_url is not None:
                validate_massive_url(
                    next_url
                )

            payload_hash = (
                calculate_payload_hash(
                    storage_payload
                )
            )

            content_hash = (
                calculate_page_content_hash(
                    storage_payload
                )
            )

            document_ids = (
                store_raw_payload_chunks(
                    source=SOURCE,
                    endpoint=ENDPOINT,
                    parameters=PARAMETERS,
                    payload=storage_payload,
                    pagination={
                        "extraction_id":
                            extraction_id,
                        "page_number":
                            page_number,
                    },
                )
            )

            ledger = (
                register_canonical_page(
                    source=SOURCE,
                    endpoint=ENDPOINT,
                    extraction_id=extraction_id,
                    page_number=page_number,
                    payload_hash=payload_hash,
                    content_hash=content_hash,
                    document_ids=document_ids,
                    record_count=len(
                        results
                    ),
                )
            )

            if (
                ledger.get(
                    "canonical_content_hash"
                )
                != content_hash
            ):
                raise RuntimeError(
                    "Canonical page content conflict"
                )

            canonical_document_ids = (
                ledger.get(
                    "canonical_document_ids"
                )
            )

            if (
                not isinstance(
                    canonical_document_ids,
                    list,
                )
                or not canonical_document_ids
            ):
                raise RuntimeError(
                    "Canonical page has no stored documents"
                )

            save_checkpoint(
                source=SOURCE,
                endpoint=ENDPOINT,
                extraction_id=extraction_id,
                cursor=next_url,
                metadata={
                    "completed":
                        next_url is None,
                    "last_page":
                        page_number,
                },
            )

            page_results = len(
                results
            )

            total_results += (
                page_results
            )

            first_ticker = (
                results[0].get(
                    "ticker"
                )
                if results
                else None
            )

            last_ticker = (
                results[-1].get(
                    "ticker"
                )
                if results
                else None
            )

            print(
                f"page={page_number} "
                f"results={page_results} "
                f"chunks={len(document_ids)} "
                f"has_next_url={bool(next_url)} "
                f"first={first_ticker} "
                f"last={last_ticker}"
            )

            url = next_url
            request_parameters = None
            page_number += 1

        pages_stored = (
            page_number - 1
        )

        (
            final_ledger_pages,
            final_total_results,
            total_raw_documents,
        ) = load_existing_progress(
            extraction_id
        )

        if (
            final_ledger_pages
            != pages_stored
        ):
            raise RuntimeError(
                "Final ledger page count "
                "does not match extraction progress"
            )

        if (
            final_total_results
            != total_results
        ):
            raise RuntimeError(
                "Final ledger record count "
                "does not match extraction progress"
            )

        complete_run(
            extraction_id=extraction_id,
            pages_stored=pages_stored,
        )

        print_final_result(
            extraction_id=extraction_id,
            pages_stored=pages_stored,
            total_results=total_results,
            total_raw_documents=total_raw_documents,
        )

    except Exception as exc:
        with suppress(
            Exception
        ):
            fail_run(
                extraction_id=extraction_id,
                error=type(
                    exc
                ).__name__,
            )

        raise


if __name__ == "__main__":
    main()

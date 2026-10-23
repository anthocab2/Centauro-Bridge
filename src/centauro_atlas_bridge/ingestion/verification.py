"""Integrity verification for completed Centauro ingestions."""

from typing import Any

from centauro_atlas_bridge.atlas.client import create_atlas_client
from centauro_atlas_bridge.config import get_database_name
from centauro_atlas_bridge.ingestion.page_ledger import (
    PAGE_LEDGER_COLLECTION,
)
from centauro_atlas_bridge.ingestion.raw import (
    RAW_COLLECTION,
    calculate_ingestion_key,
    calculate_payload_hash,
)
from centauro_atlas_bridge.ingestion.runs import (
    get_run,
    set_verification_result,
)

CHUNK_PAGINATION_FIELDS = {
    "chunk_number",
    "total_chunks",
    "storage_mode",
}


def _add_error(
    errors: list[str],
    error: str,
) -> None:
    """Add one unique integrity error."""
    if error not in errors:
        errors.append(
            error
        )


def _base_pagination(
    pagination: dict[str, Any],
) -> dict[str, Any]:
    """Remove chunk-storage details from page identity."""
    return {
        key: value
        for key, value in pagination.items()
        if key
        not in CHUNK_PAGINATION_FIELDS
    }


def _verify_page(
    page_number: int,
    documents: list[dict[str, Any]],
    ledger: dict[str, Any],
    errors: list[str],
) -> int:
    """Verify canonical chunks belonging to one source page."""
    if not documents:
        _add_error(
            errors,
            f"page_{page_number}_missing",
        )
        return 0

    chunk_numbers: list[int] = []
    total_chunks_values: set[int] = set()
    original_hashes: set[str] = set()

    reconstructed_results: list[Any] = []

    first_metadata: dict[str, Any] | None = None
    first_base_pagination: dict[str, Any] | None = None

    page_source: str | None = None
    page_endpoint: str | None = None
    page_parameters: dict[str, Any] | None = None

    actual_document_ids: set[str] = set()

    for document in documents:
        if "_id" in document:
            actual_document_ids.add(
                str(
                    document["_id"]
                )
            )

        pagination = document.get(
            "pagination",
            {},
        )

        if not isinstance(
            pagination,
            dict,
        ):
            _add_error(
                errors,
                f"page_{page_number}_invalid_pagination",
            )
            continue

        chunk_number = pagination.get(
            "chunk_number"
        )

        total_chunks = pagination.get(
            "total_chunks"
        )

        if (
            not isinstance(
                chunk_number,
                int,
            )
            or chunk_number < 1
        ):
            _add_error(
                errors,
                f"page_{page_number}_invalid_chunk_number",
            )
            continue

        if (
            not isinstance(
                total_chunks,
                int,
            )
            or total_chunks < 1
        ):
            _add_error(
                errors,
                f"page_{page_number}_invalid_total_chunks",
            )
            continue

        chunk_numbers.append(
            chunk_number
        )

        total_chunks_values.add(
            total_chunks
        )

        original_payload_hash = (
            document.get(
                "original_payload_hash"
            )
        )

        if not isinstance(
            original_payload_hash,
            str,
        ):
            _add_error(
                errors,
                f"page_{page_number}_missing_original_hash",
            )

        else:
            original_hashes.add(
                original_payload_hash
            )

        payload = document.get(
            "payload"
        )

        if not isinstance(
            payload,
            dict,
        ):
            _add_error(
                errors,
                (
                    f"page_{page_number}_"
                    f"chunk_{chunk_number}_invalid_payload"
                ),
            )
            continue

        stored_payload_hash = (
            document.get(
                "payload_hash"
            )
        )

        actual_payload_hash = (
            calculate_payload_hash(
                payload
            )
        )

        if (
            stored_payload_hash
            != actual_payload_hash
        ):
            _add_error(
                errors,
                (
                    f"page_{page_number}_"
                    f"chunk_{chunk_number}_"
                    "payload_hash_mismatch"
                ),
            )

        results = payload.get(
            "results"
        )

        if not isinstance(
            results,
            list,
        ):
            _add_error(
                errors,
                (
                    f"page_{page_number}_"
                    f"chunk_{chunk_number}_"
                    "invalid_results"
                ),
            )
            continue

        metadata = {
            key: value
            for key, value
            in payload.items()
            if key != "results"
        }

        if first_metadata is None:
            first_metadata = (
                metadata
            )

        elif (
            metadata
            != first_metadata
        ):
            _add_error(
                errors,
                f"page_{page_number}_metadata_mismatch",
            )

        reconstructed_results.extend(
            results
        )

        base_pagination = (
            _base_pagination(
                pagination
            )
        )

        if (
            first_base_pagination
            is None
        ):
            first_base_pagination = (
                base_pagination
            )

        elif (
            base_pagination
            != first_base_pagination
        ):
            _add_error(
                errors,
                f"page_{page_number}_pagination_mismatch",
            )

        source = document.get(
            "source"
        )

        endpoint = document.get(
            "endpoint"
        )

        parameters = document.get(
            "parameters"
        )

        if page_source is None:
            page_source = source
            page_endpoint = endpoint
            page_parameters = parameters

        elif (
            source != page_source
            or endpoint != page_endpoint
            or parameters
            != page_parameters
        ):
            _add_error(
                errors,
                f"page_{page_number}_provenance_mismatch",
            )

        if isinstance(
            original_payload_hash,
            str,
        ):
            expected_ingestion_key = (
                calculate_ingestion_key(
                    source=source,
                    endpoint=endpoint,
                    parameters=parameters,
                    payload_hash=(
                        original_payload_hash
                    ),
                    pagination=(
                        base_pagination
                    ),
                    fragment=(
                        f"chunk:{chunk_number}"
                    ),
                )
            )

            if (
                document.get(
                    "ingestion_key"
                )
                != expected_ingestion_key
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        f"chunk_{chunk_number}_"
                        "ingestion_key_mismatch"
                    ),
                )

    if (
        len(
            total_chunks_values
        )
        != 1
    ):
        _add_error(
            errors,
            f"page_{page_number}_total_chunks_mismatch",
        )

    expected_total_chunks = (
        next(
            iter(
                total_chunks_values
            )
        )
        if (
            len(
                total_chunks_values
            )
            == 1
        )
        else None
    )

    if (
        len(
            chunk_numbers
        )
        != len(
            set(
                chunk_numbers
            )
        )
    ):
        _add_error(
            errors,
            f"page_{page_number}_duplicate_chunk_position",
        )

    if (
        expected_total_chunks
        is not None
    ):
        expected_chunks = set(
            range(
                1,
                expected_total_chunks + 1,
            )
        )

        actual_chunks = set(
            chunk_numbers
        )

        if (
            actual_chunks
            != expected_chunks
        ):
            _add_error(
                errors,
                f"page_{page_number}_missing_or_extra_chunks",
            )

        if (
            len(
                documents
            )
            != expected_total_chunks
        ):
            _add_error(
                errors,
                f"page_{page_number}_chunk_count_mismatch",
            )

    canonical_chunk_count = (
        ledger.get(
            "canonical_chunk_count"
        )
    )

    if (
        canonical_chunk_count
        != len(
            documents
        )
    ):
        _add_error(
            errors,
            f"page_{page_number}_ledger_chunk_count_mismatch",
        )

    canonical_document_ids = (
        ledger.get(
            "canonical_document_ids"
        )
    )

    if not isinstance(
        canonical_document_ids,
        list,
    ):
        _add_error(
            errors,
            f"page_{page_number}_invalid_canonical_document_ids",
        )

    elif (
        actual_document_ids
        != set(
            canonical_document_ids
        )
    ):
        _add_error(
            errors,
            f"page_{page_number}_canonical_document_set_mismatch",
        )

    canonical_payload_hash = (
        ledger.get(
            "canonical_payload_hash"
        )
    )

    if (
        original_hashes
        != {
            canonical_payload_hash
        }
    ):
        _add_error(
            errors,
            f"page_{page_number}_canonical_payload_hash_mismatch",
        )

    if (
        first_metadata
        is not None
    ):
        reconstructed_payload = {
            **first_metadata,
            "results":
                reconstructed_results,
        }

        reconstructed_payload_hash = (
            calculate_payload_hash(
                reconstructed_payload
            )
        )

        if (
            reconstructed_payload_hash
            != canonical_payload_hash
        ):
            _add_error(
                errors,
                f"page_{page_number}_reconstructed_hash_mismatch",
            )

    reconstructed_content_hash = (
        calculate_payload_hash(
            reconstructed_results
        )
    )

    canonical_content_hash = (
        ledger.get(
            "canonical_content_hash"
        )
    )

    if (
        reconstructed_content_hash
        != canonical_content_hash
    ):
        _add_error(
            errors,
            f"page_{page_number}_content_hash_mismatch",
        )

    canonical_record_count = (
        ledger.get(
            "canonical_record_count"
        )
    )

    if (
        canonical_record_count
        != len(
            reconstructed_results
        )
    ):
        _add_error(
            errors,
            f"page_{page_number}_record_count_mismatch",
        )

    return len(
        reconstructed_results
    )


def verify_extraction(
    extraction_id: str,
) -> dict[str, Any]:
    """Verify execution, canonical pages, chunks, hashes, and provenance."""
    client = create_atlas_client()

    errors: list[str] = []

    try:
        database = client[
            get_database_name()
        ]

        raw_collection = database[
            RAW_COLLECTION
        ]

        ledger_collection = database[
            PAGE_LEDGER_COLLECTION
        ]

        run = get_run(
            extraction_id
        )

        execution_status = (
            run.get(
                "status"
            )
            if run
            else None
        )

        execution_completed = (
            execution_status
            == "completed"
        )

        if run is None:
            _add_error(
                errors,
                "missing_run",
            )

        else:
            if not execution_completed:
                _add_error(
                    errors,
                    "execution_not_completed",
                )

            if "extraction_id" not in run:
                _add_error(
                    errors,
                    "missing_run_extraction_id",
                )

            if "source" not in run:
                _add_error(
                    errors,
                    "missing_run_source",
                )

            if "endpoint" not in run:
                _add_error(
                    errors,
                    "missing_run_endpoint",
                )

            if "parameters" not in run:
                _add_error(
                    errors,
                    "missing_run_parameters",
                )

        run_has_extraction_id = (
            run is not None
            and "extraction_id"
            in run
        )

        run_has_source = (
            run is not None
            and "source"
            in run
        )

        run_has_endpoint = (
            run is not None
            and "endpoint"
            in run
        )

        run_has_parameters = (
            run is not None
            and "parameters"
            in run
        )

        run_extraction_id = (
            run.get(
                "extraction_id"
            )
            if run_has_extraction_id
            else None
        )

        run_source = (
            run.get(
                "source"
            )
            if run_has_source
            else None
        )

        run_endpoint = (
            run.get(
                "endpoint"
            )
            if run_has_endpoint
            else None
        )

        run_parameters = (
            run.get(
                "parameters"
            )
            if run_has_parameters
            else None
        )

        if (
            run_has_extraction_id
            and run_extraction_id
            != extraction_id
        ):
            _add_error(
                errors,
                "run_extraction_id_mismatch",
            )

        ledger_cursor = (
            ledger_collection.find(
                {
                    "extraction_id":
                        extraction_id,
                }
            )
            .sort(
                [
                    (
                        "page_number",
                        1,
                    )
                ]
            )
        )

        page_ledgers: dict[
            int,
            dict[str, Any],
        ] = {}

        alternate_payload_variants = 0

        for ledger in ledger_cursor:
            page_number = (
                ledger.get(
                    "page_number"
                )
            )

            if (
                not isinstance(
                    page_number,
                    int,
                )
                or page_number < 1
            ):
                _add_error(
                    errors,
                    "invalid_page_ledger_number",
                )
                continue

            if (
                page_number
                in page_ledgers
            ):
                _add_error(
                    errors,
                    "duplicate_page_ledger_entry",
                )
                continue

            page_ledgers[
                page_number
            ] = ledger

            if (
                ledger.get(
                    "extraction_id"
                )
                != extraction_id
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "ledger_extraction_id_mismatch"
                    ),
                )

            if (
                run_has_source
                and ledger.get(
                    "source"
                )
                != run_source
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "ledger_source_mismatch"
                    ),
                )

            if (
                run_has_endpoint
                and ledger.get(
                    "endpoint"
                )
                != run_endpoint
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "ledger_endpoint_mismatch"
                    ),
                )

            observed_payload_hashes = (
                ledger.get(
                    "observed_payload_hashes",
                    [],
                )
            )

            observed_content_hashes = (
                ledger.get(
                    "observed_content_hashes",
                    [],
                )
            )

            canonical_payload_hash = (
                ledger.get(
                    "canonical_payload_hash"
                )
            )

            canonical_content_hash = (
                ledger.get(
                    "canonical_content_hash"
                )
            )

            if (
                not isinstance(
                    observed_payload_hashes,
                    list,
                )
                or canonical_payload_hash
                not in observed_payload_hashes
            ):
                _add_error(
                    errors,
                    f"page_{page_number}_invalid_payload_history",
                )

            else:
                alternate_payload_variants += max(
                    0,
                    len(
                        set(
                            observed_payload_hashes
                        )
                    )
                    - 1,
                )

            if (
                not isinstance(
                    observed_content_hashes,
                    list,
                )
                or canonical_content_hash
                not in observed_content_hashes
            ):
                _add_error(
                    errors,
                    f"page_{page_number}_invalid_content_history",
                )

            elif (
                len(
                    set(
                        observed_content_hashes
                    )
                )
                > 1
            ):
                _add_error(
                    errors,
                    f"page_{page_number}_content_conflict",
                )

        if not page_ledgers:
            _add_error(
                errors,
                "no_page_ledger",
            )

        raw_cursor = (
            raw_collection.find(
                {
                    "pagination.extraction_id":
                        extraction_id,
                },
                {
                    "_id": 1,
                    "ingestion_key": 1,
                    "source": 1,
                    "endpoint": 1,
                    "parameters": 1,
                    "payload_hash": 1,
                    "original_payload_hash": 1,
                    "pagination": 1,
                    "payload": 1,
                },
            )
            .sort(
                [
                    (
                        "pagination.page_number",
                        1,
                    ),
                    (
                        "pagination.chunk_number",
                        1,
                    ),
                ]
            )
        )

        raw_documents = 0
        canonical_raw_documents = 0
        noncanonical_raw_documents = 0
        unregistered_raw_documents = 0

        total_results = 0

        ingestion_keys: set[str] = set()

        duplicate_ingestion_keys = 0

        canonical_pages_observed: set[int] = set()

        canonical_documents_by_page: dict[
            int,
            list[dict[str, Any]],
        ] = {}

        for document in raw_cursor:
            raw_documents += 1

            ingestion_key = (
                document.get(
                    "ingestion_key"
                )
            )

            if isinstance(
                ingestion_key,
                str,
            ):
                if (
                    ingestion_key
                    in ingestion_keys
                ):
                    duplicate_ingestion_keys += 1

                else:
                    ingestion_keys.add(
                        ingestion_key
                    )

            else:
                _add_error(
                    errors,
                    "missing_ingestion_key",
                )

            pagination = (
                document.get(
                    "pagination",
                    {},
                )
            )

            page_number = (
                pagination.get(
                    "page_number"
                )
                if isinstance(
                    pagination,
                    dict,
                )
                else None
            )

            if (
                not isinstance(
                    page_number,
                    int,
                )
                or page_number < 1
            ):
                _add_error(
                    errors,
                    "invalid_page_number",
                )
                continue

            if (
                not isinstance(
                    pagination,
                    dict,
                )
                or pagination.get(
                    "extraction_id"
                )
                != extraction_id
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "raw_extraction_id_mismatch"
                    ),
                )

            ledger = page_ledgers.get(
                page_number
            )

            if ledger is None:
                unregistered_raw_documents += 1

                _add_error(
                    errors,
                    f"page_{page_number}_raw_without_ledger",
                )
                continue

            document_source = (
                document.get(
                    "source"
                )
            )

            document_endpoint = (
                document.get(
                    "endpoint"
                )
            )

            document_parameters = (
                document.get(
                    "parameters"
                )
            )

            if (
                document_source
                != ledger.get(
                    "source"
                )
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "raw_ledger_source_mismatch"
                    ),
                )

            if (
                document_endpoint
                != ledger.get(
                    "endpoint"
                )
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "raw_ledger_endpoint_mismatch"
                    ),
                )

            if (
                run_has_source
                and document_source
                != run_source
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "raw_source_mismatch"
                    ),
                )

            if (
                run_has_endpoint
                and document_endpoint
                != run_endpoint
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "raw_endpoint_mismatch"
                    ),
                )

            if (
                run_has_parameters
                and document_parameters
                != run_parameters
            ):
                _add_error(
                    errors,
                    (
                        f"page_{page_number}_"
                        "raw_parameters_mismatch"
                    ),
                )

            original_payload_hash = (
                document.get(
                    "original_payload_hash"
                )
            )

            canonical_payload_hash = (
                ledger.get(
                    "canonical_payload_hash"
                )
            )

            if (
                original_payload_hash
                != canonical_payload_hash
            ):
                noncanonical_raw_documents += 1

                observed_hashes = (
                    ledger.get(
                        "observed_payload_hashes",
                        [],
                    )
                )

                if (
                    original_payload_hash
                    not in observed_hashes
                ):
                    _add_error(
                        errors,
                        (
                            f"page_{page_number}_"
                            "unregistered_raw_capture"
                        ),
                    )

                continue

            canonical_raw_documents += 1

            canonical_pages_observed.add(
                page_number
            )

            canonical_documents_by_page.setdefault(
                page_number,
                [],
            ).append(
                document
            )

        for (
            page_number,
            ledger,
        ) in sorted(
            page_ledgers.items()
        ):
            documents = (
                canonical_documents_by_page.get(
                    page_number,
                    [],
                )
            )

            total_results += (
                _verify_page(
                    page_number=page_number,
                    documents=documents,
                    ledger=ledger,
                    errors=errors,
                )
            )

        if raw_documents == 0:
            _add_error(
                errors,
                "no_raw_documents",
            )

        if duplicate_ingestion_keys:
            _add_error(
                errors,
                "duplicate_ingestion_keys",
            )

        expected_pages = (
            run.get(
                "pages_stored"
            )
            if run
            else None
        )

        ledger_pages = set(
            page_ledgers
        )

        if execution_completed:
            if (
                not isinstance(
                    expected_pages,
                    int,
                )
                or isinstance(
                    expected_pages,
                    bool,
                )
                or expected_pages < 1
            ):
                _add_error(
                    errors,
                    "invalid_pages_stored",
                )

            else:
                expected_page_numbers = set(
                    range(
                        1,
                        expected_pages + 1,
                    )
                )

                if (
                    ledger_pages
                    != expected_page_numbers
                ):
                    _add_error(
                        errors,
                        "page_ledger_set_mismatch",
                    )

                if (
                    canonical_pages_observed
                    != expected_page_numbers
                ):
                    _add_error(
                        errors,
                        "canonical_page_set_mismatch",
                    )

        verified = (
            len(
                errors
            )
            == 0
        )

        verification_status = (
            "verified"
            if verified
            else "invalid"
        )

        if run is not None:
            set_verification_result(
                extraction_id=extraction_id,
                verified=verified,
                errors=errors,
            )

        return {
            "extraction_id":
                extraction_id,
            "execution_status":
                execution_status,
            "execution_completed":
                execution_completed,
            "verification_status":
                verification_status,
            "verified":
                verified,
            "verification_errors":
                errors,
            "raw_documents":
                raw_documents,
            "canonical_raw_documents": (
                canonical_raw_documents
            ),
            "noncanonical_raw_documents": (
                noncanonical_raw_documents
            ),
            "unregistered_raw_documents": (
                unregistered_raw_documents
            ),
            "unique_ingestion_keys": len(
                ingestion_keys
            ),
            "duplicate_ingestion_keys": (
                duplicate_ingestion_keys
            ),
            "alternate_payload_variants": (
                alternate_payload_variants
            ),
            "total_results":
                total_results,
            "observed_pages": len(
                canonical_pages_observed
            ),
            "expected_pages":
                expected_pages,
            "ledger_page_numbers": sorted(
                ledger_pages
            ),
            "canonical_page_numbers": sorted(
                canonical_pages_observed
            ),
            "completed":
                execution_completed,
        }

    finally:
        client.close()

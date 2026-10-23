"""Massive REST API source adapter for Centauro."""

from contextlib import suppress
from copy import deepcopy
from typing import Any
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from centauro_atlas_bridge.config import get_massive_api_key
from centauro_atlas_bridge.ingestion.checkpoints import (
    get_checkpoint,
    save_checkpoint,
)
from centauro_atlas_bridge.ingestion.http_client import fetch_json
from centauro_atlas_bridge.ingestion.identity import (
    build_extraction_id,
)
from centauro_atlas_bridge.ingestion.page_ledger import (
    calculate_page_content_hash,
    register_canonical_page,
)
from centauro_atlas_bridge.ingestion.raw import (
    calculate_payload_hash,
    store_raw_payload_chunks,
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

MASSIVE_BASE_URL = "https://api.massive.com"
MASSIVE_ALLOWED_HOST = "api.massive.com"
SOURCE_NAME = "massive"

AUTH_QUERY_KEYS = {
    "apikey",
    "api_key",
}


class MassiveResponseError(RuntimeError):
    """Raised when Massive returns an invalid logical response."""


def validate_massive_url(
    url: str,
) -> str:
    """Validate that a URL is safe for authenticated Massive requests."""
    if not isinstance(url, str):
        raise TypeError(
            "Massive URL must be a string"
        )

    parts = urlsplit(
        url
    )

    if parts.scheme.lower() != "https":
        raise ValueError(
            "Massive URL must use HTTPS"
        )

    hostname = (
        parts.hostname.lower()
        if parts.hostname
        else None
    )

    if hostname != MASSIVE_ALLOWED_HOST:
        raise ValueError(
            "Massive URL points to an unauthorized host"
        )

    if (
        parts.username is not None
        or parts.password is not None
    ):
        raise ValueError(
            "Massive URL must not contain user credentials"
        )

    try:
        port = parts.port

    except ValueError as exc:
        raise ValueError(
            "Massive URL contains an invalid port"
        ) from exc

    if port not in {
        None,
        443,
    }:
        raise ValueError(
            "Massive URL must use the HTTPS port"
        )

    return url


def sanitize_next_url(
    url: str,
) -> str:
    """Remove authentication parameters from a pagination URL."""
    if not isinstance(url, str):
        raise TypeError(
            "Pagination URL must be a string"
        )

    parts = urlsplit(
        url
    )

    safe_query = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if key.lower()
        not in AUTH_QUERY_KEYS
    ]

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(
                safe_query
            ),
            parts.fragment,
        )
    )


def validate_massive_payload(
    payload: Any,
) -> dict[str, Any]:
    """Validate one successful Massive aggregate response."""
    if not isinstance(payload, dict):
        raise TypeError(
            "Massive payload must be a dictionary"
        )

    status = payload.get(
        "status"
    )

    if status != "OK":
        raise MassiveResponseError(
            "Massive response status is not OK"
        )

    if "results" not in payload:
        raise MassiveResponseError(
            "Massive response does not contain results"
        )

    results = payload[
        "results"
    ]

    if not isinstance(
        results,
        list,
    ):
        raise TypeError(
            "Massive results must be a list"
        )

    results_count = payload.get(
        "resultsCount"
    )

    if results_count is not None:
        if (
            not isinstance(
                results_count,
                int,
            )
            or isinstance(
                results_count,
                bool,
            )
        ):
            raise TypeError(
                "Massive resultsCount must be an integer"
            )

        if results_count < 0:
            raise MassiveResponseError(
                "Massive resultsCount cannot be negative"
            )

        if (
            results_count
            != len(results)
        ):
            raise MassiveResponseError(
                "Massive resultsCount does not match results"
            )

    next_url = payload.get(
        "next_url"
    )

    if (
        next_url is not None
        and not isinstance(
            next_url,
            str,
        )
    ):
        raise TypeError(
            "Massive next_url must be a string"
        )

    return payload


def sanitize_payload_for_storage(
    payload: Any,
) -> dict[str, Any]:
    """Create a storage-safe provider payload without URL credentials."""
    if not isinstance(payload, dict):
        raise TypeError(
            "Massive payload must be a dictionary"
        )

    safe_payload = deepcopy(
        payload
    )

    raw_next_url = safe_payload.get(
        "next_url"
    )

    if raw_next_url is None:
        return safe_payload

    if not isinstance(
        raw_next_url,
        str,
    ):
        raise TypeError(
            "Massive next_url must be a string"
        )

    safe_payload[
        "next_url"
    ] = sanitize_next_url(
        raw_next_url
    )

    return safe_payload


def _validate_completed_checkpoint_metadata(
    checkpoint_metadata: dict[str, Any],
) -> int:
    """Return the final page number from a completed checkpoint."""
    last_page = checkpoint_metadata.get(
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

    return last_page


def _run_identity_matches(
    run: dict[str, Any],
    extraction_id: str,
    endpoint: str,
    parameters: dict[str, Any],
) -> bool:
    """Return whether a run belongs to the exact current request."""
    return (
        run.get(
            "extraction_id"
        )
        == extraction_id
        and run.get(
            "source"
        )
        == SOURCE_NAME
        and run.get(
            "endpoint"
        )
        == endpoint
        and run.get(
            "parameters"
        )
        == parameters
    )


def _verification_matches_checkpoint(
    verification: dict[str, Any],
    last_page: int,
) -> bool:
    """Return whether verified page evidence matches the checkpoint."""
    expected_page_numbers = list(
        range(
            1,
            last_page + 1,
        )
    )

    return (
        verification.get(
            "ledger_page_numbers"
        )
        == expected_page_numbers
        and verification.get(
            "canonical_page_numbers"
        )
        == expected_page_numbers
    )


def _recover_completed_checkpoint(
    extraction_id: str,
    endpoint: str,
    parameters: dict[str, Any],
    checkpoint_metadata: dict[str, Any],
) -> list[str]:
    """Verify and reconcile a completed checkpoint with its run."""
    last_page = (
        _validate_completed_checkpoint_metadata(
            checkpoint_metadata
        )
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
        endpoint=endpoint,
        parameters=parameters,
    ):
        raise RuntimeError(
            "Completed checkpoint conflicts with run identity"
        )

    status = run.get(
        "status"
    )

    if status == "completed":
        run_pages_stored = (
            run.get(
                "pages_stored"
            )
        )

        if (
            not isinstance(
                run_pages_stored,
                int,
            )
            or isinstance(
                run_pages_stored,
                bool,
            )
            or run_pages_stored < 1
            or run_pages_stored
            != last_page
        ):
            raise RuntimeError(
                "Completed checkpoint page count "
                "conflicts with run state"
            )

        verification = (
            verify_extraction(
                extraction_id
            )
        )

        if (
            verification.get(
                "verified"
            )
            is not True
        ):
            raise RuntimeError(
                "Completed extraction failed integrity verification"
            )

        if not _verification_matches_checkpoint(
            verification=verification,
            last_page=last_page,
        ):
            raise RuntimeError(
                "Completed checkpoint page count "
                "conflicts with verified evidence"
            )

        return []

    if status not in {
        "started",
        "failed",
    }:
        raise RuntimeError(
            "Completed checkpoint has unsupported run state"
        )

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
            "Completed checkpoint evidence failed recovery verification"
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
            "Recovered extraction failed final integrity verification"
        )

    if not _verification_matches_checkpoint(
        verification=(
            final_verification
        ),
        last_page=last_page,
    ):
        raise RuntimeError(
            "Recovered extraction page count "
            "conflicts with verified evidence"
        )

    return []


def extract_daily_aggs(
    ticker: str,
    start_date: str,
    end_date: str,
    adjusted: bool = True,
) -> list[str]:
    """Extract Massive daily aggregate pages into MongoDB Atlas."""
    endpoint = (
        f"/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start_date}/{end_date}"
    )

    extraction_id = build_extraction_id(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
    )

    parameters = {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "adjusted": adjusted,
        "sort": "asc",
        "limit": 50000,
    }

    request_parameters = {
        "adjusted": str(
            adjusted
        ).lower(),
        "sort": "asc",
        "limit": 50000,
    }

    headers = {
        "Authorization": (
            f"Bearer {get_massive_api_key()}"
        ),
    }

    checkpoint = get_checkpoint(
        source=SOURCE_NAME,
        endpoint=endpoint,
        extraction_id=extraction_id,
    )

    checkpoint_metadata = (
        checkpoint.get(
            "metadata",
            {},
        )
        if checkpoint
        else {}
    )

    if not isinstance(
        checkpoint_metadata,
        dict,
    ):
        raise TypeError(
            "Checkpoint metadata must be a dictionary"
        )

    if checkpoint_metadata.get(
        "completed"
    ):
        return _recover_completed_checkpoint(
            extraction_id=extraction_id,
            endpoint=endpoint,
            parameters=parameters,
            checkpoint_metadata=(
                checkpoint_metadata
            ),
        )

    start_run(
        extraction_id=extraction_id,
        source=SOURCE_NAME,
        endpoint=endpoint,
        parameters=parameters,
    )

    if (
        checkpoint
        and checkpoint.get(
            "cursor"
        )
    ):
        next_url = checkpoint[
            "cursor"
        ]

        request_parameters = None

        page_number = (
            int(
                checkpoint_metadata.get(
                    "last_page",
                    0,
                )
            )
            + 1
        )

    else:
        next_url = (
            f"{MASSIVE_BASE_URL}"
            f"{endpoint}"
        )

        page_number = 1

    stored_ids: list[str] = []

    try:
        while next_url:
            validate_massive_url(
                next_url
            )

            payload = fetch_json(
                url=next_url,
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

            raw_next_url = (
                storage_payload.get(
                    "next_url"
                )
            )

            safe_next_url = (
                raw_next_url
                if raw_next_url
                else None
            )

            if safe_next_url is not None:
                validate_massive_url(
                    safe_next_url
                )

            page_content_hash = (
                calculate_page_content_hash(
                    storage_payload
                )
            )

            page_payload_hash = (
                calculate_payload_hash(
                    storage_payload
                )
            )

            results = storage_payload[
                "results"
            ]

            page_stored_ids = (
                store_raw_payload_chunks(
                    source=SOURCE_NAME,
                    endpoint=endpoint,
                    parameters=parameters,
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
                    source=SOURCE_NAME,
                    endpoint=endpoint,
                    extraction_id=extraction_id,
                    page_number=page_number,
                    payload_hash=page_payload_hash,
                    content_hash=page_content_hash,
                    document_ids=page_stored_ids,
                    record_count=len(
                        results
                    ),
                )
            )

            canonical_content_hash = (
                ledger.get(
                    "canonical_content_hash"
                )
            )

            if (
                canonical_content_hash
                != page_content_hash
            ):
                raise RuntimeError(
                    "Logical page content changed "
                    "across retries"
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
                    "Page ledger has no canonical documents"
                )

            stored_ids.extend(
                canonical_document_ids
            )

            save_checkpoint(
                source=SOURCE_NAME,
                endpoint=endpoint,
                extraction_id=extraction_id,
                cursor=safe_next_url,
                metadata={
                    "completed":
                        safe_next_url
                        is None,
                    "last_page":
                        page_number,
                },
            )

            next_url = (
                safe_next_url
            )

            request_parameters = None
            page_number += 1

        complete_run(
            extraction_id=extraction_id,
            pages_stored=(
                page_number - 1
            ),
        )

        return stored_ids

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

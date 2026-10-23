"""HTTP extraction utilities for Centauro."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 4
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_RATE_LIMIT_DELAY = 15.0
MAX_RETRY_DELAY = 60.0

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


def _exponential_delay(
    attempt: int,
    retry_delay: float,
) -> float:
    """Calculate bounded exponential backoff."""
    delay = retry_delay * (2**attempt)

    return min(
        delay,
        MAX_RETRY_DELAY,
    )


def _parse_retry_after(
    response: httpx.Response,
) -> float | None:
    """Return the provider-requested Retry-After delay in seconds."""
    retry_after = response.headers.get(
        "Retry-After"
    )

    if retry_after is None:
        return None

    try:
        seconds = float(
            retry_after
        )

    except ValueError:
        try:
            retry_at = parsedate_to_datetime(
                retry_after
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(
                tzinfo=UTC
            )

        seconds = (
            retry_at
            - datetime.now(UTC)
        ).total_seconds()

    return max(
        0.0,
        seconds,
    )


def _response_retry_delay(
    response: httpx.Response,
    attempt: int,
    retry_delay: float,
) -> float:
    """Choose the correct delay for a retryable HTTP response."""
    retry_after = _parse_retry_after(
        response
    )

    if retry_after is not None:
        return retry_after

    if response.status_code == 429:
        return max(
            DEFAULT_RATE_LIMIT_DELAY,
            _exponential_delay(
                attempt,
                retry_delay,
            ),
        )

    return _exponential_delay(
        attempt,
        retry_delay,
    )


def fetch_json(
    url: str,
    parameters: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> Any:
    """Fetch JSON from an HTTP endpoint with bounded local retries."""
    if max_retries < 0:
        raise ValueError(
            "max_retries cannot be negative"
        )

    if retry_delay < 0:
        raise ValueError(
            "retry_delay cannot be negative"
        )

    attempt = 0

    while True:
        try:
            response = httpx.get(
                url,
                params=parameters,
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )

        except httpx.TimeoutException:
            if attempt >= max_retries:
                raise

            delay = _exponential_delay(
                attempt,
                retry_delay,
            )

            attempt += 1

            time.sleep(
                delay
            )

            continue

        if (
            response.status_code
            in RETRYABLE_STATUS_CODES
        ):
            if attempt >= max_retries:
                response.raise_for_status()

            delay = _response_retry_delay(
                response,
                attempt,
                retry_delay,
            )

            attempt += 1

            time.sleep(
                delay
            )

            continue

        response.raise_for_status()

        return response.json()

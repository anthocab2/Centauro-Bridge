"""Unit tests for Massive pagination helpers."""

from centauro_atlas_bridge.sources.massive import (
    build_extraction_id,
    sanitize_next_url,
)


def test_extraction_id_is_deterministic():
    """Identical extraction requests must have identical IDs."""
    first = build_extraction_id(
        ticker="AAPL",
        start_date="2020-01-01",
        end_date="2026-01-01",
        adjusted=True,
    )

    second = build_extraction_id(
        ticker="AAPL",
        start_date="2020-01-01",
        end_date="2026-01-01",
        adjusted=True,
    )

    assert first == second


def test_different_extraction_produces_different_id():
    """Changing extraction parameters must change its identity."""
    first = build_extraction_id(
        ticker="AAPL",
        start_date="2020-01-01",
        end_date="2026-01-01",
        adjusted=True,
    )

    second = build_extraction_id(
        ticker="MSFT",
        start_date="2020-01-01",
        end_date="2026-01-01",
        adjusted=True,
    )

    assert first != second


def test_sanitize_next_url_removes_api_key():
    """Pagination URLs must never preserve API credentials."""
    url = (
        "https://api.massive.com/v3/reference/tickers"
        "?cursor=abc123&apiKey=secret"
    )

    sanitized = sanitize_next_url(url)

    assert "cursor=abc123" in sanitized
    assert "secret" not in sanitized
    assert "apiKey" not in sanitized

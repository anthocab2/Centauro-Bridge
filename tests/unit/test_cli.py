"""Unit tests for the Centauro command-line interface."""

import sys

from centauro_atlas_bridge import cli


def test_massive_aggs_command(monkeypatch, capsys):
    """Verify that the CLI starts a Massive extraction."""
    captured = {}

    def fake_extract_daily_aggs(
        ticker,
        start_date,
        end_date,
    ):
        captured["ticker"] = ticker
        captured["start_date"] = start_date
        captured["end_date"] = end_date

        return ["id_1", "id_2"]

    monkeypatch.setattr(
        cli,
        "extract_daily_aggs",
        fake_extract_daily_aggs,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "centauro-extract",
            "massive-aggs",
            "aapl",
            "2026-01-01",
            "2026-01-31",
        ],
    )

    cli.main()

    output = capsys.readouterr().out

    assert captured["ticker"] == "AAPL"
    assert captured["start_date"] == "2026-01-01"
    assert captured["end_date"] == "2026-01-31"

    assert "Stored pages: 2" in output

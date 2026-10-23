"""Command-line interface for Centauro Atlas Bridge."""

import argparse

from centauro_atlas_bridge.sources.massive import extract_daily_aggs


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Centauro Atlas Bridge data extractor."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    massive_parser = subparsers.add_parser(
        "massive-aggs",
        help="Extract Massive daily aggregates into Atlas.",
    )

    massive_parser.add_argument("ticker")
    massive_parser.add_argument("start_date")
    massive_parser.add_argument("end_date")

    return parser


def main() -> None:
    """Run the Centauro Atlas Bridge CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "massive-aggs":
        stored_ids = extract_daily_aggs(
            ticker=args.ticker.upper(),
            start_date=args.start_date,
            end_date=args.end_date,
        )

        print(f"Stored pages: {len(stored_ids)}")

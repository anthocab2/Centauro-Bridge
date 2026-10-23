"""Headless Application Core interface. All output is safe structured JSON."""

import argparse
import json
from pathlib import Path

from .coordinator import Coordinator
from .models import InputError, Request, load_profile


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes rejected values, potentially containing secrets.
        raise InputError("Invalid command arguments; use --help to see the syntax.")


def main() -> int:
    parser = Parser(description="Centauro Bridge — Massive/Atlas Application Core")
    parser.add_argument(
        "--state-dir", type=Path, help="Installation state directory (keep stable)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Start an independent extraction worker.")
    start.add_argument("--profile", type=Path, required=True)
    start.add_argument("ticker")
    start.add_argument("start_date")
    start.add_argument("end_date")
    start.add_argument("--unadjusted", action="store_true")
    status = commands.add_parser("status", help="Read and reconcile a saved job.")
    status.add_argument("job_id")
    commands.add_parser("jobs", help="List saved jobs and recover interrupted workers.")
    resume = commands.add_parser(
        "resume", help="Resume with a new job_id and the same extraction."
    )
    resume.add_argument("job_id")
    resume.add_argument("--profile", type=Path, required=True)
    try:
        args = parser.parse_args()
        coordinator = Coordinator(args.state_dir)
        if args.command == "start":
            request = Request(
                args.ticker.upper(), args.start_date, args.end_date, not args.unadjusted
            )
            result = coordinator.start(load_profile(args.profile), request)
        elif args.command == "resume":
            result = coordinator.resume(args.job_id, load_profile(args.profile))
        else:
            result = coordinator.state.status(
                args.job_id if args.command == "status" else None
            )
            if result is None:
                raise InputError("Job not found.")
        print(json.dumps(result, ensure_ascii=True))
        return (
            3
            if isinstance(result, dict) and result.get("status") == "busy"
            else (
                1 if isinstance(result, dict) and result.get("status") == "error" else 0
            )
        )
    except InputError as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "diagnostic": {"code": "invalid_input", "message": str(error)},
                }
            )
        )
        return 2
    except Exception:  # noqa: BLE001 -- public boundary must not expose secrets via exception text
        print(
            json.dumps(
                {
                    "status": "error",
                    "diagnostic": {
                        "code": "local_state",
                        "message": "Cannot access local job state; check permissions and application version.",
                    },
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

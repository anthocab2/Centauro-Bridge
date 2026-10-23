"""Detached worker. Lock ownership never transfers between processes."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

from .adapter import MassiveAtlasAdapter
from .diagnostics import classify_error, diagnostic
from .models import Profile, Request
from .state import State, now, worker_identity


def acknowledge(payload: dict) -> None:
    # Only this small protocol message uses stdout; legacy output is discarded.
    try:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, OSError):
        pass  # A vanished coordinator must not kill an accepted job.
    finally:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 -- process lifetime
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 -- process lifetime


def run(directory: Path, token: str, payload: dict, adapter=None) -> None:
    logging.disable(logging.CRITICAL)
    state = State(directory)
    with state.lock() as acquired:
        if not acquired:
            active = state.active()
            acknowledge(
                {"status": "busy", "job_id": active["job_id"] if active else None}
            )
            return
        state.recover()
        active = state.active()
        if active:
            # Unknown process visibility or a still-live owner: do not overlap.
            acknowledge({"status": "busy", "job_id": active["job_id"]})
            return
        request = Request(**payload["request"])
        public_profile = payload["profile"]
        profile = Profile(
            **{
                key: value
                for key, value in public_profile.items()
                if key != "destination_fingerprint"
            },
            massive_api_key=os.environ.get("MASSIVE_API_KEY", ""),
            mongodb_uri=os.environ.get("MONGODB_URI", ""),
        )
        if (
            profile.public() != public_profile
            or os.environ.get("MONGODB_DATABASE") != profile.database
        ):
            raise ValueError("Worker configuration mismatch.")
        resumed_from = payload.get("resumed_from")
        previous = state.get(resumed_from) if resumed_from else None
        if resumed_from and (
            previous is None
            or previous["state"] not in {"failed", "interrupted"}
            or previous["profile"] != profile.public()
            or previous["request"] != request.public()
        ):
            acknowledge(
                {
                    "status": "error",
                    "diagnostic": diagnostic(
                        "invalid_resume",
                        "Resume requires a failed/interrupted job with the same profile and request.",
                    ),
                }
            )
            return
        engine = adapter or MassiveAtlasAdapter()
        extraction_id = engine.extraction_id(request)
        if previous and previous["extraction_id"] not in (None, extraction_id):
            raise ValueError("Extraction identity mismatch.")
        job_id, timestamp = uuid4().hex, now()
        job = {
            "schema_version": 1,
            "job_id": job_id,
            "extraction_id": extraction_id,
            "resumed_from": resumed_from,
            "profile": profile.public(),
            "request": request.public(),
            "state": "preparing",
            "execution_status": "pending",
            "storage_status": "unknown",
            "verification_status": "not_verified",
            "mode": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "finished_at": None,
            "worker": worker_identity(token),
            "result": None,
            "diagnostic": None,
            "capability": {"status": "unknown", "scope": None, "exact_plan": "unknown"},
            "events": [{"state": "preparing", "at": timestamp}],
        }
        state.add(job)
        acknowledge(
            {"status": "accepted", "job_id": job_id, "extraction_id": extraction_id}
        )
        try:
            result = engine.execute(
                request, lambda **changes: state.update(job_id, **changes)
            )
            if result.get("verified") is not True:
                from .diagnostics import VerificationFailed

                raise VerificationFailed
            state.update(
                job_id,
                state="verified",
                execution_status="completed",
                storage_status="completed",
                verification_status="verified",
                result=result,
                finished_at=now(),
                capability=result.get("capability", job["capability"]),
            )
        except BaseException as error:  # noqa: BLE001 -- persist safe failure at worker boundary
            current = state.get(job_id)
            details = classify_error(error)
            state.update(
                job_id,
                state="failed",
                finished_at=now(),
                diagnostic=details,
                execution_status=(
                    "completed"
                    if current["execution_status"] == "completed"
                    else "failed"
                ),
                storage_status=(
                    "completed"
                    if current["storage_status"] == "completed"
                    else "partial_or_unknown"
                ),
                verification_status=(
                    "invalid"
                    if details["code"] == "verification_failed"
                    else "not_verified"
                ),
            )


def main(adapter=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    try:
        if os.environ.get("CENTAURO_EXPLICIT_CONFIG") != "1":
            raise ValueError("Explicit worker configuration is required.")
        payload = json.loads(sys.stdin.read())
        sys.stdin.close()
        run(args.state_dir, args.token, payload, adapter)
    except BaseException:  # noqa: BLE001 -- never expose configuration in an initialization traceback
        acknowledge(
            {
                "status": "error",
                "diagnostic": diagnostic(
                    "worker_start",
                    "The worker could not initialize; check configuration and local state permissions.",
                ),
            }
        )


if __name__ == "__main__":
    main()

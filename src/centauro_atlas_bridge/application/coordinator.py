"""Start a worker and return its receipt; query durable state from any later process."""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

from .diagnostics import diagnostic
from .models import InputError, Profile, Request
from .state import State, default_state_dir

WORKER_MODULE = "centauro_atlas_bridge.application.worker"


class Coordinator:
    def __init__(self, state_dir: Path | None = None):
        self.state = State(state_dir or default_state_dir())

    def start(
        self, profile: Profile, request: Request, *, resumed_from: str | None = None
    ) -> dict:
        payload = {
            "profile": profile.public(),
            "request": request.public(),
            "resumed_from": resumed_from,
        }
        options = (
            {"start_new_session": True}
            if os.name != "nt"
            else {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            }
        )
        try:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    WORKER_MODULE,
                    "--state-dir",
                    str(self.state.directory),
                    "--token",
                    uuid4().hex,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                env=profile.worker_environment(),
                **options,
            )
        except OSError:
            return {
                "status": "error",
                "diagnostic": diagnostic("worker_start", "Cannot start the worker."),
            }
        responses = queue.Queue()

        def receive():
            try:
                responses.put(child.stdout.readline())
            finally:
                child.stdout.close()
                child.wait()  # Reap it if the coordinator stays alive; never block submission.

        threading.Thread(target=receive, daemon=True).start()
        try:
            child.stdin.write(json.dumps(payload))
            child.stdin.close()
            response = responses.get(timeout=20)
            return json.loads(response)
        except (OSError, ValueError, queue.Empty):
            # Startup outcome may be unknown. A later status query reconciles the job.
            return {
                "status": "error",
                "diagnostic": diagnostic(
                    "worker_start_unknown",
                    "No worker receipt was received; query jobs before retrying.",
                ),
            }

    def resume(self, job_id: str, profile: Profile) -> dict:
        job = self.state.status(job_id)
        if job is None:
            raise InputError("Job not found.")
        if (
            job["state"] not in {"interrupted", "failed"}
            or job["profile"] != profile.public()
        ):
            raise InputError(
                "Resume requires a failed/interrupted job and its original profile/target."
            )
        return self.start(profile, Request(**job["request"]), resumed_from=job_id)

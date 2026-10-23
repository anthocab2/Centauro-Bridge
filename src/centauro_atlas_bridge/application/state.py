"""Durable job state, OS exclusion and process identity (local installation only)."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import portalocker
import psutil

from .diagnostics import diagnostic

ACTIVE = ("preparing", "executing", "verifying")


def now() -> str:
    return datetime.now(UTC).isoformat()


def default_state_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") if os.name == "nt" else os.getenv("XDG_STATE_HOME")
    return Path(base or Path.home() / ".local" / "state") / "CentauroBridge"


def worker_identity(token: str) -> dict:
    process = psutil.Process()
    return {"pid": process.pid, "created_at": process.create_time(), "token": token}


def worker_alive(identity: dict) -> bool | None:
    """None means permission prevented a decision; fail closed in that case."""
    try:
        process = psutil.Process(identity["pid"])
        return (
            process.is_running()
            and process.status() != psutil.STATUS_ZOMBIE
            and abs(process.create_time() - identity["created_at"]) < 0.001
            and identity["token"] in process.cmdline()
        )
    except (psutil.NoSuchProcess, KeyError, TypeError):
        return False
    except psutil.AccessDenied:
        return None


class State:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "jobs.sqlite3"
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(
                    "Unsupported job state version; use a compatible application."
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS jobs "
                "(job_id TEXT PRIMARY KEY, state TEXT NOT NULL, document TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS one_active ON jobs((1)) "
                "WHERE state IN ('preparing', 'executing', 'verifying')"
            )
            connection.execute("PRAGMA user_version=1")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def lock(self):
        # Never unlink the lock file: doing so would allow a second inode/lock.
        handle = (self.directory / "worker.lock").open("a+b")
        acquired = False
        try:
            try:
                portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
                acquired = True
            except portalocker.exceptions.LockException:
                pass
            yield acquired
        finally:
            if acquired:
                portalocker.unlock(handle)
            handle.close()

    def add(self, document: dict) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?)",
                (document["job_id"], document["state"], json.dumps(document)),
            )

    def update(self, job_id: str, **changes) -> dict:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT document FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Job not found.")
            document = json.loads(row[0])
            timestamp = now()
            if "state" in changes and changes["state"] != document["state"]:
                document["events"].append({"state": changes["state"], "at": timestamp})
            document.update(changes, updated_at=timestamp)
            connection.execute(
                "UPDATE jobs SET state=?, document=? WHERE job_id=?",
                (document["state"], json.dumps(document), job_id),
            )
        return document

    def get(self, job_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT document FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT document FROM jobs ORDER BY rowid DESC"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def active(self) -> dict | None:
        return next((job for job in self.list() if job["state"] in ACTIVE), None)

    def recover(self) -> None:
        """Caller owns worker.lock; no worker can start while reconciling."""
        for job in self.list():
            if job["state"] in ACTIVE and worker_alive(job["worker"]) is False:
                self.update(
                    job["job_id"],
                    state="interrupted",
                    finished_at=now(),
                    execution_status=(
                        "completed"
                        if job["execution_status"] == "completed"
                        else "interrupted"
                    ),
                    verification_status="not_verified",
                    diagnostic=diagnostic(
                        "worker_interrupted", "The original worker is no longer alive."
                    ),
                )

    def status(self, job_id: str | None = None):
        with self.lock() as acquired:
            if acquired:
                self.recover()
        if job_id is not None:
            return self.get(job_id)
        return self.list()

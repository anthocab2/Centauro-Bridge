import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import psutil
import pytest

from centauro_atlas_bridge.application import coordinator
from centauro_atlas_bridge.application.coordinator import Coordinator
from centauro_atlas_bridge.application.models import InputError, Request
from centauro_atlas_bridge.application.state import ACTIVE, State, worker_alive


def wait_for(core, job_id, states, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = core.state.status(job_id)
        if job["state"] in states:
            return job
        time.sleep(0.04)
    raise AssertionError(f"Job did not reach {states}: {job}")


@pytest.fixture
def core(tmp_path, monkeypatch):
    monkeypatch.setattr(
        coordinator, "WORKER_MODULE", "tests.application.worker_fixture"
    )
    value = Coordinator(tmp_path)
    yield value
    for job in value.state.list():
        if job["state"] in ACTIVE and worker_alive(job["worker"]):
            process = psutil.Process(job["worker"]["pid"])
            process.kill()
            process.wait(timeout=10)


def request(ticker="AAPL"):
    return Request(ticker, "2025-01-02", "2025-01-03")


def test_detached_job_survives_coordinator_and_persists(core, profile):
    receipt = core.start(profile, request("SLOW"))
    assert receipt["status"] == "accepted"
    later = Coordinator(core.state.directory)
    job = wait_for(later, receipt["job_id"], {"verified"})
    assert job["result"]["bar_count"] is None
    assert len(job["extraction_id"]) == 64
    assert [event["state"] for event in job["events"]] == [
        "preparing",
        "executing",
        "verifying",
        "verified",
    ]
    assert job["created_at"] <= job["updated_at"]
    assert job["finished_at"]


def test_simultaneous_requests_have_one_worker(core, profile):
    with ThreadPoolExecutor(2) as pool:
        receipts = list(
            pool.map(lambda _: core.start(profile, request("HOLD")), range(2))
        )
    assert sorted(r["status"] for r in receipts) == ["accepted", "busy"]
    assert len(core.state.list()) == 1
    accepted = next(r for r in receipts if r["status"] == "accepted")
    busy = next(r for r in receipts if r["status"] == "busy")
    assert busy["job_id"] in (None, accepted["job_id"])


def test_lock_retained_during_verification(core, profile):
    receipt = core.start(profile, request("VERIFY"))
    wait_for(core, receipt["job_id"], {"verifying"})
    assert core.start(profile, request())["status"] == "busy"
    job = wait_for(core, receipt["job_id"], {"verified"})
    assert job["verification_status"] == "verified"


def test_killed_worker_becomes_interrupted_and_resume_has_new_job(core, profile):
    receipt = core.start(profile, request("HOLD"))
    job = wait_for(core, receipt["job_id"], {"executing"})
    process = psutil.Process(job["worker"]["pid"])
    process.kill()
    process.wait(timeout=10)
    interrupted = wait_for(core, job["job_id"], {"interrupted"})
    assert interrupted["diagnostic"]["code"] == "worker_interrupted"
    resumed = core.resume(job["job_id"], profile)
    assert resumed["status"] == "accepted"
    assert resumed["job_id"] != job["job_id"]
    new = wait_for(core, resumed["job_id"], {"executing"})
    assert new["extraction_id"] == job["extraction_id"]
    assert new["resumed_from"] == job["job_id"]


def test_saved_pid_alone_is_not_liveness(core, profile):
    receipt = core.start(profile, request("FAIL"))
    job = wait_for(core, receipt["job_id"], {"failed"})
    process = psutil.Process()
    core.state.update(
        job["job_id"],
        state="executing",
        worker={
            "pid": os.getpid(),
            "created_at": process.create_time(),
            "token": "unrelated-token",
        },
    )
    recovered = core.state.status(job["job_id"])
    assert recovered["state"] == "interrupted"
    assert (
        worker_alive({"pid": os.getpid(), "created_at": 0, "token": "anything"})
        is False
    )


def test_secrets_never_enter_job_state_or_error(core, profile):
    receipt = core.start(profile, request("FAIL"))
    job = wait_for(core, receipt["job_id"], {"failed"})
    assert job["diagnostic"]["code"] == "engine_failed"
    assert job["verification_status"] == "not_verified"
    serialized = json.dumps(job)
    raw = core.state.path.read_bytes()
    for secret in (
        profile.massive_api_key,
        profile.mongodb_uri,
        "atlas-secret-sentinel",
    ):
        assert secret not in serialized
        assert secret.encode() not in raw


def test_resume_rejects_changed_destination(core, profile):
    receipt = core.start(profile, request("FAIL"))
    wait_for(core, receipt["job_id"], {"failed"})
    with pytest.raises(InputError):
        core.resume(receipt["job_id"], replace(profile, database="other"))


def test_unknown_state_schema_fails_closed(tmp_path):
    state = State(tmp_path)
    with state.connection() as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError, match="Unsupported"):
        State(tmp_path)


def test_cli_validation_is_safe(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "centauro_atlas_bridge.application.cli",
            "--state-dir",
            str(tmp_path),
            "start",
            "--profile",
            "not-found",
            "secret?token",
            "2025-01-01",
            "2025-01-02",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["diagnostic"]["code"] == "invalid_input"
    assert "secret?token" not in result.stdout + result.stderr


def test_popen_failure_is_safe(core, profile, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError(profile.mongodb_uri)

    monkeypatch.setattr(coordinator.subprocess, "Popen", fail)
    result = core.start(profile, request())
    assert result["diagnostic"]["code"] == "worker_start"
    assert profile.mongodb_uri not in json.dumps(result)


def test_verification_failure_preserves_completed_execution(core, profile):
    receipt = core.start(profile, request("BADVERIFY"))
    job = wait_for(core, receipt["job_id"], {"failed"})
    assert job["execution_status"] == "completed"
    assert job["storage_status"] == "completed"
    assert job["verification_status"] == "invalid"
    assert job["diagnostic"]["code"] == "verification_failed"
    assert job["result"] is None


def test_worker_survives_exit_of_actual_submitting_process(core, profile):
    program = """
import json, sys
from pathlib import Path
from centauro_atlas_bridge.application import coordinator
from centauro_atlas_bridge.application.models import Profile, Request
coordinator.WORKER_MODULE = "tests.application.worker_fixture"
profile = Profile("test", "test-atlas", "mvp_test", "massive-secret-sentinel",
                  "mongodb://user:atlas-secret-sentinel@localhost")
core = coordinator.Coordinator(Path(sys.argv[1]))
print(json.dumps(core.start(profile, Request("HOLD", "2025-01-02", "2025-01-03"))))
"""
    parent = subprocess.run(
        [sys.executable, "-c", program, str(core.state.directory)],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    receipt = json.loads(parent.stdout)
    job = wait_for(core, receipt["job_id"], {"executing"})
    assert worker_alive(job["worker"]) is True
    assert core.start(profile, request())["status"] == "busy"


def test_unknown_process_visibility_keeps_slot_reserved(core, profile, monkeypatch):
    receipt = core.start(profile, request("FAIL"))
    job = wait_for(core, receipt["job_id"], {"failed"})
    core.state.update(job["job_id"], state="executing")
    monkeypatch.setattr(
        "centauro_atlas_bridge.application.state.worker_alive", lambda _: None
    )
    assert core.state.status(job["job_id"])["state"] == "executing"


def test_coordinator_import_never_loads_legacy_config():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import centauro_atlas_bridge.application.coordinator; "
                "assert 'centauro_atlas_bridge.config' not in sys.modules; "
                "assert 'centauro_atlas_bridge.sources.massive' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == ""

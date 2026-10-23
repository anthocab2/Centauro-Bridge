import json
import os
import sys
from pathlib import Path

import pytest
from streamlit.proto.TextInput_pb2 import TextInput
from streamlit.testing.v1 import AppTest

from centauro_atlas_bridge.application.models import Profile, Request
from centauro_atlas_bridge.application.state import State, now
from centauro_atlas_bridge.dashboard import app
from centauro_atlas_bridge.dashboard.session import DashboardSession
from centauro_atlas_bridge.ingestion.identity import build_extraction_id
from centauro_atlas_bridge.reading.canonical import ReadingError


class TestCore:
    __test__ = False

    def __init__(self, directory):
        self.state = State(directory)
        self.starts = 0
        self.resumes = 0
        self.unknown = False

    def start(self, profile, request):
        self.starts += 1
        if self.unknown:
            return {"status": "error", "diagnostic": {"code": "worker_start_unknown"}}
        job_id = f"job-{self.starts}"
        extraction_id = build_extraction_id(**request.public())
        self.state.add(
            {
                "job_id": job_id,
                "extraction_id": extraction_id,
                "profile": profile.public(),
                "request": request.public(),
                "state": "verified",
                "mode": "new",
                "execution_status": "completed",
                "storage_status": "completed",
                "verification_status": "verified",
                "created_at": now(),
                "updated_at": now(),
                "finished_at": now(),
                "result": {"bar_count": None},
                "diagnostic": None,
                "events": [],
                "capability": {"status": "unknown"},
            }
        )
        return {"status": "accepted", "job_id": job_id, "extraction_id": extraction_id}

    def resume(self, job_id, profile):
        self.resumes += 1
        return self.start(profile, Request(**self.state.get(job_id)["request"]))


def button(at, label):
    return next(value for value in at.button if value.label == label)


def field(at, label):
    return next(value for value in at.text_input if value.label == label)


def activate(at):
    field(at, "Credencial de Massive").input("secret-api-sentinel")
    field(at, "URI de MongoDB Atlas").input(
        "mongodb://user:secret-uri-sentinel@localhost"
    )
    button(at, "Activar perfil en esta sesión").click().run()
    assert not at.exception


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dashboard.py"])
    core = TestCore(tmp_path)
    monkeypatch.setattr(app, "create_coordinator", lambda _: core)
    at = AppTest.from_file(
        Path(__file__).resolve().parents[2] / "dashboard.py", default_timeout=15
    ).run()
    assert not at.exception
    return at, core


def test_profile_is_explicit_session_only_and_password_inputs(ui):
    at, core = ui
    environment = dict(os.environ)
    activate(at)
    session = at.session_state["dashboard_session"]
    assert isinstance(session.profile, Profile)
    assert core.starts == 0
    assert dict(os.environ) == environment
    assert field(at, "Credencial de Massive").proto.type == TextInput.PASSWORD
    assert field(at, "URI de MongoDB Atlas").proto.type == TextInput.PASSWORD
    public = json.dumps(session.public()) + repr(session)
    visible = "\n".join(
        element.value
        for kind in (at.markdown, at.caption, at.success, at.info, at.error)
        for element in kind
    )
    for secret in ("secret-api-sentinel", "secret-uri-sentinel"):
        assert secret not in public + visible
        assert secret.encode() not in core.state.path.read_bytes()


def test_reruns_refresh_and_duplicate_submission_do_not_start_again(ui):
    at, core = ui
    activate(at)
    at.radio[0].set_value("Extracciones").run()
    at.run()
    assert core.starts == 0
    button(at, "Iniciar extracción").click().run()
    assert not at.exception and not at.error
    assert core.starts == 1
    session = at.session_state["dashboard_session"]
    session.submit(
        core, session.nonce, request=Request("AAPL", "2025-01-02", "2025-01-03")
    )
    assert core.starts == 1
    at.run()
    button(at, "Actualizar estado").click().run()
    assert core.starts == 1
    assert button(at, "Iniciar extracción").disabled
    assert len(core.state.status()) == 1


def test_browser_session_refresh_retains_job_in_existing_state(ui):
    at, core = ui
    activate(at)
    at.radio[0].set_value("Extracciones").run()
    button(at, "Iniciar extracción").click().run()
    fresh = AppTest.from_file(
        Path(__file__).resolve().parents[2] / "dashboard.py", default_timeout=15
    ).run()
    fresh.radio[0].set_value("Extracciones").run()
    assert fresh.selectbox[0].value == "job-1"
    assert any("job-1" in item.value for item in fresh.caption)
    assert core.starts == 1
    assert fresh.session_state["dashboard_session"].profile is None


def test_unknown_start_requires_explicit_status_check_before_retry(ui):
    at, core = ui
    activate(at)
    core.unknown = True
    at.radio[0].set_value("Extracciones").run()
    button(at, "Iniciar extracción").click().run()
    assert core.starts == 1
    assert button(at, "Preparar otra solicitud").disabled
    at.run()
    assert core.starts == 1
    button(at, "Consultar estado tras inicio incierto").click().run()
    assert not button(at, "Preparar otra solicitud").disabled
    button(at, "Preparar otra solicitud").click().run()
    assert core.starts == 1  # Preparing never sends.


def test_demo_walkthrough_filters_one_dataset_without_jobs(ui):
    at, core = ui
    button(at, "Explorar datos de prueba").click().run()
    assert at.radio[0].value == "Datos"
    assert not at.error and not at.exception
    assert len(at.dataframe[0].value) == 10
    assert any("DATOS DE PRUEBA" in item.value for item in at.warning)
    dataset = at.session_state["dataset"]
    assert dataset.request.ticker == "DEMO"
    next(
        value for value in at.date_input if value.label == "Mostrar desde (UTC)"
    ).set_value("2026-10-05").run()
    assert len(at.dataframe[0].value) == 8
    assert core.starts == 0 and core.state.status() == []


def test_active_job_prevents_profile_reconfiguration(ui, monkeypatch):
    at, core = ui
    activate(at)
    profile = at.session_state["dashboard_session"].profile
    receipt = core.start(profile, Request("AAPL", "2025-01-02", "2025-01-03"))
    core.state.update(receipt["job_id"], state="executing", worker={})
    monkeypatch.setattr(
        "centauro_atlas_bridge.application.state.worker_alive", lambda _: None
    )
    at.run()
    assert button(at, "Activar perfil en esta sesión").disabled
    assert field(at, "URI de MongoDB Atlas").disabled
    with pytest.raises(ValueError, match="trabajo activo"):
        at.session_state["dashboard_session"].configure(profile, core)


def test_resume_is_only_dispatched_once_through_coordinator(ui):
    at, core = ui
    activate(at)
    session = at.session_state["dashboard_session"]
    core.start(session.profile, Request("AAPL", "2025-01-02", "2025-01-03"))
    core.state.update("job-1", state="failed")
    token = session.nonce
    session.submit(core, token, resume_id="job-1")
    session.submit(core, token, resume_id="job-1")
    assert core.resumes == 1
    assert isinstance(session, DashboardSession)


def test_saved_extraction_reads_only_on_request_and_clears_failed_snapshot(
    ui, monkeypatch
):
    at, core = ui
    activate(at)
    profile = at.session_state["dashboard_session"].profile
    dataset = app.demo_dataset()
    receipt = core.start(profile, dataset.request)
    calls = []

    def reader(actual_profile, actual_job):
        assert actual_profile == profile
        assert actual_job["job_id"] == receipt["job_id"]
        calls.append(actual_job["extraction_id"])
        if len(calls) > 1:
            raise ReadingError("missing_fragment")
        return dataset

    monkeypatch.setattr(app, "read_extraction", reader)
    at.radio[0].set_value("Datos").run()
    assert not calls and not at.dataframe
    button(at, "Verificar y abrir datos").click().run()
    assert len(at.dataframe[0].value) == 10
    at.run()
    assert len(calls) == 1 and core.starts == 1
    button(at, "Verificar y abrir datos").click().run()
    assert len(calls) == 2 and not at.dataframe
    assert any("fragmento" in message.value for message in at.error)
    assert core.state.get(receipt["job_id"])["result"]["bar_count"] is None

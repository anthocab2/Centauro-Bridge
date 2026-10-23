import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

from centauro_atlas_bridge.application.models import (
    InputError,
    Profile,
    Request,
    load_profile,
)


def test_frozen_configuration_and_no_parent_environment_changes(profile, monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "parent-credential")
    before = dict(os.environ)
    environment = profile.worker_environment()
    assert dict(os.environ) == before
    assert environment["MASSIVE_API_KEY"] == "massive-secret-sentinel"
    monkeypatch.setenv("MASSIVE_API_KEY", "rotated")
    assert environment["MASSIVE_API_KEY"] == profile.massive_api_key
    with pytest.raises(FrozenInstanceError):
        profile.database = "other"
    request = Request("AAPL", "2025-01-02", "2025-01-02")
    with pytest.raises(FrozenInstanceError):
        request.adjusted = False
    public = json.dumps(profile.public()) + repr(profile)
    assert profile.massive_api_key not in public
    assert profile.mongodb_uri not in public
    assert "atlas-secret-sentinel" not in public


@pytest.mark.parametrize(
    "changes",
    [
        {"ticker": "../secret"},
        {"ticker": "aapl"},
        {"ticker": ""},
        {"start_date": "2025-02-30"},
        {"end_date": "2024-01-01"},
        {"start_date": "20250101"},
        {"adjusted": "false"},
        {"adjusted": 1},
    ],
)
def test_invalid_request(changes):
    args = {"ticker": "AAPL", "start_date": "2025-01-01", "end_date": "2025-01-02"}
    with pytest.raises(InputError):
        Request(**(args | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"massive_api_key": ""},
        {"mongodb_uri": "invalid-secret"},
        {"provider": "other"},
        {"destination": "other"},
        {"database": "bad/name"},
        {"declared_plan": "secret?key"},
    ],
)
def test_invalid_profile_does_not_echo_input(profile, changes):
    with pytest.raises(InputError) as caught:
        replace(profile, **changes)
    assert "secret" not in str(caught.value)


def test_profile_resolves_environment_once(tmp_path, monkeypatch):
    path = tmp_path / "profile.toml"
    path.write_text("""profile_id = "mvp"
provider = "massive"
destination = "atlas"
destination_id = "mvp-atlas"
database = "mvp_test"
massive_api_key_env = "PROFILE_KEY"
mongodb_uri_env = "PROFILE_URI"
""")
    monkeypatch.setenv("PROFILE_KEY", "original-secret")
    monkeypatch.setenv("PROFILE_URI", "mongodb://localhost")
    snapshot = load_profile(path)
    monkeypatch.setenv("PROFILE_KEY", "changed-secret")
    assert snapshot.massive_api_key == "original-secret"
    assert load_profile(path).massive_api_key == "changed-secret"


def test_explicit_worker_environment_precedes_legacy_import(profile, tmp_path):
    (tmp_path / ".env").write_text(
        "MASSIVE_API_KEY=dotenv-secret\nMONGODB_DATABASE=wrong\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from centauro_atlas_bridge.config import get_database_name; "
                "print(get_database_name())"
            ),
        ],
        env=profile.worker_environment(),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "mvp_test"


def test_profile_target_fingerprint_ignores_rotated_credentials(profile):
    rotated = replace(profile, mongodb_uri="mongodb://user:rotated@localhost")
    other = replace(profile, mongodb_uri="mongodb://user:rotated@otherhost")
    assert rotated.public() == profile.public()
    assert other.public() != profile.public()


def test_public_profile_has_no_secret_fields(profile):
    assert not {"massive_api_key", "mongodb_uri"} & profile.public().keys()
    assert isinstance(profile, Profile)

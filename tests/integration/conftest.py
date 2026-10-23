"""Real Atlas tests are explicit; absent credentials are reported as skips."""

import os

import pytest


@pytest.fixture(autouse=True)
def require_explicit_real_atlas():
    if os.getenv("CENTAURO_REAL_ATLAS") != "1":
        pytest.skip(
            "Real Atlas pending: set CENTAURO_REAL_ATLAS=1 with a dedicated MVP database."
        )
    if not os.getenv("MONGODB_URI") or not os.getenv("MONGODB_DATABASE"):
        pytest.fail("Real Atlas requested but MONGODB_URI/MONGODB_DATABASE is missing.")

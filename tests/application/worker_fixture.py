"""Test-only subprocess adapter. No fake engine option is exposed by the product CLI."""

import os
import time

from centauro_atlas_bridge.application.adapter import MassiveAtlasAdapter
from centauro_atlas_bridge.application.diagnostics import VerificationFailed
from centauro_atlas_bridge.application.worker import main


class FixtureAdapter(MassiveAtlasAdapter):
    def execute(self, request, progress):
        assert os.environ["CENTAURO_EXPLICIT_CONFIG"] == "1"
        assert os.environ["MASSIVE_API_KEY"] == "massive-secret-sentinel"
        assert os.environ["MONGODB_DATABASE"] == "mvp_test"
        progress(state="executing", execution_status="running")
        if request.ticker == "FAIL":
            raise RuntimeError(os.environ["MONGODB_URI"])
        if request.ticker == "HOLD":
            time.sleep(60)
        if request.ticker == "SLOW":
            time.sleep(1)
        progress(
            state="verifying",
            execution_status="completed",
            storage_status="completed",
            verification_status="running",
        )
        if request.ticker == "VERIFY":
            time.sleep(2)
        if request.ticker == "BADVERIFY":
            raise VerificationFailed
        return {"verified": True, "bar_count": None, "mode": "new"}


if __name__ == "__main__":
    main(FixtureAdapter())

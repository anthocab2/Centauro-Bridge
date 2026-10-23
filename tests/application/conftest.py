import pytest

from centauro_atlas_bridge.application.models import Profile


@pytest.fixture
def profile():
    return Profile(
        profile_id="test",
        destination_id="test-atlas",
        database="mvp_test",
        massive_api_key="massive-secret-sentinel",
        mongodb_uri="mongodb://user:atlas-secret-sentinel@localhost",
    )

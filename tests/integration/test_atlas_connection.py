"""Integration tests for MongoDB Atlas connectivity."""

from centauro_atlas_bridge.atlas.client import ping_atlas


def test_atlas_connection():
    """Verify that Centauro can reach MongoDB Atlas."""
    assert ping_atlas() is True

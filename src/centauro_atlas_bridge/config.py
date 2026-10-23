"""Application configuration for Centauro Atlas Bridge."""

import os

from dotenv import load_dotenv

if os.getenv("CENTAURO_EXPLICIT_CONFIG") != "1":
    load_dotenv()


def get_mongodb_uri():
    """Return the MongoDB Atlas connection URI."""
    uri = os.getenv("MONGODB_URI")

    if not uri:
        raise ValueError("MONGODB_URI is not configured")

    return uri


def get_database_name():
    """Return the configured MongoDB database name."""
    database_name = os.getenv("MONGODB_DATABASE")

    if not database_name:
        raise ValueError("MONGODB_DATABASE is not configured")

    return database_name


def get_massive_api_key():
    """Return the configured Massive API key."""
    api_key = os.getenv("MASSIVE_API_KEY")

    if not api_key:
        raise ValueError("MASSIVE_API_KEY is not configured")

    return api_key

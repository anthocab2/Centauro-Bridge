"""Explicit, bounded connection probes. No environment mutation or cached clients."""

from datetime import UTC, datetime

import httpx
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from .diagnostics import classify_error
from .models import Profile, Request


def explicit_atlas_client(profile: Profile):
    return MongoClient(
        profile.mongodb_uri,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
        appname="centauro-bridge-reader",
        tz_aware=True,
    )


def probe_atlas(profile: Profile) -> dict:
    try:
        with explicit_atlas_client(profile) as client:
            client.admin.command("ping")
        return {
            "status": "confirmed",
            "scope": "atlas_ping",
            "write_access": "unknown",
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as error:  # noqa: BLE001 -- secret-safe UI boundary
        return {
            "status": "unknown",
            "scope": "atlas_ping",
            "diagnostic": classify_error(error),
        }


def probe_massive(profile: Profile, request: Request) -> dict:
    if request.start_date != request.end_date:
        return {"status": "unknown", "diagnostic": {"code": "probe_range"}}
    try:
        response = httpx.get(
            f"https://api.massive.com/v2/aggs/ticker/{request.ticker}/range/1/day/"
            f"{request.start_date}/{request.end_date}",
            params={
                "adjusted": str(request.adjusted).lower(),
                "sort": "asc",
                "limit": 1,
            },
            headers={"Authorization": f"Bearer {profile.massive_api_key}"},
            timeout=10,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "OK"
            or not isinstance(payload.get("results"), list)
        ):
            return {"status": "unknown", "diagnostic": {"code": "provider_response"}}
        count = payload.get("resultsCount")
        if count is not None and (
            type(count) is not int or count != len(payload["results"])
        ):
            return {"status": "unknown", "diagnostic": {"code": "provider_response"}}
        return {
            "status": "confirmed",
            "scope": "daily_aggregates_probe",
            "request": request.public(),
            "data_status": "present" if payload["results"] else "empty",
            "checked_at": datetime.now(UTC).isoformat(),
            "exact_plan": "unknown",
        }
    except Exception as error:  # noqa: BLE001 -- no URL, headers or error body reaches UI
        return {
            "status": "unknown",
            "diagnostic": classify_error(error),
            "exact_plan": "unknown",
        }

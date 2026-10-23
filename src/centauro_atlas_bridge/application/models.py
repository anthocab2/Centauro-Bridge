"""Immutable input and explicit, secret-free public representations."""

import hashlib
import os
import re
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


class InputError(ValueError):
    """A message authored locally, never containing rejected input."""


def identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value
    ):
        raise InputError(
            f"{label}: use 1–64 letters, numbers, dots, underscores or hyphens."
        )


@dataclass(frozen=True)
class Request:
    ticker: str
    start_date: str
    end_date: str
    adjusted: bool = True

    def __post_init__(self):
        if not isinstance(self.ticker, str) or not re.fullmatch(
            r"[A-Z0-9][A-Z0-9.:-]{0,31}", self.ticker
        ):
            raise InputError(
                "ticker: use an uppercase symbol of at most 32 characters."
            )
        try:
            for value in (self.start_date, self.end_date):
                if not isinstance(value, str) or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", value
                ):
                    raise ValueError
            start, end = (
                date.fromisoformat(self.start_date),
                date.fromisoformat(self.end_date),
            )
        except (ValueError, TypeError):
            raise InputError("Dates must be valid YYYY-MM-DD values.") from None
        if end < start:
            raise InputError("end_date must be on or after start_date.")
        if type(self.adjusted) is not bool:
            raise InputError("adjusted must be a boolean.")

    def public(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Profile:
    profile_id: str
    destination_id: str
    database: str
    massive_api_key: str = field(repr=False)
    mongodb_uri: str = field(repr=False)
    provider: str = "massive"
    destination: str = "atlas"
    declared_plan: str = "unknown"

    def __post_init__(self):
        for name in ("profile_id", "destination_id", "database", "declared_plan"):
            identifier(getattr(self, name), name)
        if self.provider != "massive" or self.destination != "atlas":
            raise InputError("This release supports only Massive and Atlas.")
        if (
            not isinstance(self.massive_api_key, str)
            or not self.massive_api_key.strip()
        ):
            raise InputError(
                "Configure the Massive credential referenced by the profile."
            )
        if not isinstance(self.mongodb_uri, str):
            raise InputError(
                "Configure the Atlas credential referenced by the profile."
            )
        try:
            parts = urlsplit(self.mongodb_uri)
            if parts.scheme not in {"mongodb", "mongodb+srv"} or not parts.hostname:
                raise ValueError
        except ValueError:
            raise InputError("Configure a valid MongoDB connection URI.") from None

    def public(self) -> dict:
        # Excludes userinfo and query options, including passwords/auth tokens.
        cluster = urlsplit(self.mongodb_uri).netloc.rsplit("@", 1)[-1].lower()
        target = hashlib.sha256(f"{cluster}/{self.database}".encode()).hexdigest()
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "destination": self.destination,
            "destination_id": self.destination_id,
            "database": self.database,
            "destination_fingerprint": target,
            "declared_plan": self.declared_plan,
        }

    def worker_environment(self) -> dict[str, str]:
        # Copy, never mutate the coordinator's environment. Resolve credentials once.
        environment = dict(os.environ)
        environment.update(
            MASSIVE_API_KEY=self.massive_api_key,
            MONGODB_URI=self.mongodb_uri,
            MONGODB_DATABASE=self.database,
            CENTAURO_EXPLICIT_CONFIG="1",
            PYTHON_DOTENV_DISABLED="1",
        )
        return environment


def load_profile(path: Path) -> Profile:
    """Read a public TOML profile; secrets are resolved from named environment keys."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return Profile(
            profile_id=data["profile_id"],
            destination_id=data["destination_id"],
            database=data["database"],
            provider=data["provider"],
            destination=data["destination"],
            declared_plan=data.get("declared_plan", "unknown"),
            massive_api_key=os.environ.get(data["massive_api_key_env"], ""),
            mongodb_uri=os.environ.get(data["mongodb_uri_env"], ""),
        )
    except InputError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise InputError(
            "Cannot read profile: check its TOML format and required fields."
        ) from None

"""Diagnostics based on observed evidence, without exception text or provider bodies."""

import httpx
from pymongo.errors import ConnectionFailure, OperationFailure


class VerificationFailed(RuntimeError):
    pass


def diagnostic(code: str, message: str, *, http_status: int | None = None) -> dict:
    return {"code": code, "message": message, "http_status": http_status}


def classify_error(error: BaseException) -> dict:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        messages = {
            401: (
                "credentials",
                "The provider rejected authentication; check the credential.",
            ),
            403: (
                "access_restricted",
                "The provider denied this request; check access rights.",
            ),
            429: (
                "rate_limited",
                "The provider's request limit persists after retries; try later.",
            ),
        }
        code, message = messages.get(
            status, ("provider_http", "The provider returned an HTTP error.")
        )
        return diagnostic(code, message, http_status=status)
    if isinstance(error, OperationFailure):
        if error.code == 18:
            return diagnostic("credentials", "Atlas rejected authentication.")
        if error.code == 13:
            return diagnostic(
                "access_restricted", "Atlas denied the requested operation."
            )
    if isinstance(error, (httpx.TransportError, ConnectionFailure)):
        return diagnostic(
            "connection", "Connection failed; check network and service availability."
        )
    if isinstance(error, VerificationFailed):
        return diagnostic(
            "verification_failed",
            "Stored evidence did not pass integrity verification.",
        )
    # Do not infer subscriptions, access rights or authentication from arbitrary error text.
    return diagnostic(
        "engine_failed", "The extraction worker failed; inspect its safe job state."
    )

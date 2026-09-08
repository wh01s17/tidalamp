"""Retrying network calls to TIDAL.

tidalapi talks to the API with `requests` and raises whatever comes back. Most
failures we see in practice are transient — a dropped connection, a 5xx, a rate
limit — and a browser level or a track resolution that fails on the first try
usually works a second later. Anything that is *not* transient (a 401, a 404)
is raised immediately: retrying it only makes the user wait.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import requests

T = TypeVar("T")

ATTEMPTS = 3
BACKOFF = 0.6  # seconds, doubled on each retry

# 429 and 5xx are worth another go; a 4xx that is not 429 will not change.
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        return response is not None and response.status_code in _RETRY_STATUS
    return False


def with_retries(call: Callable[[], T], attempts: int = ATTEMPTS) -> T:
    """Run ``call``, retrying transient network failures with backoff."""
    delay = BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:
            if attempt == attempts or not _is_transient(exc):
                raise
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")

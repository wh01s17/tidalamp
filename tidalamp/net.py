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
from tidalapi.exceptions import TooManyRequests

T = TypeVar("T")

ATTEMPTS = 3
BACKOFF = 0.6  # seconds, doubled on each retry
MAX_RETRY_AFTER = 60  # a TUI should report a longer rate limit, not look frozen

# Seconds to connect, and to wait for each read. requests waits forever by
# default, and tidalapi never says otherwise: a request TIDAL does not answer
# held its worker for good, and never reached a retry.
TIMEOUT = (5, 20)

# 429 and 5xx are worth another go; a 4xx that is not 429 will not change.
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class TimeoutSession(requests.Session):
    """A requests session that gives up on a silent server after ``TIMEOUT``."""

    def request(self, method, url, *args, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT)
        return super().request(method, url, *args, **kwargs)


def _is_transient(exc: Exception, idempotent: bool = True) -> bool:
    # tidalapi translates an HTTP 429 into its own exception before callers
    # see it, so the HTTPError branch below can never recognize that response.
    if isinstance(exc, TooManyRequests):
        return True
    if not idempotent:
        # A write TIDAL may have applied before its answer got lost must not go
        # twice: that is a second playlist, or a batch of tracks doubled. Only
        # a refusal (the 429 above) or a request that never reached it counts.
        return isinstance(exc, requests.ConnectTimeout)
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        return response is not None and response.status_code in _RETRY_STATUS
    return False


def with_retries(
    call: Callable[[], T], attempts: int = ATTEMPTS, *, idempotent: bool = True
) -> T:
    """Run ``call``, retrying transient network failures with backoff.

    ``idempotent=False`` is for a write that must not happen twice: it is only
    retried when TIDAL surely did not apply it.
    """
    delay = BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:
            if attempt == attempts or not _is_transient(exc, idempotent):
                raise
            wait = delay
            if isinstance(exc, TooManyRequests) and exc.retry_after >= 0:
                if exc.retry_after > MAX_RETRY_AFTER:
                    raise
                wait = exc.retry_after
            time.sleep(wait)
            delay *= 2
    raise AssertionError("unreachable")

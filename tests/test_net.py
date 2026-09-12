import pytest
import requests
from tidalapi.exceptions import TooManyRequests

from tidalamp.net import BACKOFF, MAX_RETRY_AFTER, with_retries


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


def test_returns_the_value_without_retrying():
    calls = []
    assert with_retries(lambda: calls.append(1) or "ok") == "ok"
    assert len(calls) == 1


def test_retries_a_connection_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectionError("caída")
        return "ok"

    assert with_retries(flaky) == "ok"
    assert len(calls) == 3


def test_gives_up_after_the_last_attempt(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    calls = []

    def always_fails():
        calls.append(1)
        raise requests.Timeout()

    try:
        with_retries(always_fails)
    except requests.Timeout:
        pass
    else:
        raise AssertionError("debería haber propagado el Timeout")
    assert len(calls) == 3


def test_a_404_is_not_retried(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    calls = []

    def not_found():
        calls.append(1)
        raise _http_error(404)

    with pytest.raises(requests.HTTPError):
        with_retries(not_found)
    assert len(calls) == 1


def test_a_503_is_retried(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    calls = []

    def unavailable():
        calls.append(1)
        raise _http_error(503)

    with pytest.raises(requests.HTTPError):
        with_retries(unavailable)
    assert len(calls) == 3


def test_tidalapis_429_is_retried_after_the_server_delay(monkeypatch):
    sleeps = []
    monkeypatch.setattr("tidalamp.net.time.sleep", sleeps.append)
    calls = []

    def limited():
        calls.append(1)
        if len(calls) == 1:
            raise TooManyRequests(retry_after=30)
        return "ok"

    assert with_retries(limited) == "ok"
    assert len(calls) == 2
    assert sleeps == [30]


def test_a_429_without_retry_after_uses_the_normal_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr("tidalamp.net.time.sleep", sleeps.append)
    calls = []

    def limited():
        calls.append(1)
        if len(calls) == 1:
            raise TooManyRequests(retry_after=-1)
        return "ok"

    assert with_retries(limited) == "ok"
    assert sleeps == [BACKOFF]


def test_an_excessive_retry_after_is_reported_without_sleeping(monkeypatch):
    sleeps = []
    monkeypatch.setattr("tidalamp.net.time.sleep", sleeps.append)
    calls = []

    def limited():
        calls.append(1)
        raise TooManyRequests(retry_after=MAX_RETRY_AFTER + 1)

    with pytest.raises(TooManyRequests):
        with_retries(limited)
    assert len(calls) == 1
    assert sleeps == []


def test_a_write_is_not_retried_when_its_answer_is_lost(monkeypatch):
    """TIDAL may have applied it: a retry would be a second playlist."""
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    for lost in (requests.ReadTimeout(), requests.ConnectionError("cortada")):
        calls = []

        def write(error=lost, calls=calls):
            calls.append(1)
            raise error

        with pytest.raises(type(lost)):
            with_retries(write, idempotent=False)
        assert len(calls) == 1, type(lost).__name__


def test_a_write_that_never_reached_tidal_is_retried(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    for refusal in (requests.ConnectTimeout(), TooManyRequests(retry_after=-1)):
        calls = []

        def write(error=refusal, calls=calls):
            calls.append(1)
            if len(calls) == 1:
                raise error
            return "ok"

        assert with_retries(write, idempotent=False) == "ok"
        assert len(calls) == 2, type(refusal).__name__


def test_every_request_gets_a_timeout_unless_it_brings_its_own(monkeypatch):
    from tidalamp.net import TIMEOUT, TimeoutSession

    seen: list[object] = []

    def request(self, method, url, *args, **kwargs):
        seen.append(kwargs.get("timeout"))

    monkeypatch.setattr(requests.Session, "request", request)
    session = TimeoutSession()
    session.request("GET", "https://example.invalid")
    session.post("https://example.invalid", {})
    session.request("GET", "https://example.invalid", timeout=3)

    assert seen == [TIMEOUT, TIMEOUT, 3]

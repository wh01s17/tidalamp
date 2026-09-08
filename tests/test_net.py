import requests

from tidalamp.net import with_retries


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

    try:
        with_retries(not_found)
    except requests.HTTPError:
        pass
    assert len(calls) == 1


def test_a_503_is_retried(monkeypatch):
    monkeypatch.setattr("tidalamp.net.time.sleep", lambda _: None)
    calls = []

    def unavailable():
        calls.append(1)
        raise _http_error(503)

    try:
        with_retries(unavailable)
    except requests.HTTPError:
        pass
    assert len(calls) == 3

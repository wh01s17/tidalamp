"""Session loading and token refresh, without touching TIDAL."""

from __future__ import annotations

import pytest

from tidalamp import auth
from tidalamp.auth import NotLoggedIn, ensure_fresh, load_session


class FakeSession:
    """A tidalapi session with just the surface auth.py touches."""

    def __init__(
        self,
        *,
        valid: bool = True,
        refresh_token: str = "r",
        refreshes: bool = True,
        loads: bool = True,
        handshake: bool = True,
    ):
        self._valid = valid
        self.refresh_token = refresh_token
        self.token_type = "Bearer"
        self.access_token = "old"
        self.is_pkce = False
        self._refreshes = refreshes
        self._loads = loads
        self._handshake = handshake
        self.loaded_from = None
        self.saved_to = None
        self.refresh_calls: list[str] = []
        self.handshakes: list[tuple] = []

    def load_session_from_file(self, path):
        self.loaded_from = path
        if not self._loads:
            # This is what tidalapi really does with an expired token: it
            # validates it with a request and lets the 401 escape.
            raise RuntimeError("401 Client Error: Unauthorized")

    def check_login(self) -> bool:
        return self._valid

    def token_refresh(self, refresh_token: str) -> bool:
        self.refresh_calls.append(refresh_token)
        self.access_token = "new"
        return self._refreshes

    def load_oauth_session(self, token_type, access_token, refresh_token, is_pkce=False):
        self.handshakes.append((token_type, access_token, refresh_token, is_pkce))
        self._valid = self._handshake
        return self._handshake

    def save_session_to_file(self, path):
        self.saved_to = path


@pytest.fixture
def session_file(tmp_path, monkeypatch):
    path = tmp_path / "session.json"
    monkeypatch.setattr(auth, "SESSION_FILE", path)
    return path


def install(monkeypatch, session: FakeSession) -> FakeSession:
    monkeypatch.setattr(auth, "_new_session", lambda: session)
    return session


def test_no_file_at_all_says_to_log_in(session_file, monkeypatch):
    install(monkeypatch, FakeSession())
    with pytest.raises(NotLoggedIn, match="No hay sesión guardada"):
        load_session()


def test_a_valid_session_is_returned_untouched(session_file, monkeypatch):
    session_file.write_text("{}", encoding="utf-8")
    fake = install(monkeypatch, FakeSession(valid=True))

    assert load_session() is fake
    assert fake.loaded_from == session_file
    assert fake.refresh_calls == []


def test_an_expired_access_token_is_refreshed_instead_of_refused(
    session_file, monkeypatch
):
    """Opening the app the next day is the common case, not a dead session."""
    session_file.write_text("{}", encoding="utf-8")
    fake = install(monkeypatch, FakeSession(valid=False, refresh_token="r0"))

    assert load_session() is fake
    assert fake.refresh_calls == ["r0"]
    # token_refresh only swaps the access token; without redoing the handshake
    # the session has no user, no country code and no session id.
    assert fake.handshakes == [("Bearer", "new", "r0", False)]
    # The new access token has to reach disk, or every start refreshes again.
    assert fake.saved_to == session_file


def test_the_401_tidalapi_lets_escape_is_recovered_from(session_file, monkeypatch):
    """load_session_from_file validates the token and raises on an expired one."""
    session_file.write_text("{}", encoding="utf-8")
    fake = install(monkeypatch, FakeSession(valid=False, loads=False, refresh_token="r1"))

    assert load_session() is fake
    assert fake.refresh_calls == ["r1"]


def test_the_refresh_token_is_read_from_the_file_when_the_session_has_none(
    session_file, monkeypatch
):
    """A load that failed early leaves nothing on the session to refresh with."""
    session_file.write_text(
        '{"refresh_token": {"data": "del-fichero"}}', encoding="utf-8"
    )
    fake = install(monkeypatch, FakeSession(valid=False, loads=False, refresh_token=""))

    assert load_session() is fake
    assert fake.refresh_calls == ["del-fichero"]


def test_a_handshake_that_still_fails_says_to_log_in(session_file, monkeypatch):
    session_file.write_text("{}", encoding="utf-8")
    install(monkeypatch, FakeSession(valid=False, handshake=False))

    with pytest.raises(NotLoggedIn, match="no fue aceptada"):
        load_session()


def test_an_expired_session_with_nothing_to_refresh_says_to_log_in(
    session_file, monkeypatch
):
    session_file.write_text("{}", encoding="utf-8")
    install(monkeypatch, FakeSession(valid=False, refresh_token=""))

    with pytest.raises(NotLoggedIn, match="no hay refresh token"):
        load_session()


def test_a_refresh_that_fails_says_to_log_in(session_file, monkeypatch):
    session_file.write_text("{}", encoding="utf-8")
    install(monkeypatch, FakeSession(valid=False, refreshes=False))

    with pytest.raises(NotLoggedIn, match="No se pudo refrescar"):
        load_session()


def test_ensure_fresh_reports_whether_it_did_anything(session_file, monkeypatch):
    """Mid-session the handshake is already done; only the token needs swapping."""
    assert ensure_fresh(FakeSession(valid=True)) is False
    assert ensure_fresh(FakeSession(valid=False)) is True


def test_a_read_only_config_dir_does_not_stop_playback(session_file, monkeypatch):
    """The in-memory session is already valid again; the file is a nicety."""

    class Unwritable(FakeSession):
        def save_session_to_file(self, path):
            raise OSError("read-only")

    assert ensure_fresh(Unwritable(valid=False)) is True


class WritingSession(FakeSession):
    """Writes the way tidalapi does: a plain open("w"), under the umask."""

    def save_session_to_file(self, path):
        super().save_session_to_file(path)
        with open(path, "w") as handle:
            handle.write('{"refresh_token": {"data": "secret"}}')


def mode(path) -> int:
    return path.stat().st_mode & 0o777


def test_a_saved_session_is_readable_by_its_owner_alone(session_file, monkeypatch):
    import os

    old = os.umask(0o022)
    try:
        assert ensure_fresh(WritingSession(valid=False)) is True
    finally:
        os.umask(old)

    assert mode(session_file) == 0o600
    assert mode(session_file.parent) == 0o700


def test_a_session_left_readable_by_an_older_version_is_closed_on_load(
    session_file, monkeypatch
):
    session_file.write_text("{}", encoding="utf-8")
    session_file.chmod(0o644)
    session_file.parent.chmod(0o755)
    install(monkeypatch, FakeSession())

    load_session()

    assert mode(session_file) == 0o600
    assert mode(session_file.parent) == 0o700


def test_the_tidal_session_waits_for_an_answer_only_so_long():
    from tidalamp.net import TimeoutSession

    assert isinstance(auth._new_session().request_session, TimeoutSession)

"""TIDAL authentication via the device authorization flow.

No developer app registration is involved: tidalapi drives the same OAuth
device flow the official TV/desktop clients use. The user opens a link once,
approves it, and the refreshable session is cached on disk.
"""

from __future__ import annotations

import tidalapi

from .config import DEFAULT_QUALITY, SESSION_FILE, ensure_dirs


class NotLoggedIn(RuntimeError):
    pass


def _new_session() -> tidalapi.Session:
    config = tidalapi.Config(quality=tidalapi.Quality(DEFAULT_QUALITY))
    return tidalapi.Session(config)


def load_session() -> tidalapi.Session:
    """Return a logged-in session from the cached credentials."""
    if not SESSION_FILE.exists():
        raise NotLoggedIn("No hay sesión guardada. Ejecuta: tidalamp login")

    session = _new_session()
    session.load_session_from_file(SESSION_FILE)
    if not session.check_login():
        raise NotLoggedIn("La sesión guardada expiró. Ejecuta: tidalamp login")
    return session


def ensure_fresh(session: tidalapi.Session) -> bool:
    """Refresh the access token if it expired mid-session.

    TIDAL access tokens live a few hours, which is less than a listening
    session; without this the first API call after the expiry fails and the
    user sees an opaque error. The refresh token survives much longer, so we
    trade it for a new access token and re-save the file. Returns True when a
    refresh actually happened.
    """
    if session.check_login():
        return False
    refresh_token = getattr(session, "refresh_token", None)
    if not refresh_token:
        raise NotLoggedIn("La sesión expiró y no hay refresh token. Ejecuta: tidalamp login")
    if not session.token_refresh(refresh_token):
        raise NotLoggedIn("No se pudo refrescar la sesión. Ejecuta: tidalamp login")
    try:
        session.save_session_to_file(SESSION_FILE)
    except OSError:
        # A read-only config dir must not stop playback: the in-memory session
        # is already valid again.
        pass
    return True


def login(on_link) -> tidalapi.Session:
    """Run the device flow, calling ``on_link(url, expires_in)`` with the
    verification URL, then block until the user approves it."""
    ensure_dirs()
    session = _new_session()
    link, future = session.login_oauth()
    on_link(f"https://{link.verification_uri_complete}", link.expires_in)
    future.result()  # blocks until approved or the code expires
    session.save_session_to_file(SESSION_FILE)
    return session

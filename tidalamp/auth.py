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

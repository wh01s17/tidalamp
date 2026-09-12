"""TIDAL authentication via the device authorization flow.

No developer app registration is involved: tidalapi drives the same OAuth
device flow the official TV/desktop clients use. The user opens a link once,
approves it, and the refreshable session is cached on disk.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import tidalapi

from . import config as settings
from .config import SESSION_FILE, ensure_dirs
from .i18n import _
from .net import TimeoutSession

log = logging.getLogger("tidalamp.auth")


class NotLoggedIn(RuntimeError):
    pass


def _new_session() -> tidalapi.Session:
    config = tidalapi.Config(quality=tidalapi.Quality(settings.DEFAULT_QUALITY))
    session = tidalapi.Session(config)
    # tidalapi's own requests session waits forever for an answer; every
    # request, the login's included, goes through this one instead.
    session.request_session = TimeoutSession()
    return session


def _stored_refresh_token() -> str:
    """The refresh token straight out of the file, tidalapi's shape and ours."""
    try:
        raw = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    value = raw.get("refresh_token", "")
    # tidalapi wraps every field as {"data": …}; be tolerant of a flat one.
    if isinstance(value, dict):
        value = value.get("data", "")
    return value or ""


def _revive(session: tidalapi.Session) -> None:
    """Trade the refresh token for a new access token and finish the handshake.

    ``token_refresh`` only swaps the access token. The country code, session id
    and user come from ``load_oauth_session``, and on a session whose stored
    token had already expired that handshake never completed — so it has to be
    run again, or the session comes back half built and the first API call
    fails on ``session.user``.
    """
    refresh_token = getattr(session, "refresh_token", None) or _stored_refresh_token()
    if not refresh_token:
        raise NotLoggedIn(
            _("La sesión expiró y no hay refresh token. Ejecuta: tidalamp login")
        )

    try:
        refreshed = session.token_refresh(refresh_token)
    except Exception as exc:  # tidalapi raises AuthenticationError on a bad token
        raise NotLoggedIn(
            _("No se pudo refrescar la sesión ({error}). Ejecuta: tidalamp login").format(
                error=exc
            )
        ) from exc
    if not refreshed:
        raise NotLoggedIn(_("No se pudo refrescar la sesión. Ejecuta: tidalamp login"))

    if not session.load_oauth_session(
        session.token_type or "Bearer",
        session.access_token or "",
        refresh_token,
        is_pkce=getattr(session, "is_pkce", False),
    ):
        raise NotLoggedIn(
            _("La sesión refrescada no fue aceptada. Ejecuta: tidalamp login")
        )
    _save(session)


def _tighten(path: Path) -> None:
    """The session for its owner alone: the file 0600, its directory 0700.

    It holds the access and the refresh token, and tidalapi writes it with a
    plain ``open("w")``, so under the usual umask 022 it came out 0644:
    readable by every user on the machine.
    """
    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)


def _private(path: Path) -> None:
    """Make the file 0600 *before* tidalapi writes the tokens into it.

    Its ``open("w")`` keeps the mode of a file that already exists, so the
    tokens are never on disk readable by others, not even for a moment.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    _tighten(path)


def _save(session: tidalapi.Session) -> None:
    try:
        _private(SESSION_FILE)
        session.save_session_to_file(SESSION_FILE)
    except OSError:
        # A read-only config dir must not stop playback: the in-memory session
        # is already valid again.
        log.warning("no se pudo reescribir %s", SESSION_FILE)


def load_session() -> tidalapi.Session:
    """Return a logged-in session from the cached credentials.

    An access token lives a few hours, so the ordinary case for opening the app
    the next day is an expired one with a perfectly good refresh token sitting
    beside it. tidalapi does not handle that: ``load_session_from_file``
    validates the stored token with a request and lets the 401 escape as a bare
    ``HTTPError``. Catching it and refreshing is the difference between
    starting and showing the user a traceback; only a session with nothing
    left to refresh is really dead.
    """
    if not SESSION_FILE.exists():
        raise NotLoggedIn(_("No hay sesión guardada. Ejecuta: tidalamp login"))
    try:
        # A session saved by an older version is 0644; close it on the way in.
        _tighten(SESSION_FILE)
    except OSError:
        log.warning("no se pudieron ajustar los permisos de %s", SESSION_FILE)

    session = _new_session()
    try:
        session.load_session_from_file(SESSION_FILE)
    except Exception as exc:
        # The tokens are already on the session by the time it raises, so this
        # is recoverable. Anything genuinely dead fails again in _revive().
        log.info("la sesión guardada no validó (%s); se intenta refrescar", exc)

    if not session.check_login():
        _revive(session)
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
        raise NotLoggedIn(
            _("La sesión expiró y no hay refresh token. Ejecuta: tidalamp login")
        )
    if not session.token_refresh(refresh_token):
        raise NotLoggedIn(_("No se pudo refrescar la sesión. Ejecuta: tidalamp login"))
    _save(session)
    return True


def login(on_link) -> tidalapi.Session:
    """Run the device flow, calling ``on_link(url, expires_in)`` with the
    verification URL, then block until the user approves it."""
    ensure_dirs()
    session = _new_session()
    link, future = session.login_oauth()
    on_link(f"https://{link.verification_uri_complete}", link.expires_in)
    future.result()  # blocks until approved or the code expires
    _private(SESSION_FILE)
    session.save_session_to_file(SESSION_FILE)
    return session

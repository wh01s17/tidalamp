"""Offline mode: the player with local music only, and the way back to TIDAL.

Offline is a session that is not there: `auth.OfflineSession` stands where the
`tidalapi.Session` stood, and anything that asks TIDAL through it gets an
`auth.Offline` the existing error paths already put on the status line. What
this part adds is the switching: going offline keeps the real session in
memory, and coming back reuses it, or the one on disk, so turning the mode
off never asks for a new login. Only a session that is truly gone does, and
then «Iniciar sesión en TIDAL» in the settings runs the device flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import tidalapi

from . import auth, config, levels
from .i18n import _
from .workers import thread_worker

if TYPE_CHECKING:
    from .app import TidalAmp


class Connection:
    """Whether the player talks to TIDAL, and the switch between the two."""

    def __init__(self, app: TidalAmp) -> None:
        self.app = app
        # The real session while offline, to come back to without a login.
        self.kept: tidalapi.Session | None = None
        # A restore on its way, so a second toggle does not start another.
        self.restoring = False

    @property
    def node(self) -> TidalAmp:
        return self.app

    @property
    def offline(self) -> bool:
        return auth.is_offline(self.app.session)

    def announce(self) -> None:
        """What the status line says on a start without TIDAL."""
        if self.offline:
            self.app.status = _(
                "modo offline: sólo música local · o para iniciar sesión en TIDAL"
            )

    def go_offline(self) -> None:
        if self.offline:
            # A restore on its way finds the setting on again and stays put.
            return
        self.kept = self.app.session
        # Typed as the session it stands in for: everything that takes one
        # gets it, and fails with `auth.Offline` the moment it asks.
        self.app.session = cast("tidalapi.Session", auth.OfflineSession())
        # Every cached level was TIDAL's, or cut from what TIDAL answered.
        levels.forget()
        self.app.status = _("modo offline: sólo música local; la sesión se conserva")
        self._refresh_settings()

    def go_online(self) -> None:
        if not self.offline or self.restoring:
            return
        self.restoring = True
        self.app.status = _("recuperando la sesión de TIDAL…")
        self._restore_worker(self.kept)

    @thread_worker(group="connection")
    def _restore_worker(self, kept: tidalapi.Session | None) -> None:
        try:
            session = auth.restore(kept)
        except auth.NotLoggedIn as exc:
            self.app.call_from_thread(self._restore_failed, str(exc))
            return
        except Exception as exc:
            self.app.call_from_thread(
                self._restore_failed,
                _("TIDAL no contesta ({error})").format(error=exc),
            )
            return
        self.app.call_from_thread(self._restored, session)

    def _restored(self, session: tidalapi.Session) -> None:
        """The session is back; TIDAL too, unless offline was asked for again
        while it was on its way. Then it waits in memory, like any kept one."""
        if config.OFFLINE:
            self.restoring = False
            self.kept = session
            self.app.status = _("modo offline: sólo música local; la sesión se conserva")
            self._refresh_settings()
            return
        self.online(session)

    def _restore_failed(self, reason: str) -> None:
        """Still offline, and says what to do about it."""
        self.restoring = False
        self.app.status = _("sigue en modo offline: {reason}").format(reason=reason)
        self._refresh_settings()

    def online(self, session: tidalapi.Session, message: str = "") -> None:
        """Back on TIDAL, with ``session``: restored, or just logged in."""
        self.restoring = False
        self.kept = None
        self.app.session = session
        levels.forget()
        if config.OFFLINE:
            # A login from offline mode is the user asking for TIDAL back.
            config.set_option("offline", False)
        self.app.status = message or _("sesión de TIDAL recuperada")
        self._refresh_settings()

    def _refresh_settings(self) -> None:
        """The settings window, if open, shows the login row only offline."""
        from .screens import ConfigScreen

        for screen in self.app.screen_stack:
            if isinstance(screen, ConfigScreen):
                screen.refresh_rows()

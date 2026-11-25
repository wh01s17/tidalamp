"""Logging in to TIDAL from inside the player: the device flow in a window."""

from __future__ import annotations

import threading
import time

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import auth, links
from ..i18n import _


class LoginScreen(ModalScreen[object]):
    """The link and the code to approve, and a wait until TIDAL says yes.

    What `tidalamp login` does in the terminal, without leaving the player:
    offline mode is where this is offered, and closing the app to log in would
    stop the music. Dismisses with the new `tidalapi.Session`, or ``None``
    when the window is closed, the link expires or TIDAL cannot be reached.

    The wait is one check at a time (`auth.finish_login`), so esc is heard
    between two of them and the worker does not outlive the window by more
    than one of TIDAL's polling intervals.

    The link cannot be left to the terminal: the player owns the mouse, so
    neither its selection nor its click on a URL reaches the text. ↵ or a
    click opens it in the browser and `c` copies it (`links.py`); it is still
    drawn as a real hyperlink for the terminals that follow one with a
    modifier held.
    """

    BINDINGS = [
        Binding("escape", "close", _("cerrar")),
        Binding("enter,o", "open_link", _("abrir"), show=False),
        Binding("c", "copy_link", _("copiar"), show=False),
    ]

    # The least time between two checks, whatever TIDAL's interval says.
    MIN_WAIT = 0.2

    def __init__(self) -> None:
        super().__init__()
        self._stop = threading.Event()
        self._hint = _(" ↵ abrir en el navegador   c copiar   esc cancelar")
        self._message = _("pidiendo un enlace a TIDAL…")
        self._url = ""
        self._code = ""
        self._minutes = 0
        # What ↵ or c just did, under the link.
        self._feedback = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-box"):
            yield Static(_("INICIAR SESIÓN EN TIDAL"), id="choice-title", markup=False)
            yield Static(self._message, id="choice-message", markup=False)
            yield Static(self._hint, id="choice-hint", markup=False)

    def on_mount(self) -> None:
        self._fit(self._message)
        self._flow()

    def on_unmount(self) -> None:
        self._stop.set()

    def _fit(self, message: str) -> None:
        widest = max(
            [cell_len(line) + 2 for line in message.splitlines()]
            + [cell_len(self._hint), 40]
        )
        self.query_one("#choice-box").styles.width = widest + 8

    def _say(self, message: str) -> None:
        """A plain message instead of the link: a failure, or the expiry."""
        self._url = ""
        self._message = message
        self.query_one("#choice-message", Static).update(message)
        self._fit(message)

    def _show_link(self, url: str, code: str, minutes: int) -> None:
        self._url, self._code, self._minutes = url, code, minutes
        self._draw_link()

    def _draw_link(self) -> None:
        text = Text(_("Abre este enlace y autoriza el acceso:") + "\n\n  ")
        # A real hyperlink (OSC 8), underlined so it reads as one.
        text.append(self._url, style=Style(link=self._url, underline=True))
        text.append(
            "\n\n"
            + _("Código: {code} · caduca en {minutes} minutos.").format(
                code=self._code, minutes=self._minutes
            )
            + "\n"
            + (self._feedback or _("Esperando la autorización…"))
        )
        self._message = text.plain
        self.query_one("#choice-message", Static).update(text)
        self._fit(self._message)

    def action_open_link(self) -> None:
        if not self._url:
            return
        if links.open_url(self._url):
            self._feedback = _("Abierto en el navegador. Esperando la autorización…")
        else:
            self._feedback = _("No se pudo abrir el navegador: c copia el enlace.")
        self._draw_link()

    def action_copy_link(self) -> None:
        if not self._url:
            return
        if not links.copy_text(self._url):
            # The terminal's clipboard (OSC 52), when the system has no tool.
            self.app.copy_to_clipboard(self._url)
        self._feedback = _("Enlace copiado. Esperando la autorización…")
        self._draw_link()

    def on_click(self, event: events.Click) -> None:
        """A click on the window does what ↵ does; one on the player around
        it does nothing."""
        if event.widget is not None and event.widget is not self:
            self.action_open_link()

    @work(thread=True, exclusive=True, group="login")
    def _flow(self) -> None:
        try:
            session, link = auth.start_login()
        except Exception as exc:
            self._from_thread(
                self._say, _("no se pudo hablar con TIDAL: {error}").format(error=exc)
            )
            return
        url = f"https://{link.verification_uri_complete}"
        self._from_thread(
            self._show_link, url, str(link.user_code), int(link.expires_in / 60)
        )
        deadline = time.monotonic() + link.expires_in
        while not self._stop.is_set():
            if time.monotonic() > deadline:
                self._from_thread(
                    self._say,
                    _("El enlace caducó sin autorizarse. Cierra y vuelve a intentarlo."),
                )
                return
            started = time.monotonic()
            try:
                approved = auth.finish_login(session, link)
            except Exception as exc:
                self._from_thread(
                    self._say,
                    _("TIDAL no aceptó el inicio de sesión: {error}").format(error=exc),
                )
                return
            if approved:
                self._from_thread(self.dismiss, session)
                return
            # TIDAL's interval between two checks, whatever the check itself
            # took: a «not yet» that came back at once would otherwise make
            # this a loop that spins. Waited on the stop, so esc cuts it short.
            spent = time.monotonic() - started
            self._stop.wait(max(self.MIN_WAIT, float(link.interval) - spent))

    def _from_thread(self, callback, *args) -> None:
        """Back on the UI loop, unless the window is already gone."""
        if not self._stop.is_set():
            self.app.call_from_thread(callback, *args)

    def action_close(self) -> None:
        self._stop.set()
        self.dismiss(None)

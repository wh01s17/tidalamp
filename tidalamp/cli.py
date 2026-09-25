"""Command line entry point."""

from __future__ import annotations

import contextlib
import io
import sys

import typer

from . import about, desktop
from . import config as settings
from .auth import NotLoggedIn, load_session
from .auth import login as do_login
from .config import LOG_FILE, setup_logging
from .i18n import _
from .player import Mpv, MpvNotFound

app = typer.Typer(
    add_completion=False, help=_("Cliente TIDAL para terminal con interfaz retro.")
)


@app.command(help=_("Autoriza el cliente con tu cuenta TIDAL (device flow)."))
def login() -> None:
    """Autoriza el cliente con tu cuenta TIDAL (device flow)."""

    def show(url: str, expires_in: float) -> None:
        typer.echo(_("Abre esta URL y autoriza el acceso:\n"))
        typer.secho(f"    {url}\n", fg=typer.colors.GREEN, bold=True)
        typer.echo(
            _("Caduca en {minutes} minutos. Esperando…").format(
                minutes=int(expires_in / 60)
            )
        )

    session = do_login(show)
    user_id = getattr(session.user, "id", "?")
    typer.secho(
        _("Sesión guardada para {user_id}.").format(user_id=user_id),
        fg=typer.colors.GREEN,
    )


@app.command(help=_("Lanza la interfaz."))
def tui() -> None:
    """Lanza la interfaz."""
    from .app import TidalAmp

    if settings.DEBUG:
        typer.echo(_("Debug log en {path}").format(path=LOG_FILE))

    try:
        session = load_session()
    except NotLoggedIn as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    _offer_installs()
    try:
        mpv = Mpv()
    except MpvNotFound as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    try:
        application = TidalAmp(session, mpv)
        # Only once logged in and able to play: a launcher that opens
        # straight into «log in first» is not worth offering.
        application.offer_launcher = desktop.offer()
        application.run()
    finally:
        mpv.close()


def _offer_installs(platform: str = sys.platform) -> None:
    """On Windows, offer to install with winget what is missing: mpv, without
    which nothing plays, every time; cava, the real spectrum, once.

    Asked here, in the console, before the interface takes it over: winget
    shows its progress there, and the mpv installer asks for elevation.
    Linux has no such thing: the message says which command to run.
    """
    if platform != "win32" or sys.stdin is None or not sys.stdin.isatty():
        return
    from . import spectrum
    from .backends.windows import mpv as windows_mpv
    from .backends.windows import winget

    if not winget.available():
        return

    def offer(package: str) -> bool:
        if not typer.confirm(_("¿Instalarlo ahora con winget?"), default=True):
            return False
        typer.echo(" ".join(winget.command(package)))
        winget.install(package)
        return True

    if not settings.MPV_PATH and windows_mpv.find() is None:
        typer.secho(
            _("mpv no está instalado, y sin él no suena nada."),
            fg=typer.colors.YELLOW,
        )
        offer("mpv")
    if not spectrum.available() and not winget.offered("cava"):
        typer.echo(
            _(
                "cava no está instalado: sin él, el visualizador mide el nivel "
                "en lugar de dibujar el espectro."
            )
        )
        winget.mark_offered("cava")
        offer("cava")


@app.command(
    "config",
    help=_("Muestra la configuración efectiva y crea el fichero si no existe."),
)
def show_config() -> None:
    """Muestra la configuración efectiva y crea el fichero si no existe."""
    from .app import DEFAULT_KEYS, keys_for, unknown_key_actions

    path = settings.write_template()
    typer.echo(_("Fichero: {path}").format(path=path))
    typer.echo("")
    typer.echo(_("Ajustes en uso:"))
    typer.echo(f"  quality     {settings.DEFAULT_QUALITY}")
    typer.echo(f"  artwork     {settings.ARTWORK}")
    typer.echo(f"  theme       {settings.THEME}")
    typer.echo(f"  palette     {settings.PALETTE}")
    typer.echo(f"  arrangement {settings.ARRANGEMENT}")
    typer.echo(f"  cover_shape {settings.COVER_SHAPE}")
    typer.echo(f"  autoplay    {settings.AUTOPLAY}")
    typer.echo(f"  backdrop    {settings.BACKDROP}")
    typer.echo(f"  visualizer  {settings.VISUALIZER}")
    typer.echo(f"  debug       {str(settings.DEBUG).lower()}")

    changed = {a: keys_for(a) for a in DEFAULT_KEYS if keys_for(a) != DEFAULT_KEYS[a]}
    typer.echo("")
    if changed:
        typer.echo(_("Teclas cambiadas:"))
        for action, key in changed.items():
            typer.echo(
                _("  {action:<16} {key}   (por defecto {default})").format(
                    action=action, key=key, default=DEFAULT_KEYS[action]
                )
            )
    else:
        typer.echo(_("Teclas: todas por defecto."))

    unknown = unknown_key_actions()
    if unknown:
        typer.secho(
            "\n"
            + _("Estas acciones de [keys] no existen y se ignoran: {actions}").format(
                actions=", ".join(unknown)
            ),
            fg=typer.colors.YELLOW,
        )


@app.command(help=_("Busca pistas y muestra sus IDs (útil para scripts)."))
def search(query: str, limit: int = 10) -> None:
    """Busca pistas y muestra sus IDs (útil para scripts)."""
    session = load_session()
    results = session.search(query, limit=limit)
    for track in results.get("tracks", []):
        artist = getattr(track.artist, "name", "")
        typer.echo(f"{track.id:>10}  {artist} - {track.name}")


def _print_version(value: bool) -> None:
    """Answer `-v` and quit before anything else is asked of the process.

    Eager, so it never depends on a session, on mpv, or on the terminal being
    big enough: `tidalamp --version` is the thing a user is told to paste into
    a bug report, and it has to work on the install that is broken.
    """
    if value:
        typer.echo(f"tidalamp {about.version()}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def launch(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_print_version,
        is_eager=True,
        help=_("Muestra la versión y sale."),
    ),
) -> None:
    """Open the player when no explicit subcommand was given."""
    if ctx.invoked_subcommand is None:
        tui()


def _utf8_output() -> None:
    """Windows writes a redirected stdout in the ANSI code page, where the
    «», ñ and — of every message come out broken. A console already gets
    UTF-8, and so does Linux, which is left as it is."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8")


def main() -> None:
    _utf8_output()
    setup_logging()
    try:
        app()
    except NotLoggedIn as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        sys.exit(1)


if __name__ == "__main__":
    main()

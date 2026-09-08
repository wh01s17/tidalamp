"""Command line entry point."""

from __future__ import annotations

import os
import sys

import typer

from . import config as settings
from .auth import NotLoggedIn, load_session
from .auth import login as do_login
from .config import LOG_FILE, setup_logging
from .player import Mpv, MpvNotFound

app = typer.Typer(add_completion=False, help="Cliente TIDAL con interfaz estilo Winamp.")


@app.command()
def login() -> None:
    """Autoriza el cliente con tu cuenta TIDAL (flujo de dispositivo)."""

    def show(url: str, expires_in: float) -> None:
        typer.echo("Abre esta URL y autoriza el acceso:\n")
        typer.secho(f"    {url}\n", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"Caduca en {int(expires_in / 60)} minutos. Esperando…")

    session = do_login(show)
    typer.secho(f"Sesión guardada para {session.user.id}.", fg=typer.colors.GREEN)


@app.command()
def tui() -> None:
    """Lanza la interfaz."""
    from .app import TidalAmp

    if os.environ.get("TIDALAMP_DEBUG"):
        typer.echo(f"Registro de depuración en {LOG_FILE}")

    try:
        session = load_session()
    except NotLoggedIn as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1)

    try:
        mpv = Mpv()
    except MpvNotFound as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1)

    try:
        TidalAmp(session, mpv).run()
    finally:
        mpv.close()


@app.command("config")
def show_config() -> None:
    """Muestra la configuración efectiva y crea el fichero si no existe."""
    from .app import DEFAULT_KEYS, keys_for, unknown_key_actions

    path = settings.write_template()
    typer.echo(f"Fichero: {path}")
    typer.echo("")
    typer.echo("Ajustes en uso:")
    typer.echo(f"  quality  {settings.DEFAULT_QUALITY}")
    typer.echo(f"  artwork  {settings.ARTWORK}")
    typer.echo(f"  debug    {str(settings.DEBUG).lower()}")

    changed = {a: keys_for(a) for a in DEFAULT_KEYS if keys_for(a) != DEFAULT_KEYS[a]}
    typer.echo("")
    if changed:
        typer.echo("Teclas cambiadas:")
        for action, key in changed.items():
            typer.echo(f"  {action:<16} {key}   (por defecto {DEFAULT_KEYS[action]})")
    else:
        typer.echo("Teclas: todas por defecto.")

    unknown = unknown_key_actions()
    if unknown:
        typer.secho(
            "\nEstas acciones de [keys] no existen y se ignoran: "
            + ", ".join(unknown),
            fg=typer.colors.YELLOW,
        )


@app.command()
def search(query: str, limit: int = 10) -> None:
    """Busca pistas y muestra sus IDs (útil para scripts)."""
    session = load_session()
    results = session.search(query, limit=limit)
    for track in results.get("tracks", []):
        typer.echo(f"{track.id:>10}  {track.artist.name} - {track.name}")


def main() -> None:
    setup_logging()
    try:
        app()
    except NotLoggedIn as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        sys.exit(1)


if __name__ == "__main__":
    main()

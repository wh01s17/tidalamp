"""What the app tests share: a fake mpv, the runtime isolation, and the
small readers and builders they all use. Imported by name: `tests/` is not a
package, and pytest puts it on the path."""

from __future__ import annotations

import asyncio

from tidalamp import app as app_module
from tidalamp import audio as audio_module
from tidalamp.app import BrowserScreen, ConfigScreen, RowList, TidalAmp
from tidalamp.artwork import Cover, Protocol
from tidalamp.library import Row
from tidalamp.player import Mpv
from tidalamp.queue import Entry, Queue
from tidalamp.settings import Settings


async def settle(pilot, done, tries: int = 100) -> None:
    """Pump the event loop until a worker's result has landed."""
    for _ in range(tries):
        await pilot.pause()
        if done():
            # The callback can make `done` true just before the thread worker
            # itself returns. Waiting for the Worker prevents asyncio.run()
            # from closing its executor while call_from_thread() is in flight.
            await pilot.app.workers.wait_for_complete()
            return
        await asyncio.sleep(0.01)
    raise AssertionError("el worker no terminó")


class FakeMpv:
    alive = True
    position = 0.0
    duration = 0.0
    paused = False
    idle = True
    speed = 1.0

    def __init__(self) -> None:
        self.filter_calls: list[tuple[str, str | None]] = []
        self.seek_calls: list[tuple[float, str]] = []
        self.loaded: str | None = None
        self._volume = 100

    @property
    def volume(self) -> int:
        return self._volume

    @volume.setter
    def volume(self, value: int) -> None:
        # Same ceiling as the real player: the app relies on it to clamp.
        self._volume = max(0, min(Mpv.VOLUME_MAX, value))

    def load(self, url: str) -> None:
        self.loaded = url

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def stop(self) -> None:
        self.paused = False
        self.idle = True
        self.loaded = None

    def seek(self, seconds: float, mode: str = "absolute") -> None:
        self.seek_calls.append((seconds, mode))

    def set_filter(self, label: str, graph: str | None) -> None:
        self.filter_calls.append((label, graph))

    def rms(self) -> float:
        return -91.0

    def close(self) -> None:
        pass


def isolate_runtime(monkeypatch) -> None:
    async def no_mpris(self) -> None:
        return None

    def probe_audio(screen) -> None:
        """Resolve the fake audio stack inline, without a closing-loop race."""
        sink = audio_module.sink()
        allowed = audio_module.allowed_rates()
        screen._probed(sink, allowed, audio_module.hardware_rates(sink.name))

    monkeypatch.setattr(Queue, "load", lambda self: False)
    monkeypatch.setattr(Queue, "save", lambda self: None)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(TidalAmp, "_start_spectrum", lambda self: None)
    monkeypatch.setattr(TidalAmp, "_start_mpris", no_mpris)
    # The app-level audio worker is unrelated to these UI tests. Letting it
    # race the end of run_test() can leave call_from_thread() waiting on an
    # event loop that is already closing, which makes asyncio.run() wait for
    # its default executor indefinitely on Python 3.14.
    monkeypatch.setattr(TidalAmp, "_refresh_sink_worker", lambda self: None)
    monkeypatch.setattr(ConfigScreen, "_probe", probe_audio)
    monkeypatch.setattr(audio_module, "sink", lambda: audio_module.Sink())
    monkeypatch.setattr(audio_module, "allowed_rates", lambda: ())
    monkeypatch.setattr(audio_module, "hardware_rates", lambda name: ())


# The transport is drawn as boxes three rows tall; row 1 carries the labels.
LABEL_ROW = 1


def transport(application, half: str = "play") -> str:
    return application.query_one(f"#transport-{half}").render_line(LABEL_ROW).text


def use_theme(monkeypatch, name: str) -> None:
    """Both layouts come out of the same widgets; pick one for a test.

    `config.THEME` is a module global, so it is set through monkeypatch and
    not by hand: conftest restores it either way, but this keeps the reason
    next to the test that needs it.
    """
    monkeypatch.setattr(app_module.config, "THEME", name)


def lit(application) -> dict[str, bool]:
    """Whether each state button is drawn on the accent, by its glyph."""
    accent = application.tidalamp_palette["accent"].lower()
    found = {}
    for segment in application.query_one("#transport-play").render_line(LABEL_ROW):
        for glyph in ("⇄", "↻"):
            if glyph in segment.text:
                colour = segment.style.bgcolor
                found[glyph] = colour is not None and colour.name.lower() == accent
    return found


# ---------------------------------------------------------------------- artwork


def a_cover(protocol=Protocol.BLOCKS, escape=""):
    # Four samples per cell: two columns and two rows for a single cell.
    pixels = (
        ((255, 0, 0), (0, 255, 0), (0, 0, 0), (0, 0, 0)),
        ((0, 0, 255), (255, 255, 0), (0, 0, 0), (0, 0, 0)),
    )
    return Cover(
        cols=2,
        rows=1,
        protocol=protocol,
        pixels=pixels if protocol is Protocol.BLOCKS else None,
        escape=escape,
    )


# -------------------------------------------------------- el filtro del nivel


def library_rows() -> list[Row]:
    """A level with two tracks, a container and a page that is not loaded."""
    schism = Entry(id=1, title="Schism", artist="TOOL", album="Lateralus")
    sober = Entry(id=2, title="Sober", artist="TOOL", album="Undertow")
    return [
        Row(label=schism.label, detail="6:47", entry=schism),
        Row(label=sober.label, detail="5:06", entry=sober),
        Row(label="Sinfonía nº 9", detail="4 pistas", key="playlist:9"),
        Row(label="más…", detail="siguientes 100", more=lambda: [Row(label="Ænema")]),
    ]


def open_browser(application, rows=None):
    level = rows if rows is not None else library_rows()
    application.push_screen(BrowserScreen("MI BIBLIOTECA", lambda: level))


async def type_into_filter(pilot, text: str) -> None:
    for character in text:
        await pilot.press(character)
    await pilot.pause()


def visible_labels(screen) -> list[str]:
    return [row.label for row in screen.query_one(RowList).rows]


# ---------------------------------------------------------------- track menu


def track_rows() -> list[Row]:
    return [
        Row(label=name, detail="1:40", entry=Entry(id=i, title=name, artist="TOOL"))
        for i, name in enumerate(("A", "B", "C"))
    ]


def open_menu_on_b(application, rows):
    """Push the browser wired to the app, exactly as `/` and `l` do."""
    application.push_screen(
        BrowserScreen("BUSCAR: x", lambda: rows), application._browser_result
    )


def a_queue(application, *titles: str) -> None:
    """Fill the queue with one entry per title and put it on screen."""
    application.queue.replace(
        [Entry(id=i, title=t, artist="TOOL", duration=60) for i, t in enumerate(titles)],
        start=-1,
    )
    application._sync_queue()


def queue_lines(application) -> list[str]:
    """What the playlist widget is actually drawing, line by line."""
    playlist = application.query_one("#playlist", RowList)
    return [playlist.render_line(y).text.rstrip() for y in range(playlist.size.height)]


def a_deftones_track() -> Entry:
    return Entry(
        id=1,
        title="Entombed",
        artist="Deftones",
        album="Around the Fur",
        year=1997,
        duration=299,
    )


# ----------------------------------------------------------------- settings


def isolate_config(monkeypatch, tmp_path):
    """Point the config file at a temp one and drop every override."""
    path = tmp_path / "config.toml"
    monkeypatch.setattr(app_module.config, "CONFIG_FILE", path)
    for variable in app_module.config.ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    app_module.config.reload()
    return path


def config_row(screen, label: str) -> int:
    """Find a settings row by its label.

    By index, every test that touched the settings screen broke the day a row
    was inserted above the one it meant. The label is what the user is
    looking at anyway.
    """
    for index, option in enumerate(screen._rows):
        if option.label == label:
            return index
    raise AssertionError(f"no hay una fila «{label}»")


def config_text(application) -> str:
    body = application.screen.query_one("#config-list")
    return "\n".join(body.render_line(y).text for y in range(body.size.height))


def _grounds(widget, y: int) -> set[str]:
    """The background colours a list line is drawn on."""
    return {
        segment.style.bgcolor.name
        for segment in widget.render_line(y)
        if segment.style and segment.style.bgcolor
    }

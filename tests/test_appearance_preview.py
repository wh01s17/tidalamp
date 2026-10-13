"""The four appearance choices share a preview and a commit boundary."""

from __future__ import annotations

import asyncio

import pytest
from app_helpers import FakeMpv, config_row, isolate_config, isolate_runtime, wait_for
from textual.widgets import Static

from tidalamp import artwork, config
from tidalamp.app import ConfigScreen, TidalAmp
from tidalamp.screens.appearance_preview import (
    MIN_PREVIEW_WIDTH,
    Appearance,
    AppearancePreviewScreen,
    render_player,
)


def _preview_text(screen: AppearancePreviewScreen) -> str:
    widget = screen.query_one("#appearance-preview-player", Static)
    return "\n".join(widget.render_line(y).text for y in range(widget.size.height))


@pytest.mark.parametrize(
    ("label", "key", "value"),
    [
        ("Tema", "theme", "retro"),
        ("Paleta", "palette", "black"),
        ("Fondo de la cola", "backdrop", "pirata"),
        ("Disposición", "arrangement", "split"),
    ],
)
def test_preview_cancels_without_touching_the_player_or_file(
    monkeypatch, tmp_path, label, key, value
):
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(170, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application.setting_changes.apply)
            application.push_screen(screen)
            await pilot.pause()
            before = (config.THEME, config.PALETTE, config.BACKDROP, config.ARRANGEMENT)
            classes = application.query_one("#main").classes.copy()
            initial_file = path.read_text() if path.exists() else None

            screen.cursor = config_row(screen, label)
            await pilot.press("enter")
            preview = application.screen
            assert isinstance(preview, AppearancePreviewScreen)
            preview.cursor = preview.choices.index(value)
            preview.draft = preview.original.choosing(key, value)
            preview._redraw()
            await pilot.pause()
            assert value == getattr(preview.draft, key)
            assert _preview_text(preview).strip()
            assert before == (
                config.THEME,
                config.PALETTE,
                config.BACKDROP,
                config.ARRANGEMENT,
            )
            assert application.query_one("#main").classes == classes
            assert (path.read_text() if path.exists() else None) == initial_file

            if key == "palette":
                await pilot.click("#appearance-preview-cancel")
            else:
                await pilot.press("escape")
            await pilot.pause()
            assert application.screen is screen
            assert before == (
                config.THEME,
                config.PALETTE,
                config.BACKDROP,
                config.ARRANGEMENT,
            )
            assert (path.read_text() if path.exists() else None) == initial_file

    asyncio.run(scenario())


def test_paired_theme_preview_and_apply(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(170, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application.setting_changes.apply)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            preview = application.screen
            assert isinstance(preview, AppearancePreviewScreen)
            preview.cursor = preview.choices.index("pirata")
            preview.draft = preview.original.choosing("theme", "pirata")
            preview._redraw()
            await pilot.pause()
            assert (preview.draft.palette, preview.draft.backdrop) == ("pirata", "pirata")
            assert "TIDAL AMP" in _preview_text(preview)
            assert config.THEME == "quattro"

            await pilot.click("#appearance-preview-apply")
            await pilot.pause()
            assert application.screen is screen
            assert (config.THEME, config.PALETTE, config.BACKDROP) == (
                "pirata",
                "pirata",
                "pirata",
            )
            saved = config.read_file(path)
            assert (saved["theme"], saved["palette"], saved["backdrop"]) == (
                "pirata",
                "pirata",
                "pirata",
            )
            assert application.query_one("#main").has_class("pirata")

    asyncio.run(scenario())


def test_split_preview_explains_the_terminal_limit(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario(size: tuple[int, int]) -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=size) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application.setting_changes.apply)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Disposición")
            await pilot.press("enter", "down")
            preview = application.screen
            assert isinstance(preview, AppearancePreviewScreen)
            options = preview.query_one("#appearance-preview-options", Static)
            stage = preview.query_one("#appearance-preview-player", Static)
            if size[0] < MIN_PREVIEW_WIDTH:
                stage_container = preview.query_one("#appearance-preview-stage")
                assert stage_container.styles.display == "none"
                assert f"{MIN_PREVIEW_WIDTH} columnas" in str(
                    preview.query_one("#appearance-preview-note", Static).content
                )
            else:
                assert stage.region.x >= options.region.right
                assert "Pista de ejemplo" in _preview_text(preview)
            note = preview.query_one("#appearance-preview-note", Static).content
            if size[0] >= MIN_PREVIEW_WIDTH:
                assert ("160×26" in str(note)) == (size[0] < 160 or size[1] < 26)
            await pilot.press("escape")

    asyncio.run(scenario((60, 18)))
    asyncio.run(scenario((MIN_PREVIEW_WIDTH - 1, 26)))
    asyncio.run(scenario((MIN_PREVIEW_WIDTH, 26)))
    asyncio.run(scenario((170, 34)))


def test_backdrop_preview_uses_the_picture_when_pillow_is_available(monkeypatch):
    pytest.importorskip("PIL")
    state = Appearance("pirata", "pirata", "pirata", "stacked")
    painted = render_player(state, 64, 18, split=False)
    assert any("rgb(" in str(span.style) for span in painted.spans)


def test_backdrop_preview_works_without_pillow(monkeypatch):
    state = Appearance("pirata", "pirata", "pirata", "stacked")
    monkeypatch.setattr(artwork, "_emblem_image", lambda path: None)
    without_pillow = render_player(state, 64, 18, split=False)
    assert "BITÁCORA" in without_pillow.plain
    assert not any("rgb(" in str(span.style) for span in without_pillow.spans)


def test_opening_the_current_theme_keeps_independent_palette_and_backdrop():
    current = Appearance("pirata", "black", "none", "stacked")
    assert current.choosing("theme", "pirata") == current
    assert current.choosing("theme", "bosque") == Appearance(
        "bosque", "bosque", "bosque", "stacked"
    )


@pytest.mark.parametrize("size", [(60, 18), (170, 34)])
def test_arrangement_applies_only_after_confirmation(monkeypatch, tmp_path, size):
    isolate_runtime(monkeypatch)
    path = isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=size) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application.setting_changes.apply)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Disposición")
            await pilot.press("enter", "down")
            preview = application.screen
            assert isinstance(preview, AppearancePreviewScreen)
            assert config.ARRANGEMENT == "stacked"
            assert not application.query_one("#main").has_class("split")
            await pilot.press("enter")
            await pilot.pause()
            assert config.ARRANGEMENT == "split"
            assert application.query_one("#main").has_class("split") == (size[0] >= 160)
            assert config.read_file(path)["arrangement"] == "split"

    asyncio.run(scenario())


def test_preview_appears_and_hides_when_terminal_crosses_minimum(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(MIN_PREVIEW_WIDTH - 1, 26)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application.setting_changes.apply)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            preview = application.screen
            assert isinstance(preview, AppearancePreviewScreen)
            stage = preview.query_one("#appearance-preview-stage")
            assert stage.styles.display == "none"

            await pilot.resize_terminal(MIN_PREVIEW_WIDTH, 26)
            await wait_for(
                pilot,
                lambda: (
                    stage.styles.display != "none"
                    and "Pista de ejemplo" in _preview_text(preview)
                ),
            )

            await pilot.resize_terminal(MIN_PREVIEW_WIDTH - 1, 26)
            await wait_for(pilot, lambda: stage.styles.display == "none")

    asyncio.run(scenario())


def test_clicking_a_choice_moves_the_preview_cursor(monkeypatch, tmp_path):
    isolate_runtime(monkeypatch)
    isolate_config(monkeypatch, tmp_path)

    async def scenario() -> None:
        application = TidalAmp(object(), FakeMpv())
        async with application.run_test(size=(170, 34)) as pilot:
            await pilot.pause()
            screen = ConfigScreen(application.setting_changes.apply)
            application.push_screen(screen)
            await pilot.pause()
            screen.cursor = config_row(screen, "Tema")
            await pilot.press("enter")
            preview = application.screen
            assert isinstance(preview, AppearancePreviewScreen)
            await pilot.click("#appearance-preview-options", offset=(4, 2))
            await pilot.pause()
            assert preview.cursor == 1
            assert preview.draft.theme == "retro"
            assert config.THEME == "quattro"

    asyncio.run(scenario())

"""The config file, and the precedence between it, the environment and defaults."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tidalamp import config


def fresh(monkeypatch, tmp_path, contents: str | None = None, **env: str):
    """Load a private copy of config.py against a temporary config file."""
    path = tmp_path / "config.toml"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")

    for name in config.ENV_VARS.values():
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path.parent))

    spec = importlib.util.spec_from_file_location("config_probe", Path(config.__file__))
    module = importlib.util.module_from_spec(spec)
    module.CONFIG_FILE = path  # set before exec so read_file() sees it
    spec.loader.exec_module(module)
    # exec_module reassigns CONFIG_FILE from XDG; re-read against ours.
    module.FILE = module.read_file(path)
    module.DEFAULT_QUALITY = module.setting(
        "quality", "TIDALAMP_QUALITY", "HI_RES_LOSSLESS"
    )
    module.ARTWORK = module.setting("artwork", "TIDALAMP_ART", "auto")
    module.LANGUAGE = module.setting("language", "TIDALAMP_LANG", "auto")
    module.THEME = module.setting("theme", "TIDALAMP_THEME", "quattro")
    module.PALETTE = module.setting("palette", "TIDALAMP_PALETTE", "auto")
    module.COLUMNS = module.columns()
    module.DEBUG = module.flag("debug", "TIDALAMP_DEBUG")
    module.KEYS = {str(a): str(k) for a, k in (module.FILE.get("keys") or {}).items()}
    return module


# ------------------------------------------------------------------ precedence


def test_with_no_file_the_defaults_stand(monkeypatch, tmp_path):
    settings = fresh(monkeypatch, tmp_path)
    assert settings.DEFAULT_QUALITY == "HI_RES_LOSSLESS"
    assert settings.ARTWORK == "auto"
    assert settings.THEME == "quattro"
    assert settings.PALETTE == "auto"
    assert settings.DEBUG is False
    assert settings.KEYS == {}


def test_the_file_overrides_the_defaults(monkeypatch, tmp_path):
    settings = fresh(
        monkeypatch,
        tmp_path,
        (
            'quality = "HIGH"\nartwork = "blocks"\n'
            'theme = "retro"\npalette = "nord"\ndebug = true\n'
        ),
    )
    assert settings.DEFAULT_QUALITY == "HIGH"
    assert settings.ARTWORK == "blocks"
    assert settings.THEME == "retro"
    assert settings.PALETTE == "nord"
    assert settings.DEBUG is True


def test_the_environment_overrides_the_file(monkeypatch, tmp_path):
    """A one-off run has to win over what you always want."""
    settings = fresh(
        monkeypatch,
        tmp_path,
        'quality = "HIGH"\nartwork = "blocks"\n',
        TIDALAMP_QUALITY="LOW",
        TIDALAMP_ART="off",
    )
    assert settings.DEFAULT_QUALITY == "LOW"
    assert settings.ARTWORK == "off"


def test_a_broken_file_falls_back_instead_of_refusing_to_start(monkeypatch, tmp_path):
    """A typo in the config must not stop the music."""
    settings = fresh(monkeypatch, tmp_path, 'quality = "HIGH\nesto no es toml')
    assert settings.DEFAULT_QUALITY == "HI_RES_LOSSLESS"
    assert settings.KEYS == {}


def test_an_unreadable_file_falls_back_too(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("quality = 'HIGH'", encoding="utf-8")
    path.chmod(0o000)
    try:
        assert config.read_file(path) == {}
    finally:
        path.chmod(0o644)


# ------------------------------------------------------------------------ keys


def test_keys_are_read_from_the_file(monkeypatch, tmp_path):
    settings = fresh(monkeypatch, tmp_path, '[keys]\nplay = "p"\nquit = "ctrl+q"\n')
    assert settings.KEYS == {"play": "p", "quit": "ctrl+q"}


def test_an_action_without_an_override_keeps_the_winamp_key():
    from tidalamp.app import DEFAULT_KEYS, keys_for

    # Winamp's letter is still the one a button shows and the one this test
    # is about; space rides behind it as a second binding.
    assert keys_for("play").split(",")[0] == "x"
    assert keys_for("quit") == DEFAULT_KEYS["quit"]


def test_an_override_wins(monkeypatch):
    from tidalamp import app

    monkeypatch.setitem(app.config.KEYS, "play", "p")
    assert app.keys_for("play") == "p"


def test_an_unknown_action_is_reported_rather_than_silently_ignored(monkeypatch):
    """`tidalamp config` prints these; a binding for them would never fire."""
    from tidalamp import app

    monkeypatch.setitem(app.config.KEYS, "reproducir", "p")
    assert app.unknown_key_actions() == ["reproducir"]


def test_asking_for_a_key_of_an_action_that_does_not_exist_is_a_bug():
    from tidalamp import app

    with pytest.raises(KeyError):
        app.keys_for("no_existe")


def test_navigation_keys_are_not_rebindable():
    """A typo on the arrows would lock the user out of the browser."""
    from tidalamp.app import DEFAULT_KEYS

    for fixed in ("cursor_up", "cursor_down", "play_selected"):
        assert fixed not in DEFAULT_KEYS


# -------------------------------------------------------------------- template


def test_the_template_is_valid_toml_and_lists_every_action(tmp_path):
    import tomllib

    from tidalamp.app import DEFAULT_KEYS

    path = config.write_template(tmp_path / "config.toml")
    text = path.read_text(encoding="utf-8")

    parsed = tomllib.loads(text)
    assert parsed["quality"] == "HI_RES_LOSSLESS"
    assert parsed["theme"] == "quattro"
    assert parsed["palette"] == "auto"
    assert parsed["keys"] == {}, "las teclas van comentadas, no activas"
    for action in DEFAULT_KEYS:
        assert f"# {action} = " in text


def test_the_template_never_overwrites_what_the_user_wrote(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('quality = "LOW"  # mío\n', encoding="utf-8")

    config.write_template(path)

    assert path.read_text(encoding="utf-8") == 'quality = "LOW"  # mío\n'


# ------------------------------------------------------------- writing back


def test_set_option_uncomments_in_place_and_keeps_the_comments(tmp_path):
    """The template ships every setting commented out with an explanation
    above it. Appending a second line would leave the user with two."""
    path = tmp_path / "config.toml"

    config.set_option("quality", "LOSSLESS", path)
    text = path.read_text()

    assert 'quality = "LOSSLESS"' in text
    assert text.count("quality =") == 1
    # The explanation that shipped above it is still there.
    assert "HI_RES_LOSSLESS" in text
    assert "# LOW, HIGH" in text or "# LOW, HIGH, LOSSLESS" in text


def test_set_option_writes_each_type_the_way_toml_reads_it(tmp_path):
    path = tmp_path / "config.toml"

    config.set_option("quality", "HIGH", path)
    config.set_option("debug", True, path)
    config.set_option("language", "en", path)

    assert config.read_file(path) == {
        "quality": "HIGH",
        "artwork": "auto",
        "cover_shape": "square",
        "language": "en",
        "columns": "artist,album,year,duration",
        "theme": "quattro",
        "palette": "auto",
        "arrangement": "stacked",
        "backdrop": "auto",
        "visualizer": "bars",
        "debug": True,
        "transparency": False,
        "keys": {},
    }


def test_set_option_leaves_the_keys_section_alone(tmp_path):
    """`[keys]` has entries named like settings; the writer stops before it."""
    path = tmp_path / "config.toml"
    path.write_text(
        'quality = "HIGH"\n\n[keys]\n# quality = "k"\nplay = "p"\n', encoding="utf-8"
    )

    config.set_option("quality", "LOW", path)

    text = path.read_text()
    assert 'quality = "LOW"' in text
    # Still a comment: had the writer reached it, it would now be a binding.
    assert '# quality = "k"' in text, "la línea de [keys] no se toca"
    assert config.read_file(path)["keys"] == {"play": "p"}


def test_a_setting_the_file_never_had_is_added_above_the_sections(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[keys]\nplay = "p"\n', encoding="utf-8")

    config.set_option("quality", "LOW", path)

    assert config.read_file(path) == {"quality": "LOW", "keys": {"play": "p"}}


def test_writing_a_missing_file_starts_from_the_template(tmp_path):
    path = tmp_path / "config.toml"
    assert not path.exists()

    config.set_option("artwork", "blocks", path)

    assert path.exists()
    assert config.read_file(path)["artwork"] == "blocks"


# --------------------------------------------------------- reload and env


def test_reload_brings_the_module_globals_up_to_date(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    monkeypatch.delenv("TIDALAMP_QUALITY", raising=False)

    config.set_option("quality", "LOW", path)
    config.reload()

    assert config.DEFAULT_QUALITY == "LOW"


def test_the_environment_still_wins_and_the_screen_is_told_so(monkeypatch, tmp_path):
    """A value the file holds but the app is not using has to be labelled, or
    the config screen shows something that is not in effect."""
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    monkeypatch.setenv("TIDALAMP_QUALITY", "HIGH")

    config.set_option("quality", "LOW", path)
    config.reload()

    assert config.DEFAULT_QUALITY == "HIGH"
    assert config.overridden("quality") == "TIDALAMP_QUALITY"
    assert config.overridden("artwork") is None


def test_every_setting_names_the_variable_that_overrides_it():
    for name, variable in config.ENV_VARS.items():
        assert variable.startswith("TIDALAMP_"), name


def test_the_column_catalogue_and_the_setting_agree():
    """Two places name these columns; a third would be one too many."""
    from tidalamp import columns as catalogue

    assert set(catalogue.DEFAULT) <= set(catalogue.NAMES)
    assert ",".join(catalogue.DEFAULT) == config.DEFAULT_COLUMNS
    # Every name in the template is one the catalogue knows.
    from tidalamp.i18n import config_template

    line = next(
        row for row in config_template().splitlines() if row.startswith("columns = ")
    )
    written = line.split("=", 1)[1].strip().strip('"').split(",")
    assert [name.strip() for name in written] == list(catalogue.DEFAULT)


def test_an_unknown_column_name_costs_that_column_and_nothing_else(monkeypatch):
    monkeypatch.setenv("TIDALAMP_COLUMNS", "artist,inventada,year,artist")

    assert config.columns() == ("artist", "year")

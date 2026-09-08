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

    for name in ("TIDALAMP_QUALITY", "TIDALAMP_ART", "TIDALAMP_DEBUG"):
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
    module.DEBUG = module.flag("debug", "TIDALAMP_DEBUG")
    module.KEYS = {str(a): str(k) for a, k in (module.FILE.get("keys") or {}).items()}
    return module


# ------------------------------------------------------------------ precedence


def test_with_no_file_the_defaults_stand(monkeypatch, tmp_path):
    settings = fresh(monkeypatch, tmp_path)
    assert settings.DEFAULT_QUALITY == "HI_RES_LOSSLESS"
    assert settings.ARTWORK == "auto"
    assert settings.DEBUG is False
    assert settings.KEYS == {}


def test_the_file_overrides_the_defaults(monkeypatch, tmp_path):
    settings = fresh(
        monkeypatch,
        tmp_path,
        'quality = "HIGH"\nartwork = "blocks"\ndebug = true\n',
    )
    assert settings.DEFAULT_QUALITY == "HIGH"
    assert settings.ARTWORK == "blocks"
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

    assert keys_for("play") == "x"
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
    assert parsed["keys"] == {}, "las teclas van comentadas, no activas"
    for action in DEFAULT_KEYS:
        assert f"# {action} = " in text


def test_the_template_never_overwrites_what_the_user_wrote(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('quality = "LOW"  # mío\n', encoding="utf-8")

    config.write_template(path)

    assert path.read_text(encoding="utf-8") == 'quality = "LOW"  # mío\n'

"""The keys: which one does what, from the config file or the defaults.

Only the actions a user may rebind are here. The navigation keys (arrows,
page up/down, Enter, Escape) are fixed in each window's own bindings.
"""

from __future__ import annotations

from textual.binding import Binding

from . import config
from .i18n import _

# Every action a user may rebind. Navigation keys (arrows, page up/down,
# Enter, Escape) are deliberately not here: they are what makes the browser
# navigable, and a typo there locks you out of it.
#
# The transport runs z x c v across the keyboard in the order the buttons sit
# on screen, which is easier to find by touch than Winamp's z x c v b — that
# one spent a key on a separate pause, and pause now shares the play button.
DEFAULT_KEYS: dict[str, str] = {
    "prev": "z",
    # Space is what every other player uses, and nothing in the main window
    # wanted it. `x` stays first so the transport button keeps its Winamp
    # letter: `transport.button_key` draws the first key bound and no more.
    "play": "x,space",
    "stop": "c",
    "next": "v",
    "search": "slash",
    "filter_queue": "ctrl+f",
    "track_menu": "m",
    "to_playing": "g",
    "save_playlist": "p",
    "library": "l",
    "lyrics": "y",
    # Next to `y`: both answer «what is this», one with the words and the
    # other with who made it and what its licence asks.
    "credits": "k",
    "equalizer": "e",
    "shuffle": "s",
    "repeat": "r",
    "favourite": "f",
    "unfavourite": "F",
    "remove": "d,delete",
    "move_up": "alt+up",
    "move_down": "alt+down",
    "clear": "C",
    "undo_clear": "u",
    "seek_back": "left",
    "seek_fwd": "right",
    "vol_up": "plus,equals_sign",
    "vol_down": "minus",
    "balance_left": "comma",
    "balance_right": "full_stop",
    "balance_centre": "backslash",
    "toggle_time": "t",
    # After z x c v, where Winamp kept its fifth key.
    "speed": "b",
    # Only a key opens it: no row in the settings, no button on the player.
    "fullscreen": "w",
    "config": "o",
    "help": "question_mark,h",
    # `q` asks first: it sits next to `w`, and one slip closed the player.
    # ctrl+c is the way out that does not ask.
    "quit": "q",
    "force_quit": "ctrl+c",
}


def keys_for(action: str) -> str:
    """The key bound to ``action``, from the config file or the default."""
    override = config.KEYS.get(action)
    if override:
        return override
    if action not in DEFAULT_KEYS:
        raise KeyError(_("acción desconocida: {action}").format(action=action))
    return DEFAULT_KEYS[action]


def bind(action: str, description: str, show: bool = False) -> Binding:
    return Binding(keys_for(action), action, description, show=show)


def unknown_key_actions() -> list[str]:
    """Actions named in the config file that do not exist. For the CLI to warn."""
    return sorted(set(config.KEYS) - set(DEFAULT_KEYS))

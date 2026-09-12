"""The modal windows stacked over the main panel: search, library, EQ, lyrics.

They own no player state. Each one is handed what it needs at construction —
a session, a loader, a `Settings` — and reports back through `dismiss`, which
is what keeps `app.py` from having to know how any of them are laid out.

`RowList` lives here rather than in `widgets.py` because it renders a
`library.Row`, and `library` imports tidalapi: putting it there would drag
TIDAL into the one module that is deliberately ignorant of it.
"""

from .browser import BROWSER_HINTS, HINT_GAP, BrowserScreen, favourite_message, fit_hints
from .choice import ChoiceScreen
from .column_picker import ColumnsScreen, _crop, column_label
from .config_window import _ATTRIBUTES, _FLAGS, ConfigScreen, Option
from .equalizer import PRESET_LABELS, EqScreen
from .fullscreen import FullscreenScreen
from .help import HelpScreen
from .lyrics_window import LyricsScreen
from .prompts import PlaylistNameScreen, SearchScreen
from .rowlist import RowList, _hex, _Paint
from .speed import SpeedScreen, speed_text
from .tracks import (
    CONTAINER_ACTIONS,
    TRACK_ACTIONS,
    PlaylistPickerScreen,
    TrackActionsScreen,
)

__all__ = [
    "BROWSER_HINTS",
    "CONTAINER_ACTIONS",
    "HINT_GAP",
    "PRESET_LABELS",
    "TRACK_ACTIONS",
    "_ATTRIBUTES",
    "_FLAGS",
    "BrowserScreen",
    "ChoiceScreen",
    "ColumnsScreen",
    "ConfigScreen",
    "EqScreen",
    "FullscreenScreen",
    "HelpScreen",
    "LyricsScreen",
    "Option",
    "PlaylistNameScreen",
    "PlaylistPickerScreen",
    "RowList",
    "SearchScreen",
    "SpeedScreen",
    "TrackActionsScreen",
    "_Paint",
    "_crop",
    "_hex",
    "column_label",
    "favourite_message",
    "fit_hints",
    "speed_text",
]

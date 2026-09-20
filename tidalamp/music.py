"""What a source of freely licensed music hands back, and how to ask for it.

Shared by `jamendo` and `archive`, the two places «Lofi sin copyright» draws
from, so `freemusic` can treat them as the same thing and the rest of the
player never learns there was more than one.

Nothing here knows about ``Row``, tidalapi or Textual: this is the seam that
keeps TIDAL out of the free section and the free section out of TIDAL.
"""

from __future__ import annotations

import logging
import threading
import zlib
from dataclasses import dataclass
from typing import Any

import requests

from .i18n import _
from .net import TimeoutSession, with_retries

log = logging.getLogger("tidalamp.music")

USER_AGENT = "tidalamp (+https://github.com/wh01s17/tidalamp)"


class FreeMusicUnavailable(RuntimeError):
    """A source did not answer, or answered with nothing usable."""


# How a licence URL reads on screen. Longest fragment first, because
# `licenses/by-sa` contains `licenses/by`: the other order labelled every
# share-alike track «CC BY» and quietly dropped the condition that matters.
_LICENCE_NAMES = (
    ("publicdomain/zero", "CC0"),
    ("publicdomain/mark", _("dominio público")),
    ("publicdomain", _("dominio público")),
    ("licenses/by-sa", "CC BY-SA"),
    ("licenses/by-nc-sa", "CC BY-NC-SA"),
    ("licenses/by-nc-nd", "CC BY-NC-ND"),
    ("licenses/by-nd", "CC BY-ND"),
    ("licenses/by-nc", "CC BY-NC"),
    ("licenses/by", "CC BY"),
)

# The only licences «Lofi sin copyright» lets through, by the name above.
# Every Creative Commons licence allows *listening*, so this is not what
# makes playback lawful; it is what makes the section's name true. The name
# promises music you can use, and NC and ND do not deliver that.
PERMISSIVE = frozenset({"CC0", _("dominio público"), "CC BY", "CC BY-SA"})


def licence_name(url: str) -> str:
    """«CC BY-SA» out of a licence URL, or the URL when it is not one we know."""
    lowered = url.lower()
    for fragment, name in _LICENCE_NAMES:
        if fragment in lowered:
            return name
    return url


def is_permissive(licence: str) -> bool:
    """Whether the licence lets the listener reuse the work, not merely hear it."""
    return licence in PERMISSIVE


@dataclass(frozen=True, slots=True)
class Track:
    """One playable piece of music, whichever source it came from."""

    url: str
    title: str
    artist: str
    album: str
    licence: str
    duration: int = 0
    year: int = 0
    track_num: int = 0
    codec: str = ""
    art_url: str = ""
    # The page this track came from, which is what a credit points at. Not
    # the audio URL: that is a file, and attribution asks for the work.
    source_url: str = ""

    @property
    def id(self) -> int:
        """A stable negative id, unique to this URL.

        Negative on purpose: TIDAL's track ids are positive, and the queue
        keys deduplication, the lyrics cache and the restored-entry identity
        off ``Entry.id``. A number no TIDAL track can ever hold keeps those
        three working untouched, and deriving it from the URL means the same
        file restores from disk as the same track.
        """
        return -(zlib.crc32(self.url.encode("utf-8")) or 1)


# One session per thread. `requests.Session` is not safe to share between
# threads, and a new one per request throws away the connection with it.
_LOCAL = threading.local()


def session() -> requests.Session:
    found = getattr(_LOCAL, "session", None)
    if found is None:
        found = TimeoutSession()
        found.headers["User-Agent"] = USER_AGENT
        _LOCAL.session = found
    return found


def get_json(url: str, params: dict[str, Any] | None = None, *, who: str = "") -> Any:
    """One GET, retried, parsed, and with its failures named.

    ``raise_for_status`` before the parse so `with_retries` sees the HTTPError
    for a 5xx and gives it another go; a body that is not JSON is a server
    handing out an error page, which is not worth retrying.
    """

    def call() -> Any:
        response = session().get(url, params=params)
        response.raise_for_status()
        return response.json()

    try:
        return with_retries(call)
    except ValueError as exc:
        raise FreeMusicUnavailable(
            _("{who} contestó algo que no es JSON").format(who=who)
        ) from exc
    except requests.RequestException as exc:
        raise FreeMusicUnavailable(
            _("no se pudo hablar con {who}: {error}").format(who=who, error=exc)
        ) from exc


def as_int(value: Any) -> int:
    """These APIs type loosely: a year may arrive as int, str or a list."""
    if isinstance(value, list):
        value = value[0] if value else 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def as_text(value: Any) -> str:
    """Likewise for text: a `creator` is a list when a work has several."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value) if value is not None else ""

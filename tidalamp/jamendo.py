"""Jamendo: the source «Lofi sin copyright» draws from when it can.

Everything on Jamendo is published under a Creative Commons licence, which
makes it the right shape for this section in a way a general archive never
is. What it gives that digging through the Internet Archive does not:

* **One request for a whole day.** `limit=200` answers with two hundred
  tracks, each carrying its own streaming URL, so a day costs a single round
  trip instead of a search plus two dozen metadata calls and twenty seconds.
* **A real instrumental filter.** `vocalinstrumental=instrumental` is a field
  the artist set, not a guess made by reading titles for the word «rapper».
* **A licence filter that runs on the server.** `ccnc=0&ccnd=0` asks for
  neither NonCommercial nor NoDerivatives, which is exactly the permissive
  half. Measured on 2026-09-20: 23 of 200 tracks were permissive without it
  and 192 of 200 with it, out of 2787 that match the whole query.
* **Popularity that means something,** from listens, favourites and reviews
  rather than from an item's download counter.

Credentials: only a `client_id`, and it is not a secret — see
`config.JAMENDO_ID`. The `client_secret` signs OAuth writes against a user's
account, which this never does.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import config
from .i18n import _
from .music import (
    FreeMusicUnavailable,
    Track,
    as_int,
    as_text,
    get_json,
    is_permissive,
    licence_name,
)

log = logging.getLogger("tidalamp.jamendo")

API = "https://api.jamendo.com/v3.0/tracks/"
WHO = "Jamendo"

# The genre, as Jamendo's own taggers write it. `fuzzytags` and not `tags`:
# the strict one wants every tag present on the track, and almost nothing
# carries both of these at once.
#
# `chillout` was here first and it was the wrong word. It matched Jamendo's
# deep bench of 2006-era European netlabel ambient — Tryad, Zeropage,
# Sublustris Nox — which is chill and is not lofi: 2787 tracks of which only
# 15% were from 2018 or later. `chillhop` is the word this genre's own
# taggers use, and it comes back 89% recent.
TAGS = "chillhop+lofi"

# Lofi as a genre is younger than most of this catalogue. Without a floor the
# page fills with downtempo that happens to share a tag; with it, 79% of what
# comes back is from 2018 or later and the titles read «Study Beats (Lofi
# Hip-Hop Ensemble)» rather than «ecologikorgan». 331 tracks pass, which at
# forty a day is over a week before one could come round again.
SINCE = "2016-01-01"
UNTIL = "2099-01-01"

# VBR rather than the 96 kbps `mp31` that comes by default. `flac` exists
# too, but not for every track, and a station that dropped whatever had no
# FLAC would be choosing bitrate over music.
AUDIO_FORMAT = "mp32"

# What one page holds, which is Jamendo's maximum and a whole day's worth.
PAGE = 200

# Jamendo answers `success` with an empty result set every so often — no
# error, no warning, the same query that worked a second ago. Measured on
# 2026-09-20: three of twelve identical calls came back empty. So an empty
# answer is a failure here, not an answer, and it is worth another go.
EMPTY_TRIES = 6
EMPTY_PAUSE = 0.8


def configured() -> str:
    """The client id in use, or empty when there is none to use."""
    return (config.JAMENDO_ID or "").strip()


def _query(offset: int) -> dict[str, Any]:
    return {
        "client_id": configured(),
        "format": "json",
        "limit": PAGE,
        "offset": offset,
        "fuzzytags": TAGS,
        "datebetween": f"{SINCE}_{UNTIL}",
        # The artist said so; we are not guessing from the title.
        "vocalinstrumental": "instrumental",
        # Neither NonCommercial nor NoDerivatives: the permissive half.
        "ccnc": 0,
        "ccnd": 0,
        "audioformat": AUDIO_FORMAT,
        # Community ratings: listens, favourites, reviews.
        "order": "popularity_total",
    }


def _rows(offset: int) -> list[dict[str, Any]]:
    """One page, retried past Jamendo's habit of answering with nothing."""
    for attempt in range(EMPTY_TRIES):
        raw = get_json(API, _query(offset), who=WHO)
        headers = raw.get("headers") or {}
        if headers.get("status") != "success":
            raise FreeMusicUnavailable(
                _("{who} rechazó la petición: {error}").format(
                    who=WHO, error=headers.get("error_message") or headers.get("code")
                )
            )
        rows = raw.get("results")
        if rows:
            return list(rows)
        log.debug("Jamendo contestó vacío (intento %s)", attempt + 1)
        time.sleep(EMPTY_PAUSE)
    raise FreeMusicUnavailable(
        _("{who} contestó sin resultados varias veces seguidas").format(who=WHO)
    )


def _track(row: dict[str, Any]) -> Track | None:
    """One row as a `Track`, or None when it is not one we may play.

    The licence is checked again here even though the query asked the server
    to filter it: a handful of rows come back with the field empty, and an
    empty licence is not a permissive one — it is an unknown one, and this
    section may not guess.
    """
    url = as_text(row.get("audio"))
    licence = licence_name(as_text(row.get("license_ccurl")))
    if not url or not is_permissive(licence):
        return None
    return Track(
        url=url,
        title=as_text(row.get("name")),
        artist=as_text(row.get("artist_name")),
        album=as_text(row.get("album_name")),
        licence=licence,
        duration=as_int(row.get("duration")),
        year=as_int(as_text(row.get("releasedate"))[:4]),
        track_num=as_int(row.get("position")),
        codec="MP3",
        art_url=as_text(row.get("album_image") or row.get("image")),
        # The track's page on Jamendo, which is what a credit points at.
        source_url=as_text(row.get("shareurl")),
    )


def tracks(offset: int = 0) -> list[Track]:
    """One page of instrumental, permissively licensed lofi."""
    if not configured():
        raise FreeMusicUnavailable(_("no hay un client_id de Jamendo configurado"))
    found = [track for track in map(_track, _rows(offset)) if track is not None]
    if not found:
        raise FreeMusicUnavailable(
            _("{who} no devolvió nada con licencia permisiva").format(who=WHO)
        )
    log.debug("Jamendo: %s pistas utilizables desde el offset %s", len(found), offset)
    return found

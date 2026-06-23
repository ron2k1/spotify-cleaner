"""Album-art proxy: resolve a track's thumbnail via Spotify's keyless oEmbed.

Why this exists: the obvious path -- the catalog ``/v1/tracks`` endpoint -- is
forbidden to development-mode Spotify apps (every call 403s), so the table never
got thumbnails. ``open.spotify.com/oembed`` needs no token and returns a
``thumbnail_url`` for any public track, but it sets no CORS header, so the
browser cannot call it directly. We proxy it here (server-side, same origin) and
302-redirect the browser straight to the resolved CDN image.

Resolved URLs (and misses) are cached in-process: the table is virtualized, so
the same rows are requested repeatedly as the user scrolls, and a miss must not
re-hit oEmbed every time.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/api", tags=["art"])
log = logging.getLogger("spotify_cleaner.art")

_OEMBED = "https://open.spotify.com/oembed"

# Spotify ids are base-62 and (currently) 22 chars; match defensively on the
# character class rather than pin the length. Anything else never touches the
# network -- this stops a user-supplied path segment from being smuggled into
# the outbound oEmbed URL.
_ID_RE = re.compile(r"^[A-Za-z0-9]{1,40}$")

# track_id -> resolved thumbnail URL, or None for a known miss. Bounded by the
# library size and each entry is a short string, so no eviction is needed for a
# single-user self-host tool. A rare concurrent double-fetch is harmless.
_cache: dict[str, Optional[str]] = {}


def _resolve(track_id: str) -> Optional[str]:
    if track_id in _cache:
        return _cache[track_id]
    url: Optional[str] = None
    try:
        resp = requests.get(
            _OEMBED,
            params={"url": f"https://open.spotify.com/track/{track_id}"},
            timeout=6,
        )
        if resp.status_code == 200:
            url = resp.json().get("thumbnail_url") or None
        else:
            # Log the status only -- never the body. Art is cosmetic; a miss is
            # not an error worth surfacing.
            log.debug("oembed status %s for %s", resp.status_code, track_id)
    except (requests.RequestException, ValueError) as exc:
        log.debug("oembed %s for %s", type(exc).__name__, track_id)
    _cache[track_id] = url
    return url


@router.get("/art/{track_id}")
def album_art(track_id: str) -> RedirectResponse:
    """302 to the track's CDN thumbnail, or 404 if it has none."""
    if not _ID_RE.match(track_id):
        raise HTTPException(status_code=400, detail="bad_track_id")
    url = _resolve(track_id)
    if not url:
        raise HTTPException(status_code=404, detail="no_art")
    # The browser caches the final CDN image (the CDN sets its own headers); the
    # redirect itself is cheap and backed by the in-process cache.
    return RedirectResponse(url, status_code=302)

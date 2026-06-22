"""Scorer backed by the Last.fm API (per-track ``userplaycount``).

Real-time and needs no waiting, but only reflects plays you actually
scrobbled. A track Last.fm has never seen for you returns 0 plays. Requires
that you already connected Spotify to Last.fm and have scrobble history.
"""

from __future__ import annotations

import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..models import MEDIUM, PlayStats, ProgressFn, Track

API = "https://ws.audioscrobbler.com/2.0/"


def _retrying_session() -> requests.Session:
    """A session that retries transient failures instead of giving up.

    Last.fm occasionally answers a burst with 429 (rate limit) or a 5xx, and a
    bare session would surface that as a one-off "lookup failed" for the track,
    silently degrading the score. urllib3's ``Retry`` backs off exponentially
    and, critically, honours a ``Retry-After`` header so we wait exactly as long
    as the server asks. This mirrors the retry policy spotipy already applies to
    the Spotify client, so both sources fail the same graceful way.
    """
    retry = Retry(
        total=4,
        backoff_factor=0.5,  # 0s, 0.5s, 1s, 2s between attempts
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class LastfmScorer:
    name = "lastfm"
    mode = "count"

    def __init__(self, api_key: str, username: str, pause: float = 0.25):
        self.api_key = api_key
        self.username = username
        self.pause = pause  # stay well under Last.fm's ~5 req/s guidance
        self._session = _retrying_session()

    def _playcount(self, artist: str, track: str) -> Optional[int]:
        params = {
            "method": "track.getInfo",
            "api_key": self.api_key,
            "artist": artist,
            "track": track,
            "username": self.username,
            "autocorrect": 1,
            "format": "json",
        }
        try:
            r = self._session.get(API, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            return None  # network/parse failure -> "unknown", not "zero"
        if "track" not in data:
            return 0  # Last.fm has never seen this track for this user
        try:
            return int(data["track"].get("userplaycount", 0))
        except (TypeError, ValueError):
            return 0

    def score(
        self, tracks: list[Track], progress: Optional[ProgressFn] = None
    ) -> dict[str, PlayStats]:
        out: dict[str, PlayStats] = {}
        total = len(tracks)
        for i, t in enumerate(tracks, 1):
            artist = t.artists[0] if t.artists else ""
            pc = self._playcount(artist, t.name) if artist else None
            note = f"{pc} scrobbles" if pc is not None else "lookup failed"
            out[t.track_id] = PlayStats(
                source=self.name,
                play_count=pc,
                note=note,
                # Scrobbles are real plays, but only the ones you scrobbled — you
                # may have listened on a device that wasn't connected. MEDIUM.
                confidence=MEDIUM,
            )
            # One Last.fm lookup per track at ~0.25s each makes this the slow
            # scorer. Emit every 25 (and once at the end) so the web UI shows a
            # live fraction instead of an apparently frozen "scoring…" phase.
            if progress is not None and (i % 25 == 0 or i == total):
                progress("scoring", i, total)
            time.sleep(self.pause)
        return out

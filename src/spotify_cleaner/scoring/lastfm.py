"""Scorer backed by the Last.fm API (per-track ``userplaycount``).

Real-time and needs no waiting, but only reflects plays you actually
scrobbled. A track Last.fm has never seen for you returns 0 plays. Requires
that you already connected Spotify to Last.fm and have scrobble history.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from ..models import PlayStats, Track

API = "https://ws.audioscrobbler.com/2.0/"


class LastfmScorer:
    name = "lastfm"
    mode = "count"

    def __init__(self, api_key: str, username: str, pause: float = 0.25):
        self.api_key = api_key
        self.username = username
        self.pause = pause  # stay well under Last.fm's ~5 req/s guidance
        self._session = requests.Session()

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

    def score(self, tracks: list[Track]) -> dict[str, PlayStats]:
        out: dict[str, PlayStats] = {}
        for t in tracks:
            artist = t.artists[0] if t.artists else ""
            pc = self._playcount(artist, t.name) if artist else None
            note = f"{pc} scrobbles" if pc is not None else "lookup failed"
            out[t.track_id] = PlayStats(source=self.name, play_count=pc, note=note)
            time.sleep(self.pause)
        return out

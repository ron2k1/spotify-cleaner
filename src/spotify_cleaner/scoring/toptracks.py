"""Coarse proxy scorer: anything NOT in your top-played tracks is a candidate.

Needs no export and no scrobbling, but the Spotify API only returns your top
~50 per time window, so it cannot rank the long tail. It answers "top vs not",
not "how many plays". Good for a fast first pass with zero setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import PlayStats, Track

if TYPE_CHECKING:
    import spotipy

# Spotify's top-items endpoint only ever returns up to 50 items per window.
_API_MAX = 50


class TopTracksScorer:
    name = "toptracks"
    mode = "rank"

    def __init__(self, sp: "spotipy.Spotify", time_range: str = "long_term", top_n: int = 50):
        self.sp = sp
        self.time_range = time_range
        self.top_n = min(top_n, _API_MAX)

    def _top_ranks(self) -> dict[str, int]:
        ranks: dict[str, int] = {}
        offset = 0
        while offset < self.top_n:
            limit = min(_API_MAX, self.top_n - offset)
            page = self.sp.current_user_top_tracks(
                limit=limit, offset=offset, time_range=self.time_range
            )
            items = page.get("items", []) if page else []
            if not items:
                break
            for j, tr in enumerate(items):
                if tr.get("id"):
                    ranks.setdefault(tr["id"], offset + j + 1)
            offset += len(items)
        return ranks

    def score(self, tracks: list[Track]) -> dict[str, PlayStats]:
        ranks = self._top_ranks()
        out: dict[str, PlayStats] = {}
        for t in tracks:
            r = ranks.get(t.track_id)
            in_top = r is not None
            note = f"top #{r} ({self.time_range})" if in_top else "not in top tracks"
            out[t.track_id] = PlayStats(
                source=self.name, in_top=in_top, rank=r, note=note
            )
        return out

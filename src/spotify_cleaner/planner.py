"""Turns scores into a ranked list of cleanup candidates.

Pure logic, no I/O, so this is the part that is unit-tested against fixtures.
It is deliberately conservative: a track is only ever a *candidate*; nothing
here deletes anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .library import Library
from .models import PlayStats, ScoredTrack

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def plan(
    library: Library,
    stats: dict[str, PlayStats],
    mode: str,
    *,
    liked_only: bool = True,
    min_plays: int = 2,
    stale_days: Optional[int] = None,
) -> list[ScoredTrack]:
    """Return cleanup candidates, least-listened first.

    count mode: flag tracks with <= ``min_plays`` plays, or (if ``stale_days``
                is set) not played within that many days.
    rank mode:  flag tracks absent from your top tracks.
    """
    universe = library.liked() if liked_only else list(library.tracks.values())
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=stale_days)
        if stale_days is not None
        else None
    )

    candidates: list[ScoredTrack] = []
    for t in universe:
        st = stats.get(t.track_id) or PlayStats(source="none", play_count=0, note="no data")
        reason = _why(st, mode, min_plays, cutoff)
        if reason:
            candidates.append(ScoredTrack(track=t, stats=st, reason=reason))

    candidates.sort(key=lambda c: _sort_key(c.stats))
    return candidates


def _why(
    st: PlayStats, mode: str, min_plays: int, cutoff: Optional[datetime]
) -> str:
    """Return a non-empty reason string if the track is a candidate, else ""."""
    if mode == "rank":
        return "" if st.in_top else (st.note or "not in top tracks")

    # count mode
    if st.play_count is None:
        # Unknown plays (e.g. a failed Last.fm lookup) is not evidence of low
        # listening — don't flag it. "Unknown" must never collapse to "zero".
        return ""
    count = st.play_count
    if count <= min_plays:
        return f"only {count} play(s)"
    if cutoff is not None and st.last_played is not None and st.last_played < cutoff:
        return f"not played since {st.last_played.date()}"
    return ""


def _sort_key(st: PlayStats):
    """Least-listened first: low count, oldest last-play, worst rank."""
    # Unknown count sorts LAST (big sentinel), so a confirmed 0-play track
    # outranks a "we don't know" track. The opposite would push uncertain
    # tracks to the top of the deletion list.
    count = st.play_count if st.play_count is not None else 10**9
    last = st.last_played or _EPOCH
    rank = st.rank if st.rank is not None else 10**9
    return (count, last, -rank)

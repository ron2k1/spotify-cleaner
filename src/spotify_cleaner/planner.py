"""Turns scores into a ranked list of cleanup candidates.

Pure logic, no I/O, so this is the part that is unit-tested against fixtures.
It is deliberately conservative: a track is only ever a *candidate*; nothing
here deletes anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .library import Library
from .models import PlayStats, ScoredTrack, Track

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def plan(
    library: Library,
    stats: dict[str, PlayStats],
    mode: str,
    *,
    liked_only: bool = True,
    min_plays: int = 2,
    stale_days: Optional[int] = None,
    grace_days: Optional[int] = None,
) -> list[ScoredTrack]:
    """Return cleanup candidates, least-listened first.

    count mode: flag tracks with <= ``min_plays`` plays, or (if ``stale_days``
                is set) not played within that many days.
    rank mode:  flag tracks absent from your top tracks.

    ``grace_days`` protects freshly added tracks: a track added within that many
    days is too new to judge (you have not had time to play it yet) and is never
    flagged. It is purely subtractive -- it only suppresses a flag when there is
    positive evidence the track is recent, so a track with a missing/unparseable
    ``added_at`` is handled exactly as if no grace were set.
    """
    universe = library.liked() if liked_only else list(library.tracks.values())
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=stale_days)
        if stale_days is not None
        else None
    )
    grace_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=grace_days)
        if grace_days is not None
        else None
    )

    candidates: list[ScoredTrack] = []
    for t in universe:
        if grace_cutoff is not None:
            added = _parse_added(t.added_at)
            if added is not None and added >= grace_cutoff:
                continue  # added within the grace window -- too new to judge
        st = stats.get(t.track_id) or PlayStats(source="none", play_count=0, note="no data")
        reason = _why(st, mode, min_plays, cutoff)
        if reason:
            candidates.append(ScoredTrack(track=t, stats=st, reason=reason))

    candidates.sort(key=lambda c: _sort_key(c.stats, c.track))
    return candidates


def _parse_added(added_at: Optional[str]) -> Optional[datetime]:
    """Parse a Spotify ``added_at`` ISO string to an aware datetime, or None.

    Returns None for a missing or malformed value so the caller can fall back to
    normal handling rather than mistake "unknown age" for "recently added".
    """
    if not added_at:
        return None
    try:
        dt = datetime.fromisoformat(added_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    # Force UTC on an offset-less value so the comparison with grace_cutoff never
    # raises "can't compare naive and aware datetimes".
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _why(
    st: PlayStats, mode: str, min_plays: int, cutoff: Optional[datetime]
) -> str:
    """Return a non-empty reason string if the track is a candidate, else ""."""
    if mode == "rank":
        return "" if st.in_top else (st.note or "not in top tracks")

    # count mode
    if st.play_count is None:
        # Unknown plays (e.g. a count-mode source whose lookup failed) is not
        # evidence of low listening — don't flag it. "Unknown" must never
        # collapse to "zero".
        return ""
    count = st.play_count
    if count <= min_plays:
        return f"only {count} play(s)"
    if cutoff is not None and st.last_played is not None and st.last_played < cutoff:
        return f"not played since {st.last_played.date()}"
    return ""


def _sort_key(st: PlayStats, track: Track):
    """Least-listened first, with oldest-added as the final tie-breaker.

    The first three terms order by listening evidence (low count, oldest
    last-play, worst rank). ``added_at`` ascending breaks ties: in rank /
    toptracks mode every candidate shares the same first three terms (no
    counts, no last-play dates, no rank), so this term alone decides the order
    and surfaces the songs you've sat on longest — not the ones you just saved.
    A missing date sorts last via the ``"9999"`` sentinel (Spotify's ISO 8601
    timestamps sort chronologically under a plain lexical compare).
    """
    # Unknown count sorts LAST (big sentinel), so a confirmed 0-play track
    # outranks a "we don't know" track. The opposite would push uncertain
    # tracks to the top of the deletion list.
    count = st.play_count if st.play_count is not None else 10**9
    last = st.last_played or _EPOCH
    rank = st.rank if st.rank is not None else 10**9
    added = track.added_at or "9999"
    return (count, last, -rank, added)

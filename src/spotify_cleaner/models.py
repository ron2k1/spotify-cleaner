"""Core data contracts shared across the whole tool.

These dataclasses are the only types the planner and cleaner know about.
Scorers translate their very different raw data (GDPR JSON, Last.fm responses,
top-track ranks) into ``PlayStats`` so everything downstream stays uniform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

# A best-effort progress sink: (phase, current, total_or_None). The long Spotify
# I/O functions call it so a UI can show live progress. The CLI passes nothing,
# so every call collapses to a no-op and the command-line path is unchanged.
ProgressFn = Callable[[str, int, Optional[int]], None]

# How much to trust a scorer's verdict for a single track. It is a property of
# the *evidence*, not the planner: a true lifetime count (gdpr, matched by id)
# is "high"; a crude top-50-vs-not proxy is "low". The UI surfaces this so a
# user can be more careful before removing a low-confidence flag.
Confidence = str  # one of the constants below
HIGH = "high"
MEDIUM = "medium"
LOW = "low"


@dataclass(frozen=True)
class Track:
    """A single track in the user's library, plus where it lives."""

    track_id: str  # Spotify base-62 id, e.g. "0eGsygTp906u18L0Oimnem"
    uri: str  # "spotify:track:<id>"
    name: str
    artists: tuple[str, ...]
    added_at: Optional[str] = None  # ISO string from /me/tracks
    is_liked: bool = False  # present in Liked Songs
    playlist_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def label(self) -> str:
        artist = ", ".join(self.artists) if self.artists else "(unknown artist)"
        return f"{artist} - {self.name}"


@dataclass
class PlayStats:
    """How much the user has listened to one track, per a given source.

    Different scorers populate different fields. Count-based sources fill
    ``play_count``/``last_played``; the rank-based proxy fills ``in_top``/``rank``.
    ``note`` is a short human-readable explanation shown in the review list.
    """

    source: str
    play_count: Optional[int] = None
    last_played: Optional[datetime] = None
    in_top: Optional[bool] = None
    rank: Optional[int] = None
    note: str = ""
    # How trustworthy this verdict is. Set by the scorer from the quality of the
    # underlying evidence (data source + how the track was matched), so the UI
    # can warn before acting on a weak signal. Defaults to MEDIUM.
    confidence: Confidence = MEDIUM


@dataclass
class ScoredTrack:
    """A cleanup candidate: a track plus why it was flagged."""

    track: Track
    stats: PlayStats
    reason: str

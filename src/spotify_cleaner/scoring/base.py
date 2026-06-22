"""The pluggable scoring contract. Every data source implements ``Scorer``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import PlayStats, Track


@runtime_checkable
class Scorer(Protocol):
    #: short identifier shown to the user, e.g. "gdpr"
    name: str
    #: "count" -> fills play_count/last_played; "rank" -> fills in_top/rank
    mode: str

    def score(self, tracks: list[Track]) -> dict[str, PlayStats]:
        """Return ``{track_id: PlayStats}``.

        A track absent from the result is treated as "no listens recorded".
        """
        ...

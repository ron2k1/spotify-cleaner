"""Turn core dataclasses into plain JSON-able dicts for the API, and pull in
the one thing the core model deliberately omits: album art.

``Track`` has no album_art_url -- the CLI never needs it, so the frozen model
stays lean. The web table wants thumbnails, so we fetch them here in a separate
batched pass rather than widening the core model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from ..models import ProgressFn, ScoredTrack

if TYPE_CHECKING:
    import spotipy


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def enrich_album_art(
    sp: "spotipy.Spotify",
    track_ids: Iterable[str],
    progress: Optional[ProgressFn] = None,
) -> dict[str, str]:
    """Map track_id -> a small album-art URL via batched /tracks calls (50/req).

    Best-effort: a track with no images simply gets no entry. Spotify returns
    images largest-first, so the last one is the ~64px thumbnail we want.
    """
    ids = [t for t in track_ids if t]
    art: dict[str, str] = {}
    total = len(ids)
    done = 0
    for batch in _chunks(ids, 50):
        try:
            resp = sp.tracks(batch) or {}
        except Exception as exc:  # noqa: BLE001
            # Album art is a cosmetic enrichment, never the result. A 403 means
            # this Spotify app can't read the catalog /v1/tracks endpoint at all
            # (a development-mode/quota restriction on some apps), so every
            # remaining batch would fail identically -- stop now and return what
            # we have; the table just shows placeholders. Any other (likely
            # transient) error: skip this one batch and keep going.
            if getattr(exc, "http_status", None) == 403:
                break
            resp = {}
        for tr in resp.get("tracks") or []:
            if not tr:
                continue
            images = (tr.get("album") or {}).get("images") or []
            if images:
                art[tr["id"]] = images[-1].get("url")
        done += len(batch)
        if progress is not None:
            progress("enriching", min(done, total), total)
    return art


def track_row(scored: ScoredTrack, art: dict[str, str]) -> dict:
    """One candidate as a flat dict keyed exactly how the React table expects."""
    t = scored.track
    st = scored.stats
    return {
        "track_id": t.track_id,
        "uri": t.uri,
        "name": t.name,
        "artists": list(t.artists),
        "artist_label": ", ".join(t.artists) if t.artists else "(unknown artist)",
        "reason": scored.reason,
        "play_count": st.play_count,
        "last_played": st.last_played.isoformat() if st.last_played else None,
        "in_top": st.in_top,
        "rank": st.rank,
        "note": st.note,
        "is_liked": t.is_liked,
        "playlist_ids": list(t.playlist_ids),
        "playlist_count": len(t.playlist_ids),
        "added_at": t.added_at,
        "album_art_url": art.get(t.track_id),
    }

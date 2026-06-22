"""Turn core dataclasses into the flat JSON dicts the web API returns.

The frozen ``Track`` model deliberately omits album art -- the CLI never needs
it. The web table wants thumbnails, but the catalog endpoint that would supply
them (``/v1/tracks``) is blocked for development-mode Spotify apps, so each row
instead points at the ``/api/art/{id}`` proxy (see ``routers/art.py``). That
proxy resolves a thumbnail lazily via oEmbed, only for the rows a user actually
scrolls into view -- so a large library costs zero art lookups up front.
"""

from __future__ import annotations

from ..models import ScoredTrack


def track_row(scored: ScoredTrack) -> dict:
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
        "confidence": st.confidence,
        "is_liked": t.is_liked,
        "playlist_ids": list(t.playlist_ids),
        "playlist_count": len(t.playlist_ids),
        "added_at": t.added_at,
        # Lazy, same-origin album-art proxy (see routers/art.py). Every row gets
        # a candidate URL; the proxy 404s for tracks with no art and the table
        # falls back to a placeholder icon via the cell's onError handler.
        "album_art_url": f"/api/art/{t.track_id}",
    }

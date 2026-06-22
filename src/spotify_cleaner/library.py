"""Reads the whole library: Liked Songs, playlists, and which playlist each
track sits in. Identical regardless of how we later score listens.

Spotipy is only touched at call time through the ``sp`` client passed in, so
this module has no runtime third-party imports and stays unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Iterator, Optional

from .models import Track

if TYPE_CHECKING:  # type-checker only; never imported at runtime
    import spotipy


@dataclass
class Playlist:
    playlist_id: str
    name: str
    owner_id: str
    public: bool
    snapshot_id: str
    track_uris: list[str] = field(default_factory=list)


@dataclass
class Library:
    """Everything we need to score and clean, indexed for fast joins."""

    tracks: dict[str, Track]  # track_id -> Track
    playlists: dict[str, Playlist]  # playlist_id -> Playlist

    def liked(self) -> list[Track]:
        return [t for t in self.tracks.values() if t.is_liked]


def _artist_names(tr: dict) -> tuple[str, ...]:
    # Spotify can return an artist with a null/missing "name" (relinked,
    # unavailable, or local-file-shadowed tracks). Keep only real string names
    # so a None never reaches ", ".join(...) in Track.label or .strip() in the
    # scorers, both of which would raise mid-run.
    return tuple(
        a["name"]
        for a in tr.get("artists", [])
        if isinstance(a, dict) and a.get("name")
    )


def _id_from_uri(uri: str) -> Optional[str]:
    # "spotify:track:0eGsy..." -> "0eGsy..."; ignore local files / episodes.
    parts = uri.split(":")
    if len(parts) == 3 and parts[1] == "track":
        return parts[2]
    return None


def _paginate(sp: "spotipy.Spotify", page: dict) -> Iterator[dict]:
    """Yield every item across all pages of a Spotify paging object."""
    current: Optional[dict] = page
    while current:
        for item in current.get("items", []):
            yield item
        current = sp.next(current) if current.get("next") else None


def fetch_liked(sp: "spotipy.Spotify") -> dict[str, Track]:
    out: dict[str, Track] = {}
    first = sp.current_user_saved_tracks(limit=50)
    for item in _paginate(sp, first):
        tr = item.get("track") or {}
        tid = tr.get("id")
        if not tid:
            continue  # local file or unavailable track
        out[tid] = Track(
            track_id=tid,
            uri=tr.get("uri", f"spotify:track:{tid}"),
            name=tr.get("name", "(unknown)"),
            artists=_artist_names(tr),
            added_at=item.get("added_at"),
            is_liked=True,
        )
    return out


def fetch_playlists(
    sp: "spotipy.Spotify", owned_only: bool, me_id: str
) -> dict[str, Playlist]:
    out: dict[str, Playlist] = {}
    first = sp.current_user_playlists(limit=50)
    for pl in _paginate(sp, first):
        if not pl:
            continue
        owner = (pl.get("owner") or {}).get("id", "")
        # You can only remove tracks from playlists you own.
        if owned_only and owner != me_id:
            continue
        out[pl["id"]] = Playlist(
            playlist_id=pl["id"],
            name=pl.get("name", "(unnamed)"),
            owner_id=owner,
            public=bool(pl.get("public")),
            snapshot_id=pl.get("snapshot_id", ""),
        )
    return out


def _iter_playlist_items(sp: "spotipy.Spotify", playlist_id: str) -> Iterator[dict]:
    first = sp.playlist_items(
        playlist_id,
        limit=50,  # the read endpoint caps at 50/page (write/delete caps at 100)
        additional_types=("track",),
        fields="items(track(id,uri,name,artists(name))),next",
    )
    yield from _paginate(sp, first)


def build_library(sp: "spotipy.Spotify", owned_only: bool = True) -> Library:
    me_id = sp.me()["id"]
    tracks = fetch_liked(sp)
    playlists = fetch_playlists(sp, owned_only, me_id)

    for pl in playlists.values():
        for item in _iter_playlist_items(sp, pl.playlist_id):
            tr = item.get("track") or {}
            uri = tr.get("uri")
            if not uri:
                continue
            pl.track_uris.append(uri)
            tid = _id_from_uri(uri)
            if tid is None:
                continue
            existing = tracks.get(tid)
            if existing is None:
                # In a playlist but not in Liked Songs.
                tracks[tid] = Track(
                    track_id=tid,
                    uri=uri,
                    name=tr.get("name", "(unknown)"),
                    artists=_artist_names(tr),
                    is_liked=False,
                    playlist_ids=frozenset({pl.playlist_id}),
                )
            else:
                tracks[tid] = replace(
                    existing, playlist_ids=existing.playlist_ids | {pl.playlist_id}
                )

    return Library(tracks=tracks, playlists=playlists)

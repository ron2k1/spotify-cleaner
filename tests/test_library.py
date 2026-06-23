"""Library assembly tests -- no Spotify account, network, or credentials.

These pin the playlist-reading behaviour that build_library depends on. The
regression they guard: Spotify's playlist-items endpoint returns each row's
media object under the key ``item`` (it was ``track`` before a 2025 API
change). Reading the old key silently dropped every playlist track, so a scan
saw only Liked Songs.
"""

from __future__ import annotations

from spotify_cleaner.library import build_library, fetch_playlists


class _FakeSp:
    """Minimal spotipy stand-in for build_library.

    ``playlist_items`` is keyed by playlist id; each row is the raw shape the
    real endpoint returns. Single-page only (``next`` is None), which is all
    build_library's _paginate needs to terminate.
    """

    def __init__(self, me_id, liked=None, playlists=None, items=None):
        self._me = me_id
        self._liked = liked or []
        self._playlists = playlists or []
        self._items = items or {}

    def me(self):
        return {"id": self._me}

    def current_user_saved_tracks(self, limit=50):
        return {"items": self._liked, "total": len(self._liked), "next": None}

    def current_user_playlists(self, limit=50):
        return {"items": self._playlists, "next": None}

    def playlist_items(self, playlist_id, limit=50, additional_types=None, fields=None):
        return {"items": self._items.get(playlist_id, []), "next": None}

    def next(self, page):  # _paginate guards on page["next"], so never reached
        return None


def _playlist(pid="p1", name="Mix", owner="me"):
    return {
        "id": pid,
        "name": name,
        "owner": {"id": owner},
        "public": False,
        "snapshot_id": "snap",
        # The list endpoint reports total=0 even for full playlists; build_library
        # must not trust it -- it reads the items directly.
        "tracks": {"total": 0},
    }


def _row(uri, name="Song", artist="Band", key="item", is_local=False):
    """A playlist row with the media under `key` ('item' = current API shape)."""
    return {
        "is_local": is_local,
        key: {
            "id": uri.split(":")[-1] if uri.startswith("spotify:track:") else None,
            "uri": uri,
            "name": name,
            "artists": [{"name": artist}],
        },
    }


def test_build_library_reads_playlist_track_under_item_key():
    # The regression: a real Spotify track delivered under "item" must enter the
    # library as a playlist-sourced (not liked) track.
    sp = _FakeSp(
        "me",
        liked=[],
        playlists=[_playlist("p1")],
        items={"p1": [_row("spotify:track:x1", "Song", "Band")]},
    )
    lib = build_library(sp, owned_only=True)
    assert "x1" in lib.tracks
    t = lib.tracks["x1"]
    assert t.uri == "spotify:track:x1"
    assert t.is_liked is False
    assert t.artists == ("Band",)
    assert "p1" in t.playlist_ids


def test_build_library_still_reads_legacy_track_key():
    # Defense-in-depth: if Spotify ever serves the old "track" key again, the
    # fallback must still pick the media up.
    sp = _FakeSp(
        "me",
        playlists=[_playlist("p1")],
        items={"p1": [_row("spotify:track:y2", key="track")]},
    )
    lib = build_library(sp, owned_only=True)
    assert "y2" in lib.tracks
    assert "p1" in lib.tracks["y2"].playlist_ids


def test_build_library_merges_playlist_id_onto_liked_track():
    # A track that is both Liked and in a playlist stays is_liked=True but gains
    # the playlist id, so removal can offer to take it out of both places.
    liked = [
        {"track": {"id": "z3", "uri": "spotify:track:z3", "name": "Dup",
                   "artists": [{"name": "Band"}]}}
    ]
    sp = _FakeSp(
        "me",
        liked=liked,
        playlists=[_playlist("p1")],
        items={"p1": [_row("spotify:track:z3", "Dup", "Band")]},
    )
    lib = build_library(sp, owned_only=True)
    t = lib.tracks["z3"]
    assert t.is_liked is True
    assert "p1" in t.playlist_ids


def test_build_library_skips_local_files():
    # Local files have no track id and no play data -- they can't be scored or
    # removed via the API, so they must never enter the scored universe.
    sp = _FakeSp(
        "me",
        playlists=[_playlist("p1")],
        items={"p1": [
            _row("spotify:local:::Some+Local+File:120", is_local=True),
            _row("spotify:track:real1", "Real", "Band"),
        ]},
    )
    lib = build_library(sp, owned_only=True)
    assert "real1" in lib.tracks
    # the local row contributes its uri to the playlist's uri list but no Track
    assert all(t.uri != "spotify:local:::Some+Local+File:120" for t in lib.tracks.values())


def test_fetch_playlists_owned_only_excludes_followed():
    sp = _FakeSp(
        "me",
        playlists=[_playlist("mine", owner="me"), _playlist("theirs", owner="someone")],
    )
    owned = fetch_playlists(sp, owned_only=True, me_id="me")
    assert set(owned) == {"mine"}
    both = fetch_playlists(sp, owned_only=False, me_id="me")
    assert set(both) == {"mine", "theirs"}

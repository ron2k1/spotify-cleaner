"""Logic tests that need no Spotify account, network, or credentials.

They exercise the candidacy rules and the GDPR parser against small fixtures
that mirror the documented export schemas.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from spotify_cleaner.library import Library
from spotify_cleaner.models import PlayStats, Track
from spotify_cleaner.planner import plan
from spotify_cleaner.scoring.gdpr import GdprScorer


def _lib(tracks: list[Track]) -> Library:
    return Library(tracks={t.track_id: t for t in tracks}, playlists={})


def _t(tid: str, name: str = "Song", artist: str = "Band") -> Track:
    return Track(tid, f"spotify:track:{tid}", name, (artist,), is_liked=True)


# --- count mode -------------------------------------------------------------


def test_count_mode_flags_low_plays_only():
    lib = _lib([_t("a"), _t("b")])
    stats = {
        "a": PlayStats("gdpr", play_count=1),
        "b": PlayStats("gdpr", play_count=200),
    }
    cands = plan(lib, stats, "count", min_plays=2)
    assert [c.track.track_id for c in cands] == ["a"]


def test_count_mode_missing_stats_is_candidate():
    # A track with no data at all counts as 0 plays -> flagged.
    lib = _lib([_t("a")])
    cands = plan(lib, {}, "count", min_plays=2)
    assert len(cands) == 1 and "0 play" in cands[0].reason


def test_count_mode_unknown_count_not_flagged():
    # play_count=None means "lookup failed / unknown", NOT zero. It must not
    # be treated as a low-play deletion candidate.
    lib = _lib([_t("a")])
    stats = {"a": PlayStats("lastfm", play_count=None, note="lookup failed")}
    cands = plan(lib, stats, "count", min_plays=2)
    assert cands == []


def test_count_mode_stale_filter():
    old = datetime.now(timezone.utc) - timedelta(days=400)
    lib = _lib([_t("a")])
    stats = {"a": PlayStats("gdpr", play_count=50, last_played=old)}
    cands = plan(lib, stats, "count", min_plays=2, stale_days=365)
    assert len(cands) == 1 and "not played since" in cands[0].reason


def test_count_mode_orders_least_listened_first():
    lib = _lib([_t("a"), _t("b"), _t("c")])
    stats = {
        "a": PlayStats("gdpr", play_count=2),
        "b": PlayStats("gdpr", play_count=0),
        "c": PlayStats("gdpr", play_count=1),
    }
    cands = plan(lib, stats, "count", min_plays=2)
    assert [c.track.track_id for c in cands] == ["b", "c", "a"]


# --- rank mode --------------------------------------------------------------


def test_rank_mode_flags_not_in_top():
    lib = _lib([_t("a"), _t("b")])
    stats = {
        "a": PlayStats("toptracks", in_top=True, rank=3),
        "b": PlayStats("toptracks", in_top=False),
    }
    cands = plan(lib, stats, "rank")
    assert [c.track.track_id for c in cands] == ["b"]


def test_rank_mode_orders_oldest_added_first():
    # Spotify returns saved tracks newest-first, so that is the input order.
    # In rank mode none of these have a play count, last-play date, or rank,
    # so the first three sort terms tie for all of them. Without the added_at
    # tie-break a stable sort would leave them newest-first (the bug: a song
    # you just saved sitting atop the "least listened" list). They must come
    # back oldest-added first instead.
    def _at(tid: str, added_at: str) -> Track:
        return Track(tid, f"spotify:track:{tid}", tid, ("B",),
                     is_liked=True, added_at=added_at)

    lib = _lib([
        _at("new", "2024-06-01T00:00:00Z"),
        _at("mid", "2022-01-01T00:00:00Z"),
        _at("old", "2019-03-15T00:00:00Z"),
    ])
    stats = {tid: PlayStats("toptracks", in_top=False) for tid in ("new", "mid", "old")}
    cands = plan(lib, stats, "rank")
    assert [c.track.track_id for c in cands] == ["old", "mid", "new"]


def test_added_at_only_breaks_ties_in_count_mode():
    # When real play counts differ they must still dominate; added_at only
    # decides between tracks with identical listening evidence. Here two tracks
    # have 0 plays, so the older-added one comes first; a 1-play track sorts
    # last despite being the oldest, because count dominates the tie-break.
    older = Track("o", "spotify:track:o", "o", ("B",), is_liked=True,
                  added_at="2020-01-01T00:00:00Z")
    newer = Track("n", "spotify:track:n", "n", ("B",), is_liked=True,
                  added_at="2024-01-01T00:00:00Z")
    busy = Track("b", "spotify:track:b", "b", ("B",), is_liked=True,
                 added_at="2018-01-01T00:00:00Z")  # oldest, but played more
    lib = _lib([newer, older, busy])
    stats = {
        "n": PlayStats("gdpr", play_count=0),
        "o": PlayStats("gdpr", play_count=0),
        "b": PlayStats("gdpr", play_count=1),
    }
    cands = plan(lib, stats, "count", min_plays=2)
    assert [c.track.track_id for c in cands] == ["o", "n", "b"]


# --- GDPR parser ------------------------------------------------------------


def test_gdpr_modern_schema_counts_and_threshold(tmp_path):
    rows = [
        {"ts": "2024-01-01T10:00:00Z", "ms_played": 200000,
         "spotify_track_uri": "spotify:track:a",
         "master_metadata_track_name": "A", "master_metadata_album_artist_name": "X"},
        {"ts": "2024-02-01T10:00:00Z", "ms_played": 200000,
         "spotify_track_uri": "spotify:track:a",
         "master_metadata_track_name": "A", "master_metadata_album_artist_name": "X"},
        {"ts": "2024-03-01T10:00:00Z", "ms_played": 5000,  # skip, under 30s
         "spotify_track_uri": "spotify:track:a",
         "master_metadata_track_name": "A", "master_metadata_album_artist_name": "X"},
    ]
    (tmp_path / "Streaming_History_Audio_2024_0.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    a = Track("a", "spotify:track:a", "A", ("X",), is_liked=True)
    stats = GdprScorer(str(tmp_path)).score([a])
    assert stats["a"].play_count == 2  # the 5s skip is excluded
    assert stats["a"].last_played is not None and stats["a"].last_played.year == 2024


def test_gdpr_legacy_schema_matches_by_name(tmp_path):
    rows = [{"endTime": "2020-01-09 15:15", "msPlayed": 200000,
             "trackName": "Song", "artistName": "Band"}]
    (tmp_path / "StreamingHistory0.json").write_text(json.dumps(rows), encoding="utf-8")
    # track id is unknown to the export, so it must match on artist+title
    t = Track("unknown-id", "spotify:track:unknown-id", "Song", ("Band",), is_liked=True)
    stats = GdprScorer(str(tmp_path)).score([t])
    assert stats["unknown-id"].play_count == 1


def test_gdpr_offsetless_iso_is_tz_aware_and_stale_safe(tmp_path):
    # An ISO ts with no 'Z' and no offset must still yield a tz-AWARE datetime,
    # otherwise the stale-days comparison in plan() raises TypeError.
    rows = [{"ts": "2019-11-05T14:28:00", "ms_played": 200000,
             "spotify_track_uri": "spotify:track:a",
             "master_metadata_track_name": "A", "master_metadata_album_artist_name": "X"}]
    (tmp_path / "h.json").write_text(json.dumps(rows), encoding="utf-8")
    a = Track("a", "spotify:track:a", "A", ("X",), is_liked=True)
    stats = GdprScorer(str(tmp_path)).score([a])
    assert stats["a"].last_played is not None
    assert stats["a"].last_played.tzinfo is not None
    # The naive-vs-aware comparison would crash here before the fix.
    cands = plan(_lib([a]), stats, "count", min_plays=0, stale_days=365)
    assert len(cands) == 1 and "not played since" in cands[0].reason


def test_gdpr_matches_any_listed_artist(tmp_path):
    # Export keys the play on album artist "Main"; the library track's primary
    # artist is the featured "Guest" but it also lists "Main" -> must match.
    rows = [{"endTime": "2024-01-01 10:00", "msPlayed": 200000,
             "trackName": "Collab", "artistName": "Main"}]
    (tmp_path / "StreamingHistory0.json").write_text(json.dumps(rows), encoding="utf-8")
    t = Track("uid", "spotify:track:uid", "Collab", ("Guest", "Main"), is_liked=True)
    stats = GdprScorer(str(tmp_path)).score([t])
    assert stats["uid"].play_count == 1


def test_gdpr_never_played_track(tmp_path):
    rows = [{"ts": "2024-01-01T10:00:00Z", "ms_played": 200000,
             "spotify_track_uri": "spotify:track:other",
             "master_metadata_track_name": "Other", "master_metadata_album_artist_name": "Z"}]
    (tmp_path / "h.json").write_text(json.dumps(rows), encoding="utf-8")
    a = Track("a", "spotify:track:a", "A", ("X",), is_liked=True)
    stats = GdprScorer(str(tmp_path)).score([a])
    assert stats["a"].play_count == 0 and "never played" in stats["a"].note

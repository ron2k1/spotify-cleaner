"""Tests for the pre-delete restore manifest + its CSV formula-injection guard.

The manifest is written on every real delete, and is meant to be opened in a
spreadsheet -- so the same CWE-1236 defang the scan export has must apply here.
None of this touches Spotify; it writes local files under a temp backups/ dir.
"""

from __future__ import annotations

import csv
from pathlib import Path

from spotify_cleaner import backup, cleaner
from spotify_cleaner.csvsafe import csv_safe
from spotify_cleaner.library import Library, Playlist
from spotify_cleaner.models import PlayStats, ScoredTrack, Track


class _FakeSp:
    """Spotify stub: the removal calls are no-ops so apply() exercises its own
    bookkeeping (the backup safety net) without any network."""

    def current_user_saved_tracks_delete(self, tracks=None):
        pass

    def playlist_remove_all_occurrences_of_items(self, pid, batch):
        pass


def test_csv_safe_quotes_formula_leads_only():
    # Risky leads get a quote prefix; ordinary text is untouched.
    assert csv_safe('=HYPERLINK("http://evil","x")').startswith("'=")
    assert csv_safe("+1") == "'+1"
    assert csv_safe("-cmd") == "'-cmd"
    assert csv_safe("@SUM(1)") == "'@SUM(1)"
    assert csv_safe("\tx") == "'\tx"
    assert csv_safe("Normal Song") == "Normal Song"
    assert csv_safe(None) == ""
    assert csv_safe(0) == "0"


def _candidate(name: str, artist: str, pid: str) -> ScoredTrack:
    track = Track(
        "t1",
        "spotify:track:t1",
        name,
        (artist,),
        is_liked=True,
        playlist_ids=frozenset({pid}),
    )
    return ScoredTrack(track, PlayStats("gdpr", play_count=0), reason="0 plays")


def test_write_backup_defangs_csv_formula_injection(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLEANER_BACKUP_DIR", str(tmp_path))
    cand = _candidate('=HYPERLINK("http://evil","x")', "@evil", "pl1")
    library = Library(
        tracks={cand.track.track_id: cand.track},
        playlists={
            "pl1": Playlist("pl1", "+danger", "me", False, "snap", [])
        },
    )

    backup.write_backup(
        [cand], library, unlike=True, remove_from_playlists=True
    )

    csv_file = next(Path(tmp_path).glob("backup-*.csv"))
    rows = list(csv.reader(csv_file.read_text(encoding="utf-8").splitlines()))
    data = rows[1]  # row 0 is the header
    # The malicious name, artist and (collaborator) playlist name are all quoted
    # so a spreadsheet treats them as text, not live formulas.
    assert any(cell.startswith("'=HYPERLINK") for cell in data)
    assert "'@evil" in data
    assert "'+danger" in data


def test_write_backup_writes_json_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLEANER_BACKUP_DIR", str(tmp_path))
    cand = _candidate("Normal Song", "Band", "pl1")
    library = Library(
        tracks={cand.track.track_id: cand.track},
        playlists={"pl1": Playlist("pl1", "Chill", "me", False, "snap", [])},
    )

    manifest = backup.write_backup(
        [cand], library, unlike=True, remove_from_playlists=False
    )

    assert manifest.exists() and manifest.suffix == ".json"
    assert manifest.read_text(encoding="utf-8").find('"count": 1') != -1


def test_apply_reports_backup_written_true_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLEANER_BACKUP_DIR", str(tmp_path))
    cand = _candidate("Normal Song", "Band", "pl1")
    library = Library(
        tracks={cand.track.track_id: cand.track},
        playlists={"pl1": Playlist("pl1", "Chill", "me", False, "snap", [])},
    )
    summary = cleaner.apply(
        _FakeSp(), library, [cand],
        confirm=True, unlike=True, remove_from_playlists=False,
    )
    assert summary["backup_written"] is True


def test_apply_reports_backup_written_false_when_manifest_fails(
    tmp_path, monkeypatch
):
    # An unwritable backups/ dir must NOT silently swallow the safety-net loss:
    # the web apply job reads summary["backup_written"] to warn the user.
    monkeypatch.setenv("SPOTIFY_CLEANER_BACKUP_DIR", str(tmp_path))

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(backup, "write_backup", boom)
    cand = _candidate("Normal Song", "Band", "pl1")
    library = Library(
        tracks={cand.track.track_id: cand.track},
        playlists={"pl1": Playlist("pl1", "Chill", "me", False, "snap", [])},
    )
    summary = cleaner.apply(
        _FakeSp(), library, [cand],
        confirm=True, unlike=True, remove_from_playlists=False,
    )
    assert summary["backup_written"] is False

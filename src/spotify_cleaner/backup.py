"""Write a restore manifest + audit trail before any irreversible delete.

The cleaner removes tracks from Liked Songs and owned playlists -- Spotify
offers no undo for either. So just before committing, we snapshot exactly what
is about to be removed (and from which playlists) to a timestamped file under a
gitignored ``backups/`` folder, and append one line to an append-only audit log.
The manifest captures enough to put everything back by hand: each track's URI,
whether it was liked, and the playlists it belonged to (re-liking is trivial,
but restoring playlist placement needs the membership the delete destroys).

Nothing here ever touches Spotify; it only records intent + outcome locally.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .csvsafe import csv_safe

if TYPE_CHECKING:
    from .library import Library
    from .models import ScoredTrack


def _backup_dir() -> Path:
    # Default to ./backups (covered by .gitignore); overridable via env for
    # tests or an odd working directory. Created lazily so a dry run that never
    # reaches the apply path leaves no folder behind.
    return Path(os.getenv("SPOTIFY_CLEANER_BACKUP_DIR", "backups"))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rows(candidates: list["ScoredTrack"], library: "Library") -> list[dict]:
    """One restore record per candidate, with its playlist memberships resolved."""
    rows: list[dict] = []
    for c in candidates:
        t = c.track
        names = [
            library.playlists[pid].name
            for pid in t.playlist_ids
            if pid in library.playlists
        ]
        rows.append(
            {
                "track_id": t.track_id,
                "uri": t.uri,
                "name": t.name,
                "artists": ", ".join(t.artists),
                "is_liked": t.is_liked,
                "playlist_ids": sorted(t.playlist_ids),
                "playlist_names": names,
                "reason": c.reason,
                "play_count": c.stats.play_count,
            }
        )
    return rows


def write_backup(
    candidates: list["ScoredTrack"],
    library: "Library",
    *,
    unlike: bool,
    remove_from_playlists: bool,
) -> Path:
    """Write a timestamped JSON+CSV manifest of what is about to be removed.

    Returns the JSON manifest path. Raises ``OSError`` on a write failure so the
    caller can decide whether to proceed without a safety net.
    """
    d = _backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    rows = _rows(candidates, library)

    manifest = d / f"backup-{stamp}.json"
    manifest.write_text(
        json.dumps(
            {
                "created_utc": stamp,
                "unlike": unlike,
                "remove_from_playlists": remove_from_playlists,
                "count": len(rows),
                "tracks": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # A flat CSV alongside the JSON, for eyeballing in a spreadsheet.
    csv_path = d / f"backup-{stamp}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "track_id",
                "uri",
                "name",
                "artists",
                "is_liked",
                "playlist_names",
                "reason",
                "play_count",
            ]
        )
        for r in rows:
            # Same formula-injection defang as the scan export: track/artist/
            # playlist names are attacker-influenceable and this file is meant
            # to be opened in a spreadsheet.
            writer.writerow(
                [
                    csv_safe(r["track_id"]),
                    csv_safe(r["uri"]),
                    csv_safe(r["name"]),
                    csv_safe(r["artists"]),
                    r["is_liked"],
                    csv_safe(" | ".join(r["playlist_names"])),
                    csv_safe(r["reason"]),
                    r["play_count"],
                ]
            )
    return manifest


def append_audit(
    *,
    manifest: Optional[Path],
    summary: dict,
    unlike: bool,
    remove_from_playlists: bool,
) -> None:
    """Append one JSON line recording the action's outcome. Best-effort.

    Logs counts only -- never tokens or response bodies -- and swallows its own
    I/O errors so a logging failure can never mask a completed (or partial)
    delete.
    """
    d = _backup_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        line = {
            "ts_utc": _stamp(),
            "manifest": manifest.name if manifest else None,
            "unlike": unlike,
            "remove_from_playlists": remove_from_playlists,
            "unliked": summary.get("unliked", 0),
            "removed_from_playlists": summary.get("removed_from_playlists", 0),
            "playlists_touched": summary.get("playlists_touched", 0),
        }
        with (d / "audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass

"""Scorer backed by Spotify's "Extended Streaming History" GDPR export.

This is the only source of *true* lifetime play counts. Each row in the JSON
is one play event; we group by track and count plays over a minimum-duration
threshold (to drop skips), recording the most recent play timestamp.

Two export schemas exist and are both handled:
  * modern: ``ts`` / ``ms_played`` / ``spotify_track_uri`` / ``master_metadata_*``
  * legacy: ``endTime`` / ``msPlayed`` / ``trackName`` / ``artistName``
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models import PlayStats, Track

MIN_MS = 30_000  # a "real" play: at least 30s, matching common scrobble rules
_SEP = "␟"  # unlikely separator for the artist/title fallback key


def _parse_ts(row: dict) -> Optional[datetime]:
    raw = row.get("ts") or row.get("endTime")
    if not raw:
        return None
    try:
        if "T" in raw:  # ISO-8601, e.g. "2019-11-05T14:28:00Z"
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            # An offset-less value (no "Z", no +hh:mm) parses tz-naive. Force
            # UTC so every last_played is aware and comparable in the planner;
            # otherwise the stale-days check raises "can't compare naive/aware".
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        # legacy "2020-01-09 15:15"
        return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _name_key(artist: str, name: str) -> str:
    return f"{artist.strip().lower()}{_SEP}{name.strip().lower()}"


def _row_keys(row: dict) -> tuple[Optional[str], str]:
    """Return ``(spotify_id_or_None, name_key)`` for one play row."""
    uri = row.get("spotify_track_uri")
    sid = uri.split(":")[-1] if uri and uri.startswith("spotify:track:") else None
    name = row.get("master_metadata_track_name") or row.get("trackName") or ""
    artist = row.get("master_metadata_album_artist_name") or row.get("artistName") or ""
    return sid, _name_key(artist, name)


class GdprScorer:
    name = "gdpr"
    mode = "count"

    def __init__(self, export_dir: str, min_ms: int = MIN_MS):
        self.export_dir = Path(export_dir)
        self.min_ms = min_ms

    def _load_rows(self):
        files = sorted(self.export_dir.glob("*.json"))
        if not files:
            raise SystemExit(
                f"No .json files found in {self.export_dir}. Point --gdpr-dir at "
                "your unzipped Extended Streaming History folder."
            )
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, list):
                yield from data

    def score(self, tracks: list[Track]) -> dict[str, PlayStats]:
        # rec = [count, last_played]; two indexes so a row can be matched
        # by exact id, with an artist/title fallback for legacy rows.
        by_id: dict[str, list] = defaultdict(lambda: [0, None])
        by_name: dict[str, list] = defaultdict(lambda: [0, None])

        for row in self._load_rows():
            ms = row.get("ms_played", row.get("msPlayed", 0)) or 0
            if ms < self.min_ms:
                continue
            sid, name_key = _row_keys(row)
            ts = _parse_ts(row)
            for bucket, key in ((by_id, sid), (by_name, name_key)):
                if not key:
                    continue
                rec = bucket[key]
                rec[0] += 1
                if ts and (rec[1] is None or ts > rec[1]):
                    rec[1] = ts

        out: dict[str, PlayStats] = {}
        for t in tracks:
            rec = by_id.get(t.track_id)
            if rec is None:  # fall back to artist/title for export rows lacking a URI
                # The export's name key uses the *album* artist, but a track can
                # list several performing artists. Try each so a collaboration
                # whose primary artist differs from the album artist still hits.
                for artist in t.artists or ("",):
                    rec = by_name.get(_name_key(artist, t.name))
                    if rec:
                        break
            count = rec[0] if rec else 0
            last = rec[1] if rec else None
            if count:
                note = f"{count} plays" + (f", last {last.date()}" if last else "")
            else:
                note = "never played (in export)"
            out[t.track_id] = PlayStats(
                source=self.name, play_count=count, last_played=last, note=note
            )
        return out

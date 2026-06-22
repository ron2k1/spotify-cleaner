"""Executes (or previews) the cleanup.

Destructive actions are OFF by default: nothing is removed unless BOTH
``apply`` is requested on the CLI AND ``confirm`` is True (the caller types
DELETE). The two-key design makes an accidental wipe very hard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from . import backup
from .library import Library
from .models import ProgressFn, ScoredTrack

if TYPE_CHECKING:
    import spotipy


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def preview(candidates: list[ScoredTrack], limit: int = 50) -> None:
    if not candidates:
        print("No cleanup candidates found. Your library looks tidy.")
        return
    print(f"\n{len(candidates)} cleanup candidate(s) (showing up to {limit}):\n")
    print(f"{'#':>3}  {'plays':>5}  {'reason':<26}  track")
    print("-" * 78)
    for i, c in enumerate(candidates[:limit], 1):
        pc = "-" if c.stats.play_count is None else str(c.stats.play_count)
        print(f"{i:>3}  {pc:>5}  {c.reason[:26]:<26}  {c.track.label[:46]}")
    if len(candidates) > limit:
        print(f"... and {len(candidates) - limit} more")


def apply(
    sp: "spotipy.Spotify",
    library: Library,
    candidates: list[ScoredTrack],
    *,
    confirm: bool,
    unlike: bool,
    remove_from_playlists: bool,
    progress: Optional[ProgressFn] = None,
) -> dict:
    """Remove candidates from playlists and/or unlike them. No-op unless confirm."""
    summary = {"unliked": 0, "removed_from_playlists": 0, "playlists_touched": 0}

    if not confirm:
        print("\n[dry run] Nothing was changed. Re-run with --apply to act.")
        return summary
    if not candidates:
        return summary

    cand_ids = {c.track.track_id for c in candidates}

    # Safety net: snapshot what is about to be removed (and from which playlists)
    # so it can be restored by hand -- Spotify has no undo. If the snapshot can't
    # be written we warn and continue rather than block: the user explicitly
    # typed DELETE, and the deletes themselves are idempotent.
    manifest = None
    try:
        manifest = backup.write_backup(
            candidates,
            library,
            unlike=unlike,
            remove_from_playlists=remove_from_playlists,
        )
        print(f"Backup written to {manifest}")
    except OSError as exc:
        print(
            f"\nWarning: could not write backup ({type(exc).__name__}); "
            "proceeding without a restore manifest."
        )

    try:
        if remove_from_playlists:
            # Resolve which playlists actually contain a candidate first, so the
            # progress total is the real count of playlists we'll touch, not the
            # whole library (most playlists have no matches).
            pending = [
                (
                    pl,
                    [
                        u
                        for u in pl.track_uris
                        if u.startswith("spotify:track:")
                        and u.split(":")[-1] in cand_ids
                    ],
                )
                for pl in library.playlists.values()
            ]
            pending = [(pl, uris) for pl, uris in pending if uris]
            total_pl = len(pending)
            for done, (pl, uris) in enumerate(pending, 1):
                for batch in _chunks(uris, 100):  # playlist removal cap is 100/call
                    sp.playlist_remove_all_occurrences_of_items(pl.playlist_id, batch)
                    summary["removed_from_playlists"] += len(batch)
                summary["playlists_touched"] += 1
                if progress is not None:
                    progress("removing_from_playlists", done, total_pl)

        if unlike:
            liked_ids = [c.track.track_id for c in candidates if c.track.is_liked]
            total_liked = len(liked_ids)
            for batch in _chunks(liked_ids, 50):  # saved-track removal cap is 50/call
                sp.current_user_saved_tracks_delete(tracks=batch)
                summary["unliked"] += len(batch)
                if progress is not None:
                    progress("unliking", summary["unliked"], total_liked)
    except Exception as exc:
        # A batch may have committed server-side before this raised. Record the
        # partial outcome in the audit log, then show what got through (only the
        # error TYPE, never the message — it can carry response bodies/tokens)
        # and re-raise. Both ops are idempotent, so re-running the same command
        # safely finishes the job.
        backup.append_audit(
            manifest=manifest,
            summary=summary,
            unlike=unlike,
            remove_from_playlists=remove_from_playlists,
        )
        print(
            f"\nInterrupted by {type(exc).__name__}. So far: unliked "
            f"{summary['unliked']}, removed {summary['removed_from_playlists']} "
            f"playlist entries across {summary['playlists_touched']} playlist(s)."
            "\nThese operations are idempotent - re-run the same command to "
            "finish; already-removed tracks are simply skipped."
        )
        raise

    backup.append_audit(
        manifest=manifest,
        summary=summary,
        unlike=unlike,
        remove_from_playlists=remove_from_playlists,
    )
    print(
        f"\nDone. Unliked {summary['unliked']}, removed "
        f"{summary['removed_from_playlists']} playlist entries across "
        f"{summary['playlists_touched']} playlist(s)."
    )
    return summary

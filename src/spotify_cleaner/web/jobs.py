"""Background jobs (scan, apply) + the SSE event engine that streams them.

Why threads at all: the whole core (spotipy, the scorers) is synchronous and
blocking. Running it in a daemon thread keeps the event loop free, and a
``threading.Condition`` lets the async SSE generator wait for new events
without busy-polling. Each job keeps a full event *log* so a reconnecting
client can replay from its ``Last-Event-ID`` rather than lose progress.

This is a single-process, single-user local app, so an in-memory job store is
exactly right -- no database, no broker, no cross-process state.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional

from .. import cleaner
from ..library import build_library
from ..planner import plan
from .serialize import track_row

if TYPE_CHECKING:
    import spotipy
    from fastapi import Request


@dataclass
class Event:
    id: int
    type: str  # "phase" | "progress" | "log" | "done" | "error"
    data: dict


class Job:
    """A running (then terminal) unit of work with an append-only event log."""

    def __init__(self, job_id: str, kind: str):
        self.id = job_id
        self.kind = kind
        self.events: list[Event] = []
        self.seq = 0
        self.status = "running"  # "running" | "done" | "error"
        self.error: Optional[str] = None
        self.result: Any = None
        self._cond = threading.Condition()

    def emit(self, type: str, **data: Any) -> None:
        with self._cond:
            self.seq += 1
            self.events.append(Event(self.seq, type, dict(data)))
            if type == "done":
                self.status = "done"
            elif type == "error":
                self.status = "error"
            self._cond.notify_all()

    def events_after(self, after_id: int) -> list[Event]:
        with self._cond:
            return [e for e in self.events if e.id > after_id]

    def wait(self, after_id: int, timeout: float) -> None:
        """Block until an event newer than ``after_id`` exists, or timeout."""
        with self._cond:
            if self.events and self.events[-1].id > after_id:
                return
            self._cond.wait(timeout=timeout)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        job = Job(uuid.uuid4().hex, kind)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


# One manager for the process. Routers import this singleton directly; there is
# no benefit to per-request injection in a single-user local server.
manager = JobManager()


def _progress(job: Job):
    def emit(phase: str, current: int, total: Optional[int]) -> None:
        job.emit("progress", phase=phase, current=current, total=total)

    return emit


def run_scan(
    job: Job,
    sp: "spotipy.Spotify",
    scorer: Any,
    *,
    all_tracks: bool,
    min_plays: int,
    stale_days: Optional[int],
    grace_days: Optional[int] = None,
) -> None:
    """Read -> score -> plan -> serialize. Same pipeline as cli.main, observable."""
    try:
        prog = _progress(job)
        job.emit(
            "phase",
            phase="reading_library",
            message="Reading your library (Liked Songs + owned playlists)…",
        )
        library = build_library(sp, owned_only=True, progress=prog)
        liked = library.liked()
        job.emit(
            "log",
            message=(
                f"{len(liked)} liked, {len(library.playlists)} owned playlists, "
                f"{len(library.tracks)} unique tracks."
            ),
        )

        universe = list(library.tracks.values()) if all_tracks else liked
        job.emit(
            "phase",
            phase="scoring",
            message=f"Scoring {len(universe)} track(s) via '{scorer.name}'…",
        )
        stats = scorer.score(universe, progress=prog)

        job.emit("phase", phase="planning", message="Selecting cleanup candidates…")
        candidates = plan(
            library,
            stats,
            scorer.mode,
            liked_only=not all_tracks,
            min_plays=min_plays,
            stale_days=stale_days,
            grace_days=grace_days,
        )

        rows = [track_row(c) for c in candidates]

        job.result = {
            "library": library,
            "candidates": candidates,
            "rows": rows,
            "source": scorer.name,
            "mode": scorer.mode,
        }
        job.emit("done", count=len(rows))
    except Exception as exc:  # noqa: BLE001 - surface the type only, never a message
        job.error = type(exc).__name__
        job.emit("error", error=type(exc).__name__)


def run_apply(
    job: Job,
    sp: "spotipy.Spotify",
    scan_job: Job,
    *,
    track_ids: list[str],
    unlike: bool,
    remove_from_playlists: bool,
) -> None:
    """Apply the (already DELETE-confirmed, server-side) removal to a subset."""
    try:
        prog = _progress(job)
        wanted = set(track_ids)
        candidates = scan_job.result["candidates"]
        selected = [c for c in candidates if c.track.track_id in wanted]
        job.emit(
            "phase",
            phase="applying",
            message=f"Removing {len(selected)} track(s)…",
        )
        summary = cleaner.apply(
            sp,
            scan_job.result["library"],
            selected,
            confirm=True,  # the typed-DELETE gate was validated in the router
            unlike=unlike,
            remove_from_playlists=remove_from_playlists,
            progress=prog,
        )
        job.result = summary
        job.emit("done", **summary)
    except Exception as exc:  # noqa: BLE001 - type only; the op is idempotent
        job.error = type(exc).__name__
        job.emit("error", error=type(exc).__name__)


async def sse_events(
    job: Job, request: "Request", last_event_id: int = 0
) -> AsyncIterator[dict]:
    """Yield SSE dicts for a job, replaying anything after ``last_event_id``.

    Parks in a worker thread between events (no busy loop) and bails the moment
    the client disconnects or a terminal event is sent.
    """
    last = last_event_id
    while True:
        for ev in job.events_after(last):
            last = ev.id
            yield {"id": str(ev.id), "event": ev.type, "data": json.dumps(ev.data)}
            if ev.type in ("done", "error"):
                return
        if await request.is_disconnected():
            return
        await asyncio.to_thread(job.wait, last, 10.0)

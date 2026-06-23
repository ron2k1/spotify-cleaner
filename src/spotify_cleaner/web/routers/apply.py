"""Apply removals to a selected subset of a finished scan.

Two independent keys, mirroring the CLI's safety design:
  1. the client must POST the literal ``confirm: "DELETE"``;
  2. at least one of unlike / remove_from_playlists must be on.
Only then does a worker call ``cleaner.apply(..., confirm=True)``. The scan job
holds the resolved Library + candidates, so apply reuses them by id -- no
re-reading the library, and no chance of acting on a stale plan.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from .. import oauth
from ..jobs import manager, run_apply, sse_events
from ..schemas import ApplyRequest, JobStarted

router = APIRouter(prefix="/api", tags=["apply"])


@router.post("/apply", response_model=JobStarted)
def start_apply(req: ApplyRequest) -> JobStarted:
    if req.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="confirmation_required")
    if not (req.unlike or req.remove_from_playlists):
        raise HTTPException(status_code=400, detail="no_action_selected")

    scan_job = manager.get(req.scan_job_id)
    if scan_job is None or scan_job.status != "done" or not scan_job.result:
        raise HTTPException(status_code=409, detail="scan_not_ready")

    cfg = oauth.load_config(req.profile)
    sp = oauth.client_for(cfg)
    if sp is None:
        raise HTTPException(status_code=401, detail="not_connected")

    job = manager.create("apply")
    threading.Thread(
        target=run_apply,
        args=(job, sp, scan_job),
        kwargs=dict(
            track_ids=req.track_ids,
            unlike=req.unlike,
            remove_from_playlists=req.remove_from_playlists,
        ),
        daemon=True,
    ).start()
    return JobStarted(job_id=job.id)


@router.get("/apply/{job_id}/events")
async def apply_events(job_id: str, request: Request) -> EventSourceResponse:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    last = int(request.headers.get("last-event-id") or 0)
    return EventSourceResponse(sse_events(job, request, last))

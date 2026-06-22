"""Start a scan, stream its progress, fetch its candidate rows.

A scan always needs a connected Spotify client -- even ``gdpr``/``lastfm``,
because the *library* (which tracks are liked / in which playlists) only comes
from Spotify. The source only changes how those tracks are *scored*.
"""

from __future__ import annotations

import os
import threading

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ...config import LastfmConfig
from ...scoring.gdpr import GdprScorer
from ...scoring.lastfm import LastfmScorer
from ...scoring.toptracks import TopTracksScorer
from .. import oauth
from ..jobs import manager, run_scan, sse_events
from ..schemas import JobStarted, ScanRequest
from .gdpr import resolve_gdpr

router = APIRouter(prefix="/api", tags=["scan"])


def _build_scorer(req: ScanRequest, sp):
    if req.source == "gdpr":
        return GdprScorer(str(resolve_gdpr(req.gdpr_token)), min_ms=req.min_ms)
    if req.source == "lastfm":
        if req.lastfm_user:
            os.environ["LASTFM_USERNAME"] = req.lastfm_user
        try:
            lf = LastfmConfig.from_env()
        except SystemExit:
            raise HTTPException(status_code=400, detail="lastfm_not_configured")
        return LastfmScorer(lf.api_key, lf.username)
    return TopTracksScorer(sp, time_range=req.time_range, top_n=req.top_n)


@router.post("/scan", response_model=JobStarted)
def start_scan(req: ScanRequest) -> JobStarted:
    cfg = oauth.load_config(req.profile)  # NotConfigured -> 503
    sp = oauth.client_for(cfg)
    if sp is None:
        raise HTTPException(status_code=401, detail="not_connected")
    scorer = _build_scorer(req, sp)

    job = manager.create("scan")
    threading.Thread(
        target=run_scan,
        args=(job, sp, scorer),
        kwargs=dict(
            all_tracks=req.all_tracks,
            min_plays=req.min_plays,
            stale_days=req.stale_days,
            grace_days=req.grace_days,
        ),
        daemon=True,
    ).start()
    return JobStarted(job_id=job.id)


@router.get("/scan/{job_id}/events")
async def scan_events(job_id: str, request: Request) -> EventSourceResponse:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    last = int(request.headers.get("last-event-id") or 0)
    return EventSourceResponse(sse_events(job, request, last))


@router.get("/scan/{job_id}/result")
def scan_result(job_id: str) -> dict:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    if job.status == "error":
        raise HTTPException(status_code=500, detail=job.error or "scan_failed")
    if job.status != "done" or not job.result:
        raise HTTPException(status_code=409, detail="scan_not_ready")
    r = job.result
    return {
        "count": len(r["rows"]),
        "source": r["source"],
        "mode": r["mode"],
        "rows": r["rows"],
    }

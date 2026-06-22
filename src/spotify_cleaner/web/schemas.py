"""Pydantic request/response contracts.

Pydantic v2 validates every inbound body at the edge, so by the time a value
reaches the core it's already the right type and within range -- the same
guard the CLI gets from argparse, expressed once for the HTTP layer.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ConfigInfo(BaseModel):
    configured: bool  # are SPOTIFY_CLIENT_ID/_SECRET set?
    redirect_uri: str  # echo it so the UI can show "register this exact URI"


class AuthStatus(BaseModel):
    profile: str
    connected: bool
    display_name: Optional[str] = None
    error: Optional[str] = None  # an exception *type* name only, never a message


class ProfileInfo(BaseModel):
    id: str
    connected: bool


class ScanRequest(BaseModel):
    source: Literal["toptracks", "gdpr", "lastfm"] = "toptracks"
    profile: str = "default"
    all_tracks: bool = False
    min_plays: int = Field(2, ge=0)
    stale_days: Optional[int] = Field(None, ge=1)
    grace_days: Optional[int] = Field(None, ge=1)  # protect tracks added recently
    time_range: Literal["short_term", "medium_term", "long_term"] = "long_term"
    top_n: int = Field(50, ge=1, le=50)
    min_ms: int = Field(30_000, ge=0)
    lastfm_user: Optional[str] = None
    gdpr_token: Optional[str] = None  # handle from a prior /api/gdpr/upload


class ApplyRequest(BaseModel):
    scan_job_id: str
    profile: str = "default"
    track_ids: list[str] = Field(default_factory=list, min_length=1)
    unlike: bool = False
    remove_from_playlists: bool = False
    confirm: str  # must be the literal "DELETE" -- the typed-key gate


class JobStarted(BaseModel):
    job_id: str

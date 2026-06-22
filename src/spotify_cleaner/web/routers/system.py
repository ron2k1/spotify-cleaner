"""Health, configuration status, and profile listing.

None of these touch Spotify, so they answer instantly and never prompt. The
UI hits ``/api/config`` first: if creds are missing it shows setup help instead
of a dead login button, echoing the exact redirect URI to register.
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from .. import oauth
from ..schemas import ConfigInfo

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config", response_model=ConfigInfo)
def config() -> ConfigInfo:
    return ConfigInfo(
        configured=oauth.credentials_present(),
        redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        ),
        # The username can come from the form, but the API key is server-only,
        # so the UI can't know if Last.fm will work until we tell it here.
        lastfm_available=bool(os.getenv("LASTFM_API_KEY")),
    )


@router.get("/profiles")
def profiles() -> list[dict]:
    return oauth.list_profiles()


@router.delete("/profiles/{profile}")
def delete_profile(profile: str) -> dict:
    cfg = oauth.load_config(profile)
    return {"removed": oauth.logout(cfg)}

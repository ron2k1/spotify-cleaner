"""Browser-driven Spotify login.

Flow: the SPA does a *full-page* navigation to ``/api/auth/login`` (not fetch,
so the browser follows the 307 to Spotify). The user approves; Spotify sends
the browser to ``/callback`` -- the one path registered with the app -- which
exchanges the code, caches the token for that profile, and 303s back to the UI.

``/callback`` is mounted at the site root (no /api prefix) because the redirect
URI must match exactly what's registered in the Spotify dashboard.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from .. import oauth
from ..schemas import AuthStatus

router = APIRouter(prefix="/api/auth", tags=["auth"])
callback_router = APIRouter(tags=["auth"])  # mounted at root for /callback


@router.get("/status", response_model=AuthStatus)
def status(profile: str = "default") -> AuthStatus:
    cfg = oauth.load_config(profile)  # raises NotConfigured -> 503 handler
    sp = oauth.client_for(cfg)
    if sp is None:
        return AuthStatus(profile=profile, connected=False)
    try:
        me = sp.me()
        return AuthStatus(
            profile=profile,
            connected=True,
            display_name=me.get("display_name") or me.get("id"),
        )
    except Exception as exc:  # noqa: BLE001 - report the type only, never a body
        return AuthStatus(profile=profile, connected=False, error=type(exc).__name__)


@router.get("/login")
def login(profile: str = "default") -> RedirectResponse:
    cfg = oauth.load_config(profile)
    return RedirectResponse(oauth.begin_login(cfg, profile), status_code=307)


@router.post("/logout")
def logout(profile: str = "default") -> dict:
    cfg = oauth.load_config(profile)
    return {"removed": oauth.logout(cfg)}


def _ui_redirect(query: str) -> RedirectResponse:
    # In dev the UI lives on the Vite origin; in prod it's same-origin ("/").
    origin = os.getenv("SPOTIFY_WEB_UI_ORIGIN", "")
    return RedirectResponse(f"{origin}/?{query}", status_code=303)


@callback_router.get("/callback")
def callback(
    code: str | None = None, state: str | None = None, error: str | None = None
) -> RedirectResponse:
    if error or not code or not state:
        return _ui_redirect("auth=error")
    profile = oauth.resolve_state(state)
    if profile is None:
        return _ui_redirect("auth=badstate")
    try:
        oauth.complete_login(oauth.load_config(profile), code)
    except Exception:  # noqa: BLE001 - never leak OAuth error details to the URL
        return _ui_redirect("auth=error")
    return _ui_redirect(f"auth=ok&profile={profile}")

"""Server-driven OAuth, built so the server can NEVER block on a prompt.

The danger with spotipy's Authorization Code flow inside a server: when no
valid token is cached, ``get_access_token()`` (which spotipy calls on every API
request) falls back to an *interactive* prompt -- it prints a URL and blocks on
``input()``. In a web process that would hang the request thread forever.

So every helper here that hands back a client first proves a valid (or
refreshable) token already exists in the cache. If it doesn't, we return
``None`` and the caller answers 401 -- we never let spotipy reach its prompt.
The browser drives consent instead: ``begin_login`` -> Spotify -> ``/callback``
-> ``complete_login`` writes the token to the per-profile cache file.
"""

from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

from ..config import SCOPES, SpotifyConfig

DEFAULT_PROFILE = "default"

# state token -> profile, set at login, popped at callback. Guards against a
# stray callback landing on the wrong profile (and basic CSRF on loopback).
_pending_states: dict[str, str] = {}
_states_lock = threading.Lock()


class NotConfigured(Exception):
    """Raised when SPOTIFY_CLIENT_ID / _SECRET are not set in the environment."""


def credentials_present() -> bool:
    return bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))


def load_config(profile: Optional[str]) -> SpotifyConfig:
    """Build a SpotifyConfig for a profile, or raise NotConfigured.

    ``SpotifyConfig.from_env`` raises SystemExit when creds are missing (great
    for the CLI, fatal for a server). Convert it to a catchable exception the
    app maps to a 503 -- so the server stays up and the UI can show setup help.
    """
    prof = None if profile in (None, "", DEFAULT_PROFILE) else profile
    try:
        return SpotifyConfig.from_env(profile=prof)
    except SystemExit:
        # The SystemExit message is the generic "Missing env vars" text (no
        # secret), but we don't forward it regardless -- a fixed code is enough.
        raise NotConfigured()


def get_oauth(cfg: SpotifyConfig, *, state: Optional[str] = None) -> SpotifyOAuth:
    return SpotifyOAuth(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        redirect_uri=cfg.redirect_uri,
        scope=SCOPES,
        cache_path=cfg.cache_path,
        open_browser=False,  # the server never opens a browser or prompts
        state=state,
        show_dialog=False,
    )


def has_token(cfg: SpotifyConfig) -> bool:
    return get_oauth(cfg).cache_handler.get_cached_token() is not None


def client_for(cfg: SpotifyConfig) -> Optional[spotipy.Spotify]:
    """An authed client IFF a valid/refreshable token is already cached.

    Returns None (never prompts) when there is no usable token, so the caller
    can answer 401 and the UI can send the user through the browser login.
    """
    auth = get_oauth(cfg)
    try:
        token = auth.validate_token(auth.cache_handler.get_cached_token())
    except SpotifyOauthError:
        return None  # cached token present but refresh failed (revoked/expired)
    if not token:
        return None
    # validate_token just refreshed-into-cache if needed, so the auth_manager
    # will read a fresh token and won't hit its interactive branch.
    return spotipy.Spotify(auth_manager=auth, requests_timeout=30, retries=5)


def begin_login(cfg: SpotifyConfig, profile: str) -> str:
    """Return the Spotify authorize URL (carries only the public Client ID)."""
    state = secrets.token_urlsafe(24)
    with _states_lock:
        _pending_states[state] = profile or DEFAULT_PROFILE
    return get_oauth(cfg, state=state).get_authorize_url()


def resolve_state(state: str) -> Optional[str]:
    with _states_lock:
        return _pending_states.pop(state, None)


def complete_login(cfg: SpotifyConfig, code: str) -> None:
    """Exchange the callback code for tokens and cache them for this profile."""
    auth = get_oauth(cfg)
    auth.get_access_token(code, as_dict=False, check_cache=False)


def logout(cfg: SpotifyConfig) -> bool:
    """Delete a profile's cached token. Returns True if a file was removed."""
    path = Path(cfg.cache_path)
    if path.exists():
        path.unlink()
        return True
    return False


def list_profiles() -> list[dict]:
    """Discover profiles from the .cache-spotify* files in the working dir.

    'default' is always present (the operator's own slot) even before login.
    Each ``.cache-spotify-<name>`` file is a separate person's saved token.
    """
    profiles: dict[str, bool] = {DEFAULT_PROFILE: False}
    for path in Path(".").glob(".cache-spotify*"):
        name = path.name
        if name == ".cache-spotify":
            profiles[DEFAULT_PROFILE] = True
        elif name.startswith(".cache-spotify-"):
            profiles[name[len(".cache-spotify-") :]] = True
    return [{"id": pid, "connected": connected} for pid, connected in profiles.items()]

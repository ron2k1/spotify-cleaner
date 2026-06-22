"""Builds an authenticated Spotipy client via the Authorization Code flow.

The access token and its refresh token are cached to disk, so you authorize
in the browser once and every later run is silent until the token is revoked.
"""

from __future__ import annotations

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .config import SCOPES, SpotifyConfig


def make_client(cfg: SpotifyConfig) -> spotipy.Spotify:
    auth = SpotifyOAuth(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        redirect_uri=cfg.redirect_uri,
        scope=SCOPES,
        cache_path=cfg.cache_path,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth, requests_timeout=30, retries=5)

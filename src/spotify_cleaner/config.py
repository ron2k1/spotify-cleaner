"""Environment + tunables. Nothing here makes a listening decision;
it only wires credentials and constants."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; real env vars still work
    pass

# Every scope the tool might need. Requesting them all up front means one
# browser consent screen instead of re-authorizing when you switch sources.
SCOPES = " ".join(
    [
        "user-library-read",  # read Liked Songs
        "user-library-modify",  # unlike tracks
        "playlist-read-private",  # read your playlists
        "playlist-modify-private",  # remove from private playlists
        "playlist-modify-public",  # remove from public playlists
        "user-top-read",  # top-tracks proxy scorer
        "user-read-recently-played",  # reserved for a future forward-polling scorer
    ]
)


@dataclass
class SpotifyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    cache_path: str

    @classmethod
    def from_env(cls) -> "SpotifyConfig":
        missing = [
            k
            for k in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")
            if not os.getenv(k)
        ]
        if missing:
            raise SystemExit(
                "Missing env vars: "
                + ", ".join(missing)
                + "\nCopy .env.example to .env and fill in your Spotify app credentials."
            )
        return cls(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
            # Spotify requires loopback redirects to use 127.0.0.1 (not "localhost").
            redirect_uri=os.getenv(
                "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
            ),
            cache_path=os.getenv("SPOTIFY_TOKEN_CACHE", ".cache-spotify"),
        )


@dataclass
class LastfmConfig:
    api_key: str
    username: str

    @classmethod
    def from_env(cls) -> "LastfmConfig":
        key = os.getenv("LASTFM_API_KEY")
        user = os.getenv("LASTFM_USERNAME")
        if not key or not user:
            raise SystemExit(
                "Last.fm source needs LASTFM_API_KEY and LASTFM_USERNAME set."
            )
        return cls(api_key=key, username=user)

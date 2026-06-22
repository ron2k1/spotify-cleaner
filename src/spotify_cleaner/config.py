"""Environment + tunables. Nothing here makes a listening decision;
it only wires credentials and constants."""

from __future__ import annotations

import os
import re
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


_PROFILE_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _profile_cache_path(profile: str) -> str:
    """Map a --profile name to its own token-cache filename.

    One operator can hold several friends' logins at once, each in its own
    cache, so they never clobber one another. The name lands inside a filename,
    so collapse anything that isn't a safe identifier char to a dash. That also
    neutralizes a traversal-looking value like "../foo" — it can never steer
    the cache file outside the project directory.
    """
    safe = _PROFILE_UNSAFE.sub("-", profile.strip()).strip("-")
    if not safe:
        raise SystemExit(
            "--profile must contain at least one letter, digit, dash, or underscore."
        )
    return f".cache-spotify-{safe}"


@dataclass
class SpotifyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    cache_path: str

    @classmethod
    def from_env(cls, profile: str | None = None) -> "SpotifyConfig":
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
        # An explicit --profile wins over SPOTIFY_TOKEN_CACHE: it's a per-person
        # choice made at the command line, so it must not be silently overridden
        # by a single cache path left in the environment.
        if profile:
            cache_path = _profile_cache_path(profile)
        else:
            cache_path = os.getenv("SPOTIFY_TOKEN_CACHE", ".cache-spotify")
        return cls(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
            # Spotify requires loopback redirects to use 127.0.0.1 (not "localhost").
            redirect_uri=os.getenv(
                "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
            ),
            cache_path=cache_path,
        )

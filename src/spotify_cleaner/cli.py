"""Command-line entry point: auth -> library -> scorer -> plan -> preview/apply."""

from __future__ import annotations

import argparse
import os
from typing import Optional

from . import cleaner
from .auth import make_client
from .config import LastfmConfig, SpotifyConfig
from .library import build_library
from .planner import plan
from .scoring.gdpr import GdprScorer
from .scoring.lastfm import LastfmScorer
from .scoring.toptracks import TopTracksScorer


def _force_utf8_output() -> None:
    # Track/artist names from Spotify's global catalog are routinely non-ASCII.
    # A legacy Windows console binds stdout to cp1252, so printing them would
    # raise UnicodeEncodeError mid-run. Reconfigure to UTF-8 (replacing the rare
    # unmappable char) so output can never crash the program.
    import sys

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # not a TextIOWrapper (e.g. redirected to a custom sink)
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # stream already detached/closed; leave it as-is


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be a positive integer (>= 1)")
    return n


def _nonneg_int(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be zero or a positive integer")
    return n


def _build_scorer(args, sp):
    if args.source == "gdpr":
        return GdprScorer(args.gdpr_dir, min_ms=args.min_ms)
    if args.source == "lastfm":
        cfg = LastfmConfig.from_env()
        return LastfmScorer(cfg.api_key, cfg.username)
    return TopTracksScorer(sp, time_range=args.time_range, top_n=args.top_n)


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="spotify-cleaner",
        description="Find and clear out your least-listened Spotify songs.",
    )
    p.add_argument(
        "--source",
        choices=["gdpr", "lastfm", "toptracks"],
        default="toptracks",
        help="where play data comes from (default: toptracks, zero setup)",
    )
    p.add_argument("--gdpr-dir", help="folder of unzipped Extended Streaming History JSON")
    p.add_argument("--min-ms", type=int, default=30_000, help="gdpr: ms to count a play")
    p.add_argument("--lastfm-user", help="Last.fm username (or set LASTFM_USERNAME)")
    p.add_argument(
        "--time-range",
        choices=["short_term", "medium_term", "long_term"],
        default="long_term",
        help="toptracks window (default: long_term)",
    )
    p.add_argument(
        "--top-n", type=_positive_int, default=50, help="toptracks: size of the 'top' set"
    )
    p.add_argument(
        "--min-plays",
        type=_nonneg_int,
        default=2,
        help="count mode: flag tracks with this many plays or fewer (default: 2)",
    )
    p.add_argument(
        "--stale-days",
        type=int,
        default=None,
        help="count mode: also flag tracks not played in this many days",
    )
    p.add_argument(
        "--grace-days",
        type=_positive_int,
        default=None,
        help="never flag tracks added within this many days (too new to judge)",
    )
    p.add_argument(
        "--all-tracks",
        action="store_true",
        help="consider all library/playlist tracks, not just Liked Songs",
    )
    p.add_argument(
        "--apply", action="store_true", help="perform changes (default: dry run only)"
    )
    p.add_argument("--unlike", action="store_true", help="when applying, remove from Liked Songs")
    p.add_argument(
        "--remove-from-playlists",
        action="store_true",
        help="when applying, remove from your owned playlists",
    )
    p.add_argument(
        "--limit", type=_positive_int, default=50, help="how many candidates to print"
    )
    p.add_argument(
        "--profile",
        help="token-cache name, e.g. a friend's name; keeps each person's login "
        "in its own .cache-spotify-<profile> file when you run for several people",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authorize URL and paste back the redirect URL instead of "
        "opening a browser; lets you authorize a friend on their own device",
    )
    return p, p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    _force_utf8_output()
    parser, args = _parse_args(argv)

    if args.source == "gdpr" and not args.gdpr_dir:
        parser.error("--source gdpr requires --gdpr-dir")
    if args.lastfm_user:
        # Direct assignment: an explicit flag must win over a stale exported
        # LASTFM_USERNAME (setdefault would let the env value silently win).
        os.environ["LASTFM_USERNAME"] = args.lastfm_user
    if args.source == "lastfm":
        # Fail fast on missing creds BEFORE the Spotify auth + full library
        # fetch, so a missing key doesn't waste an interactive browser consent.
        LastfmConfig.from_env()
    if args.apply and not (args.unlike or args.remove_from_playlists):
        parser.error("--apply needs at least one of --unlike / --remove-from-playlists")

    sp = make_client(
        SpotifyConfig.from_env(profile=args.profile),
        open_browser=not args.no_browser,
    )

    print("Reading your library (Liked Songs + owned playlists)...")
    library = build_library(sp, owned_only=True)
    print(
        f"  {len(library.liked())} liked, {len(library.playlists)} owned playlists, "
        f"{len(library.tracks)} unique tracks total."
    )

    scorer = _build_scorer(args, sp)
    universe = list(library.tracks.values()) if args.all_tracks else library.liked()
    print(f"Scoring {len(universe)} track(s) via '{scorer.name}' ({scorer.mode} mode)...")
    stats = scorer.score(universe)

    candidates = plan(
        library,
        stats,
        scorer.mode,
        liked_only=not args.all_tracks,
        min_plays=args.min_plays,
        stale_days=args.stale_days,
        grace_days=args.grace_days,
    )
    cleaner.preview(candidates, limit=args.limit)

    if args.apply and candidates:
        targets = []
        if args.remove_from_playlists:
            targets.append("remove from playlists")
        if args.unlike:
            targets.append("unlike")
        resp = input(
            f"\nType DELETE to {' + '.join(targets)} for {len(candidates)} track(s): "
        ).strip()
        cleaner.apply(
            sp,
            library,
            candidates,
            confirm=(resp == "DELETE"),
            unlike=args.unlike,
            remove_from_playlists=args.remove_from_playlists,
        )


if __name__ == "__main__":
    main()

"""Local web app for spotify-cleaner.

A thin FastAPI layer over the exact same core (``library`` / ``scoring`` /
``planner`` / ``cleaner``) the CLI uses. It adds nothing to the cleaning logic;
it only drives OAuth from the browser, streams progress over SSE, and serves a
single-page UI. Launch it with ``python -m spotify_cleaner.web``.

The Client Secret never leaves this process: the browser only ever sees the
public authorize URL and the rows the API chooses to return.
"""

# Contributing

Thanks for taking a look. This is a small, focused tool; the bar for a change
is that it stays simple, honest about what it can and can't know, and safe
around anything destructive.

## Project shape

```
src/spotify_cleaner/
  auth.py, library.py    Spotify I/O (OAuth, reading Liked Songs + owned playlists)
  scoring/               the pluggable sources — toptracks / gdpr / lastfm
  planner.py             pure candidacy logic (which tracks are "least listened"); fully tested
  cleaner.py             the guarded removals (dry-run by default, typed-DELETE gate)
  backup.py              writes a restore manifest + audit log before any delete
  cli.py                 argparse wiring
  web/                   optional FastAPI app + SSE jobs; serves the built SPA
frontend/                Vite + React + TS + Tailwind SPA (built into web/static/)
tests/                   logic + web-contract tests; no live Spotify account needed
```

The one invariant worth internalising: **Spotify's API does not expose personal
play counts.** Every source is a way to approximate "least listened" without
them, so each `Scorer` is honest about its confidence (`high` / `medium` /
`low`) rather than pretending to a precision it doesn't have. A new source is
just a class with `name`, `mode` (`rank` or `count`), and
`score(tracks, progress=None) -> dict[track_id, PlayStats]`.

## Backend setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev,web]"       # dev = pytest/httpx, web = fastapi/uvicorn/...
pytest -q                         # no account needed
```

`pytest` covers the planner, the web contracts (health, the configured/
unconfigured split, the typed-DELETE gate, GDPR upload rules, CSV-export
escaping), and scorer behaviour with fake Spotify clients. Anything that needs
a real account is verified manually and stays out of the suite.

## Frontend setup

```bash
cd frontend
npm ci
npm run dev          # Vite on :5173, proxies /api to the server on :8888
npm run build        # type-checks (tsc --noEmit) then bundles into web/static/
```

For a full local run, build the SPA, then launch the server from the repo root:

```bash
python -m spotify_cleaner.web      # or, after install: spotify-cleaner-web
```

The server serves the built SPA and handles the OAuth callback on the **same
origin** (`127.0.0.1:8888`), which is why the token never reaches the browser
and there's no CORS to configure. If the SPA isn't built yet, `/` shows a short
how-to instead of a blank 404 — the JSON API is still fully usable.

## Conventions

- **Match the surrounding style.** Formatting is hand-maintained and consistent;
  there's intentionally no enforced Prettier/ESLint config, so mirror the file
  you're editing (2-space indent, double quotes, trailing commas in TS).
- **Never leak secrets or raw errors.** The server returns machine-readable
  detail codes (`not_connected`, `lastfm_not_configured`), never exception
  messages, response bodies, or tokens. Logs follow the same rule.
- **Treat destructive paths with suspicion.** Removals are dry-run by default,
  gated behind a typed `DELETE`, only touch playlists you own, and write a
  backup manifest first. Keep new code on that side of the line.
- **Keep `types.ts` in sync** with `web/schemas.py` and `web/serialize.py` —
  the contract is hand-mirrored (no codegen) because the surface is small.

## CI

Every push and PR runs two jobs (`.github/workflows/ci.yml`):

- **pytest** across Python 3.10–3.13,
- **frontend** — `npm ci` then `npm run build`, which type-checks and bundles.

Please make sure both are green locally before opening a PR. Keep commits atomic
(one logical change each) with a short imperative subject and a body that says
*why*.

## License

By contributing you agree your work is licensed under the project's
[MIT License](LICENSE).

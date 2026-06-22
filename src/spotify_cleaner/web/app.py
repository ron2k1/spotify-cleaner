"""FastAPI application factory.

Route order matters: the API + ``/callback`` routes are registered first, then
the built SPA is mounted at ``/`` as a catch-all. Starlette matches in
registration order, so ``/api/*`` always wins over the static mount.

If the SPA hasn't been built yet, ``/`` serves a short how-to instead of a
blank 404 -- the app is still fully usable headlessly via the JSON API.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .oauth import NotConfigured
from .routers import apply, auth, gdpr, scan, system

_STATIC_DIR = Path(__file__).parent / "static"

_NOT_BUILT_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>spotify-cleaner</title><style>body{font:16px/1.6 system-ui;max-width:42rem;
margin:4rem auto;padding:0 1rem;color:#e7e7ea;background:#121214}code{background:#1f1f24;
padding:.15rem .4rem;border-radius:.3rem}a{color:#1db954}</style></head><body>
<h1>spotify-cleaner</h1><p>The API is running, but the web UI hasn't been built yet.</p>
<p>Build it once:</p><pre><code>cd frontend
npm install
npm run build</code></pre>
<p>...then reload. For UI development run <code>npm run dev</code> and open
<a href="http://127.0.0.1:5173/">http://127.0.0.1:5173/</a> instead.</p>
<p>API docs: <a href="/api/docs">/api/docs</a></p></body></html>"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="spotify-cleaner",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # Dev only: when the UI is served from the Vite origin, allow it through.
    ui_origin = os.getenv("SPOTIFY_WEB_UI_ORIGIN", "")
    if ui_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[ui_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(NotConfigured)
    async def _not_configured(request: Request, exc: NotConfigured) -> JSONResponse:
        # Server stays up; the UI reads this and shows .env setup help.
        return JSONResponse(
            status_code=503, content={"detail": "spotify_app_not_configured"}
        )

    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(auth.callback_router)
    app.include_router(scan.router)
    app.include_router(apply.router)
    app.include_router(gdpr.router)

    if (_STATIC_DIR / "index.html").exists():
        # html=True makes "/" serve index.html and 404s fall back to it (SPA).
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="spa")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def _root() -> str:
            return _NOT_BUILT_HTML

    return app

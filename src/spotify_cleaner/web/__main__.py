"""``python -m spotify_cleaner.web`` -- run the local web app.

Defaults to 127.0.0.1:8888 because that's the host:port of the redirect URI the
README tells you to register (``http://127.0.0.1:8888/callback``). Serving the
UI and handling the OAuth callback on the same origin is what lets login work
with no CORS and no token ever reaching the browser.
"""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from .app import create_app


def main() -> None:
    host = os.getenv("SPOTIFY_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("SPOTIFY_WEB_PORT", "8888"))

    if os.getenv("SPOTIFY_WEB_OPEN", "1") != "0":
        url = f"http://{host}:{port}/"
        # Fire after a short delay so the server is listening when it opens.
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

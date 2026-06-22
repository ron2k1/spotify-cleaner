"""Web-layer tests that never touch a real Spotify account.

They pin the contracts a UI relies on: health, the configured/unconfigured
split, the 503-not-503 behaviour when creds are missing, the typed-DELETE gate
on apply, and the GDPR upload's accept/reject rules. Anything needing live
Spotify auth is out of scope here (it's covered manually against a real app).
"""

from __future__ import annotations

import json

import pytest

# The web stack is an optional extra; skip these tests entirely when it isn't
# installed (e.g. a core-only `pip install -e ".[dev]"`) instead of failing at
# collection. CI installs ".[dev,web]", so they always run there.
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from spotify_cleaner.web.app import create_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def no_creds(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_reports_unconfigured(client, no_creds):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["redirect_uri"].endswith("/callback")


def test_status_unconfigured_is_503(client, no_creds):
    r = client.get("/api/auth/status", params={"profile": "default"})
    assert r.status_code == 503
    assert r.json()["detail"] == "spotify_app_not_configured"


def test_scan_unconfigured_is_503(client, no_creds):
    r = client.post("/api/scan", json={"source": "toptracks", "profile": "default"})
    assert r.status_code == 503


def test_profiles_always_lists_default(client):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    assert "default" in [p["id"] for p in r.json()]


def test_apply_requires_typed_delete(client):
    r = client.post(
        "/api/apply",
        json={
            "scan_job_id": "x",
            "track_ids": ["a"],
            "unlike": True,
            "confirm": "nope",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "confirmation_required"


def test_apply_requires_an_action(client):
    r = client.post(
        "/api/apply",
        json={"scan_job_id": "x", "track_ids": ["a"], "confirm": "DELETE"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "no_action_selected"


def test_apply_rejects_unknown_scan(client):
    r = client.post(
        "/api/apply",
        json={
            "scan_job_id": "missing",
            "track_ids": ["a"],
            "unlike": True,
            "confirm": "DELETE",
        },
    )
    assert r.status_code == 409


def test_apply_validation_rejects_empty_selection(client):
    # track_ids has min_length=1, so an empty list is a 422 before any logic.
    r = client.post(
        "/api/apply",
        json={"scan_job_id": "x", "track_ids": [], "unlike": True, "confirm": "DELETE"},
    )
    assert r.status_code == 422


def test_csv_export_unknown_job_is_404(client):
    r = client.get("/api/scan/deadbeef/export.csv")
    assert r.status_code == 404
    assert r.json()["detail"] == "job_not_found"


def test_csv_export_defangs_formula_injection(client):
    """A track named like a spreadsheet formula must download as literal text."""
    from spotify_cleaner.web.jobs import manager
    from spotify_cleaner.web.routers.scan import _csv_safe

    # Unit: risky leading chars get a single-quote guard; safe values pass through.
    assert _csv_safe('=HYPERLINK("x")') == "'=HYPERLINK(\"x\")"
    assert _csv_safe("+1") == "'+1"
    assert _csv_safe("@SUM(1)") == "'@SUM(1)"
    assert _csv_safe("Normal Song") == "Normal Song"
    assert _csv_safe(None) == ""
    assert _csv_safe(3) == "3"

    # Integration: the same guard reaches the actual downloaded bytes.
    job = manager.create("scan")
    job.result = {
        "rows": [
            {
                "name": "=2+5",
                "artist_label": "@SUM(1)",
                "reason": "never played (in export)",
                "play_count": 0,
                "last_played": None,
                "confidence": "high",
                "is_liked": True,
                "playlist_count": 0,
                "added_at": None,
                "uri": "spotify:track:abc",
            }
        ],
        "source": "gdpr",
        "mode": "count",
    }
    job.emit("done", count=1)  # flips status to "done"

    r = client.get(f"/api/scan/{job.id}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert body.splitlines()[0].startswith("name,artist_label,reason")
    assert "'=2+5" in body and "'@SUM(1)" in body


def test_gdpr_rejects_non_json(client):
    r = client.post(
        "/api/gdpr/upload",
        files={"files": ("note.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "no_streaming_history_json"


def test_gdpr_accepts_streaming_json(client):
    payload = json.dumps(
        [
            {
                "ts": "2020-01-01T00:00:00Z",
                "ms_played": 40_000,
                "spotify_track_uri": "spotify:track:abc",
                "master_metadata_track_name": "Song",
                "master_metadata_album_artist_name": "Artist",
            }
        ]
    ).encode()
    r = client.post(
        "/api/gdpr/upload",
        files={"files": ("Streaming_History_Audio_2020_1.json", payload, "application/json")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["file_count"] == 1
    assert body["gdpr_token"]

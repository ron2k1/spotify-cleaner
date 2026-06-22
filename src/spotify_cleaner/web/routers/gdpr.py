"""GDPR export upload.

A non-technical friend just drops the .zip Spotify emailed them (or the loose
``Streaming_History_Audio_*.json`` files). We extract on the server, flatten
everything to one temp dir by *basename only* -- which both defeats zip-slip
(we never trust an embedded path) and satisfies ``GdprScorer``'s non-recursive
``*.json`` glob even when the export nests the files in a subfolder.

The temp dir is referenced later by an opaque token in the scan request.
"""

from __future__ import annotations

import io
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api", tags=["gdpr"])

# token -> extracted directory. Lives for the process; a local app's lifetime.
_uploads: dict[str, Path] = {}

_MAX_BYTES = 200 * 1024 * 1024  # a sane ceiling; real exports are far smaller


def resolve_gdpr(token: str | None) -> Path:
    """Return the dir for a prior upload token, or 400 if it's gone/unknown."""
    if not token or token not in _uploads or not _uploads[token].exists():
        raise HTTPException(status_code=400, detail="gdpr_upload_missing")
    return _uploads[token]


def _extract_zip(data: bytes, dest: Path) -> int:
    written = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            base = Path(info.filename).name  # drop any directory component
            if not base.lower().endswith(".json"):
                continue
            target = dest / base
            # Belt-and-braces: confirm the flat target really sits inside dest.
            if dest.resolve() not in target.resolve().parents:
                continue
            with zf.open(info) as src:
                target.write_bytes(src.read())
            written += 1
    return written


@router.post("/gdpr/upload")
async def upload_gdpr(files: list[UploadFile] = File(...)) -> dict:
    dest = Path(tempfile.mkdtemp(prefix="spotcleaner-gdpr-"))
    json_count = 0
    for uf in files:
        name = Path(uf.filename or "upload").name
        data = await uf.read()
        if len(data) > _MAX_BYTES:
            raise HTTPException(status_code=413, detail="file_too_large")
        lowered = name.lower()
        if lowered.endswith(".zip"):
            json_count += _extract_zip(data, dest)
        elif lowered.endswith(".json"):
            (dest / name).write_bytes(data)
            json_count += 1
    if json_count == 0:
        raise HTTPException(status_code=400, detail="no_streaming_history_json")
    token = uuid.uuid4().hex
    _uploads[token] = dest
    return {"gdpr_token": token, "file_count": json_count}

"""GET /api/v1/exports/{filename} (api-contracts.md `download_url` target
from the export job status response). Serves the flat file
`oracle_csv.get_export_path()`/`excel_builder` already wrote under
BASE_EXPORT_DIR — this endpoint only needs to resolve `filename` back to a
path safely (CWE-22) since it comes straight from the URL.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.agents.exporter.oracle_csv import BASE_EXPORT_DIR
from app.agents.voice.schemas import OperatorClaims
from app.api.deps import get_current_operator

router = APIRouter(prefix="/exports", tags=["exports"])

_MEDIA_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/{filename}")
async def download_export(
    filename: str,
    _operator: OperatorClaims = Depends(get_current_operator),
) -> FileResponse:
    # Path(filename) alone would let ".." components escape BASE_EXPORT_DIR
    # once resolved — reject any filename that isn't a single bare path
    # segment before ever touching the filesystem (CWE-22).
    if filename != Path(filename).name:
        raise HTTPException(status_code=400, detail={"error": "INVALID_FILENAME"})

    candidate = (BASE_EXPORT_DIR / filename).resolve()
    if not candidate.is_relative_to(BASE_EXPORT_DIR) or not candidate.is_file():
        raise HTTPException(status_code=404, detail={"error": "EXPORT_NOT_FOUND"})

    media_type = _MEDIA_TYPES.get(candidate.suffix, "application/octet-stream")
    return FileResponse(candidate, media_type=media_type, filename=candidate.name)

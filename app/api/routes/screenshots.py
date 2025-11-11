from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Response


router = APIRouter(prefix="/api", tags=["screenshots"])


@router.get("/screenshot/{filename}")
def get_screenshot(filename: str):
    file_path = Path("data/screenshots") / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    content = file_path.read_bytes()
    headers = {"Cache-Control": "public, max-age=86400"}
    return Response(content=content, media_type="image/png", headers=headers)


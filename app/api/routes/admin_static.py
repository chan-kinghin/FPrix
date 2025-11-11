from __future__ import annotations

from pathlib import Path
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.security import verify_admin


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin)])

BASE = Path("admin")


def _serve_file(fp: Path) -> Response:
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    mime, _ = mimetypes.guess_type(str(fp))
    return Response(content=fp.read_bytes(), media_type=mime or "text/plain")


@router.get("/")
def admin_index():
    return _serve_file(BASE / "index.html")


@router.get("/{path:path}")
def admin_files(path: str):
    p = BASE / path
    if str(path).endswith("/"):
        p = p / "index.html"
    return _serve_file(p)


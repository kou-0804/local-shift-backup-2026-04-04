"""P4c routes: confirm a roster + list/download confirmed-month archives.

- POST /rosters/{rid}/confirm  -> admin only (flips status, writes archive)
- GET  /archives               -> admin|editor|viewer (no draft leakage)
- GET  /archives/{id}/excel    -> admin|editor|viewer (download xlsx bytes)
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response

from webapp.api.db import get_db
from webapp.api.auth.deps import require_role
from webapp.api.archive import service

router = APIRouter(tags=["archives"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VIEWER_ROLES = require_role("admin", "editor", "viewer")


@router.post("/rosters/{rid}/confirm")
def confirm_roster(rid: int, conn=Depends(get_db),
                   user: dict = Depends(require_role("admin"))):
    hdr = conn.execute("SELECT id FROM rosters WHERE id=?", (rid,)).fetchone()
    if hdr is None:
        raise HTTPException(status_code=404, detail="roster not found")
    return service.confirm_roster(conn, rid, user_id=user.get("login_id", ""))


@router.get("/archives", dependencies=[Depends(VIEWER_ROLES)])
def list_archives(conn=Depends(get_db)):
    return service.list_archives(conn)


@router.get("/archives/{archive_id}/excel", dependencies=[Depends(VIEWER_ROLES)])
def download_archive(archive_id: int, conn=Depends(get_db)):
    payload = service.get_archive_bytes(conn, archive_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="archive not found")
    xlsx, year, month = payload
    filename = f"勤務表_{year}年{month}月.xlsx"
    # RFC 5987: non-ASCII filenames must be percent-encoded (HTTP headers latin-1).
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(content=xlsx, media_type=XLSX_MIME,
                    headers={"Content-Disposition": disposition})

"""P4a: production same-origin serving.

A single uvicorn process serves BOTH the built SPA (``frontend/dist``) and the
JSON API. ``mount_spa`` is called LAST in ``webapp/api/main.py`` so Starlette
matches every explicit API route before the catch-all SPA fallback.

Contract:
- ``GET /``            -> ``index.html`` (the SPA shell)
- ``GET /assets/*``   -> hashed JS/CSS via ``StaticFiles`` (correct MIME types)
- ``GET /favicon.ico`` (and any real file in ``dist``) -> that file
- ``GET /<client route>`` (not under the API namespace) -> ``index.html``
- ``GET /<api prefix>/...`` that no explicit route handled -> JSON 404 (NOT the
  SPA shell), so the client can still detect a missing roster/job/etc.

Dev mode keeps the Vite proxy and serves the SPA from Vite; in that case
``SHIFT_FRONTEND_DIST`` is unset and ``mount_spa`` is a no-op.
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# First path segment of every JSON API namespace. A request whose first segment
# is one of these must NEVER be answered with index.html — if no explicit route
# matched it, it is a genuine API 404 and must surface as JSON.
API_PREFIXES = ("health", "auth", "jobs", "rosters", "masters", "master-sets", "archives")


def mount_spa(app: FastAPI, dist_dir) -> bool:
    """Mount the built SPA + an API-aware catch-all fallback.

    Returns True when mounted, False in dev mode (no dist dir). Idempotent-safe
    to skip when ``dist_dir`` is falsy or missing so API-only test runs and the
    Vite dev server are unaffected.
    """
    if not dist_dir or not os.path.isdir(dist_dir):
        return False

    dist_dir = os.path.abspath(dist_dir)
    index_path = os.path.join(dist_dir, "index.html")
    assets_dir = os.path.join(dist_dir, "assets")
    if os.path.isdir(assets_dir):
        # StaticFiles sets correct Content-Type (e.g. text/javascript for .js).
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        first = full_path.split("/", 1)[0]
        # Genuine API 404 — do not swallow it with the SPA shell.
        if full_path and first in API_PREFIXES:
            raise HTTPException(status_code=404, detail="not found")
        # Serve a real root-level file (favicon.ico, vite.svg, robots.txt, ...)
        # when present; guard against path traversal outside dist_dir.
        if full_path:
            candidate = os.path.abspath(os.path.join(dist_dir, full_path))
            if (
                os.path.isfile(candidate)
                and os.path.commonpath([candidate, dist_dir]) == dist_dir
            ):
                return FileResponse(candidate)
        # Any other non-API GET is a client-side route -> the SPA shell.
        return FileResponse(index_path)

    return True

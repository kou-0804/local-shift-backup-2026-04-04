"""FastAPI router for master management: per-master CRUD + clone + (Task 6)
safety-check + (Task 7) 予定申請 import. Included from ``webapp/api/main.py``.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from webapp.api.db import get_db
from webapp.api.auth.deps import current_user
from webapp.api.requests_import import preview_requests, store_requests, requests_status
from . import crud
from .safety import LOAD_BEARING_IDS, SafetyError, assert_load_bearing_ids
from .validation import ValidationError


def masters_guard(request: Request, user: dict = Depends(current_user)) -> dict:
    """Role gate for the whole master namespace (P4b): reads (GET) need
    admin|editor; writes (POST/PUT/DELETE, incl. clone + 予定申請 import) need
    admin. One method-aware guard avoids per-route drift."""
    write = request.method in ("POST", "PUT", "DELETE")
    allowed = {"admin"} if write else {"admin", "editor"}
    if user["role"] not in allowed:
        raise HTTPException(status_code=403, detail="insufficient role")
    return user


router = APIRouter(prefix="/masters", tags=["masters"],
                   dependencies=[Depends(masters_guard)])
# Separate (unprefixed) router so the collection lives at /master-sets, not
# /masters/...; included alongside `router` in webapp/api/main.py.
sets_router = APIRouter(tags=["masters"], dependencies=[Depends(masters_guard)])


@sets_router.get("/master-sets")
def list_master_sets(conn=Depends(get_db)):
    """[{master_set_id, name, created_at, parent_set_id}] for every master_set."""
    return crud.list_master_sets(conn)


def _name_to_id(conn, master_set_id: Optional[int]) -> dict:
    if master_set_id is None:
        return {}
    return {r["name"]: r["tech_id"] for r in conn.execute(
        "SELECT name,tech_id FROM ms_staff WHERE master_set_id=?", (master_set_id,))}


# --- 予定申請 import (import-only, NOT CRUD) --------------------------------
# The CSV is POSTed as the raw request body (text/csv or octet-stream). Reading
# raw bytes keeps the stored BLOB byte-exact and avoids a python-multipart dep.

@router.post("/requests/preview")
async def requests_preview(request: Request,
                           master_set_id: Optional[int] = Query(default=None),
                           conn=Depends(get_db)):
    raw = await request.body()
    return preview_requests(raw, _name_to_id(conn, master_set_id))


@router.get("/requests/{year}/{month}")
def requests_status_route(year: int, month: int, conn=Depends(get_db)):
    """Read-only: latest 予定申請 import status for the month (admin|editor).
    Lets the 勤務表作成 page show whether the CSV for the target month is loaded."""
    return requests_status(conn, year, month)


@router.post("/requests/{year}/{month}", status_code=201)
async def requests_commit(request: Request, year: int, month: int,
                          master_set_id: Optional[int] = Query(default=None),
                          imported_by: str = Query(default=""),
                          source_filename: str = Query(default="予定申請.csv"),
                          conn=Depends(get_db)):
    raw = await request.body()
    imp_id = store_requests(conn, year=year, month=month, raw=raw,
                            source_filename=source_filename,
                            imported_by=imported_by,
                            name_to_id=_name_to_id(conn, master_set_id))
    return {"import_id": imp_id}


def _422(exc: ValidationError):
    raise HTTPException(status_code=422, detail={"field": exc.field, "message": exc.message})


# --- clone (edit-on-a-copy so the seed set stays pristine) ------------------

@router.post("/{master_set_id}/clone", status_code=201)
def clone(master_set_id: int, payload: Dict[str, Any] = None, conn=Depends(get_db)):
    payload = payload or {}
    try:
        new_id = crud.clone_master_set(
            conn, master_set_id, created_by=payload.get("created_by", ""),
            name=payload.get("name"))
    except KeyError:
        raise HTTPException(status_code=404, detail="master_set not found")
    return {"master_set_id": new_id}


# --- staff -----------------------------------------------------------------

@router.get("/{master_set_id}/staff")
def list_staff(master_set_id: int, conn=Depends(get_db)):
    return crud.list_staff(conn, master_set_id)


@router.post("/{master_set_id}/staff", status_code=201)
def create_staff(master_set_id: int, payload: Dict[str, Any], conn=Depends(get_db)):
    try:
        return crud.create_staff(conn, master_set_id, payload)
    except ValidationError as exc:
        _422(exc)


@router.put("/{master_set_id}/staff/{tech_id}")
def update_staff(master_set_id: int, tech_id: str, payload: Dict[str, Any],
                 conn=Depends(get_db)):
    try:
        return crud.update_staff(conn, master_set_id, tech_id, payload)
    except ValidationError as exc:
        _422(exc)
    except KeyError:
        raise HTTPException(status_code=404, detail="staff not found")


@router.delete("/{master_set_id}/staff/{tech_id}")
def delete_staff(master_set_id: int, tech_id: str, conn=Depends(get_db)):
    return crud.delete_staff(conn, master_set_id, tech_id)


# --- skill -----------------------------------------------------------------

@router.get("/{master_set_id}/skill")
def list_skill(master_set_id: int, conn=Depends(get_db)):
    return crud.list_skill(conn, master_set_id)


@router.put("/{master_set_id}/skill/{tech_id}")
def update_skill(master_set_id: int, tech_id: str, cells: Dict[str, Any],
                 conn=Depends(get_db)):
    try:
        return crud.update_skill(conn, master_set_id, tech_id, cells)
    except ValidationError as exc:
        _422(exc)


# --- holiday_targets -------------------------------------------------------

@router.get("/{master_set_id}/holiday_targets")
def list_holiday(master_set_id: int, conn=Depends(get_db)):
    return crud.list_holiday_targets(conn, master_set_id)


@router.post("/{master_set_id}/holiday_targets", status_code=201)
def upsert_holiday(master_set_id: int, payload: Dict[str, Any], conn=Depends(get_db)):
    try:
        return crud.upsert_holiday_target(
            conn, master_set_id, payload.get("year_month"), payload.get("holiday_count"))
    except ValidationError as exc:
        _422(exc)


@router.delete("/{master_set_id}/holiday_targets/{key}")
def delete_holiday(master_set_id: int, key: str, conn=Depends(get_db)):
    return crud.delete_holiday_target(conn, master_set_id, key)


# --- safety gate (load-bearing IDs) ----------------------------------------

@router.get("/{master_set_id}/safety-check")
def safety_check(master_set_id: int, conn=Depends(get_db)):
    """Verify the §3.5 hardcoded staff IDs exist. {ok, missing}."""
    try:
        assert_load_bearing_ids(conn, master_set_id)
        return {"ok": True, "missing": [], "load_bearing_ids": LOAD_BEARING_IDS}
    except SafetyError as exc:
        present = {r["tech_id"] for r in conn.execute(
            "SELECT tech_id FROM ms_staff WHERE master_set_id=?", (master_set_id,))}
        missing = [t for t in LOAD_BEARING_IDS if t not in present]
        return {"ok": False, "missing": missing, "message": str(exc),
                "load_bearing_ids": LOAD_BEARING_IDS}


# --- write endpoints (P3a-2): replace-style PUTs ---------------------------
# Clone-before-edit applies (POST /masters/{id}/clone). Each replaces the whole
# master atomically; ValidationError -> 422 {field, message}, set untouched.

@router.put("/{master_set_id}/location_set")
def put_location_set(master_set_id: int, payload: Dict[str, Any],
                     conn=Depends(get_db)):
    """ATOMIC: body {locations:[...], power_balance:[...]} replaces BOTH tables."""
    try:
        return crud.replace_location_set(
            conn, master_set_id, payload.get("locations") or [],
            payload.get("power_balance") or [])
    except ValidationError as exc:
        _422(exc)


@router.put("/{master_set_id}/special_rules")
def put_special_rules(master_set_id: int, rows: List[Dict[str, Any]],
                      conn=Depends(get_db)):
    try:
        return crud.replace_special_rules(conn, master_set_id, rows)
    except ValidationError as exc:
        _422(exc)


@router.put("/{master_set_id}/training")
def put_training(master_set_id: int, rows: List[Dict[str, Any]],
                 conn=Depends(get_db)):
    try:
        return crud.replace_training(conn, master_set_id, rows)
    except ValidationError as exc:
        _422(exc)


@router.put("/{master_set_id}/night_quota")
def put_night_quota(master_set_id: int, rows: List[Dict[str, Any]],
                    year_month: str = Query(...), conn=Depends(get_db)):
    try:
        return crud.replace_night_quota(conn, master_set_id, year_month, rows)
    except ValidationError as exc:
        _422(exc)


@router.put("/{master_set_id}/night_overrides")
def put_night_overrides(master_set_id: int, rows: List[Dict[str, Any]],
                        conn=Depends(get_db)):
    try:
        return crud.replace_night_overrides(conn, master_set_id, rows)
    except ValidationError as exc:
        _422(exc)


# --- read-only list for the remaining masters ------------------------------

@router.get("/{master_set_id}/{master}")
def list_generic(master_set_id: int, master: str, conn=Depends(get_db)):
    try:
        return crud.list_generic(conn, master_set_id, master)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown master '{master}'")

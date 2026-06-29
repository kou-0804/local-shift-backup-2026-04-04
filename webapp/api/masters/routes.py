"""FastAPI router for master management: per-master CRUD + clone + (Task 6)
safety-check + (Task 7) 予定申請 import. Included from ``webapp/api/main.py``.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from webapp.api.db import get_db
from . import crud
from .safety import LOAD_BEARING_IDS, SafetyError, assert_load_bearing_ids
from .validation import ValidationError

router = APIRouter(prefix="/masters", tags=["masters"])


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


# --- read-only list for the remaining masters ------------------------------

@router.get("/{master_set_id}/{master}")
def list_generic(master_set_id: int, master: str, conn=Depends(get_db)):
    try:
        return crud.list_generic(conn, master_set_id, master)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown master '{master}'")

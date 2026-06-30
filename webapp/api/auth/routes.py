"""/auth router: login / logout / me + admin-only user management.

Login is JSON (``{login_id, password}``) — NOT multipart — so no python-multipart
dependency is needed. On success an HMAC token is set as an httpOnly, SameSite=
Strict ``session`` cookie (Bearer fallback for CLI/tests).
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from webapp.api.config import settings
from webapp.api.db import get_db
from webapp.api.auth import service
from webapp.api.auth.deps import current_user, require_role
from webapp.api.auth.tokens import resolve_secret, sign_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login_id: str
    password: str


def _public_fields(user: dict) -> dict:
    return {"uid": user["id"], "login_id": user["login_id"],
            "role": user["role"], "name": user["name"]}


@router.post("/login")
def login(req: LoginRequest, response: Response, conn=Depends(get_db)):
    user = service.authenticate(conn, req.login_id, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    ttl = settings.token_ttl_seconds
    token = sign_token({"uid": user["id"], "role": user["role"]}, resolve_secret(), ttl)
    # SameSite=Strict + httpOnly. Secure is omitted because v1 is plain-HTTP LAN
    # (set Secure once IT provides TLS — see deploy/README §Decisions).
    response.set_cookie("session", token, max_age=ttl, httponly=True,
                        samesite="strict", path="/")
    return _public_fields(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session", path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"uid": user["id"], "login_id": user["login_id"],
            "role": user["role"], "name": user["name"]}


# --- admin-only user management --------------------------------------------

@router.get("/users", dependencies=[Depends(require_role("admin"))])
def list_users(conn=Depends(get_db)):
    return service.list_users(conn)


@router.post("/users", status_code=201, dependencies=[Depends(require_role("admin"))])
def create_user(payload: Dict[str, Any], conn=Depends(get_db)):
    try:
        uid = service.create_user(
            conn, login_id=payload.get("login_id", ""),
            password=payload.get("password", ""),
            role=payload.get("role", ""), name=payload.get("name", ""))
    except service.DuplicateUser as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"id": uid}


@router.put("/users/{uid}", dependencies=[Depends(require_role("admin"))])
def update_user(uid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    if service.get_user(conn, uid) is None:
        raise HTTPException(status_code=404, detail="user not found")
    if "password" in payload:
        try:
            service.set_password(conn, uid, payload["password"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if "disabled" in payload:
        service.set_disabled(conn, uid, bool(payload["disabled"]))
    return service.get_user(conn, uid)

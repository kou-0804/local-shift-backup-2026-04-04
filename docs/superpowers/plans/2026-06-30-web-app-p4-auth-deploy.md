# Web App P4 — Production Serving + Auth + Confirm/Archive + Windows Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit with the exact message given. Backend tests use pytest + Starlette `TestClient`; the login UI uses Vitest + @testing-library/react. **Auth is stdlib-only — no new Python dependency may be added for hashing or token signing.**

**Date:** 2026-06-30
**Depends on:**
- `docs/superpowers/specs/2026-06-29-web-app-shift-scheduler-design.md` — §10 (auth/confirm/archive), §13 (deployment + IT checklist), §5 (`users`/`archives` data model), §12 (release order).
- The shipped backend: `webapp/api/main.py` (FastAPI app + roster/job endpoints), `webapp/api/db.py` (SQLite at `webapp_data/shift.db`, additive `init_*_db` pattern), `webapp/api/jobs.py`, `webapp/api/rosters.py`, `webapp/api/masters/` (CRUD + clone + safety + 予定申請 import), `webapp/api/config.py`.
- The shipped frontend: `frontend/` (Vite + React 18 + TS), same-origin API client `frontend/src/api/http.ts` (`BASE = import.meta.env.VITE_API_BASE ?? ''`), query-param routing in `frontend/src/App.tsx`.

**User intent (verbatim, do not dilute):** 「コスト度外視...最高水準で...本番はwindows」 — cost is no object, build to the highest standard, **production runs on Windows**. For this phase that means: the PRIMARY production model is a **single Python process** that serves BOTH the built SPA and the API (dev==prod, no proxy/CORS in prod), launched from a `.bat` and runnable as a Windows service; Docker is OPTIONAL. Auth uses **stdlib only** (`hashlib.pbkdf2_hmac` + `hmac`) so the hospital IT install has the fewest moving parts. Every failure is explicit (no silent auth bypass, no silent archive corruption). Windows file-path + newline + encoding handling is pinned everywhere.

---

## Phase-numbering note

The parent task names this phase **P4 = production-serving + auth + confirm/archive + Windows deployment**. The design spec §12 happens to label the *auth/confirm/archive/backup* bundle "P5" and the *heatmap/dashboard/partial-lock* bundle "P4". Those are independent tracks; **this plan owns the auth/serving/deploy track and uses the P4a–P4d labels from the parent task throughout.** Partial-lock re-solve already shipped (`POST /rosters/{rid}/resolve` in `main.py`); heatmap/dashboard is out of scope here.

---

## Goal

Take the working single-machine web app to a **deployable, multi-user, Windows-hosted v1**:

1. **P4a — Production same-origin serving.** FastAPI serves the built `frontend/dist` as static files with an SPA fallback (any non-API GET → `index.html`), while keeping `/health`, `/jobs`, `/rosters`, `/masters`, `/master-sets` as JSON APIs. This makes dev == prod (the Vite proxy is a dev-only convenience) and is the Windows single-process model. `VITE_API_BASE` stays empty (same origin).
2. **P4b — Auth (local accounts + roles).** A `users` table; `hashlib.pbkdf2_hmac` password hashing with a per-user salt; a stdlib-HMAC-signed session token delivered as an httpOnly cookie (with `Authorization: Bearer` fallback for tests/CLI); a FastAPI dependency enforcing roles (`admin` / `editor` / `viewer`); a first-run admin bootstrap. Existing endpoints are role-gated. A small React login screen attaches the session and hides controls by role.
3. **P4c — Confirm-lock + monthly archive + backup.** Roster status `draft → confirmed` (admin only); on confirm, render the Direction-A Excel bytes and store them in an `archives` table with a SHA-256 checksum + ISO timestamp; viewers list/download only confirmed/archived months and never see drafts; a backup script (copy the SQLite DB + archive bytes to a target dir) as a Windows `.bat` plus a tested Python fallback.
4. **P4d — Windows deployment packaging.** A `deploy/` folder: a frontend build script, a Windows `start.bat` (venv + pip + LAN-bound uvicorn), an optional NSSM service note, a pinned `requirements.txt` (no new heavy deps; `python-multipart` intentionally absent), a `deploy/README.md` covering install location / fixed host:port / Windows Firewall (LAN-only) / backup medium / the spec §13 IT-coordination checklist, and a note that Docker Compose is an optional alternative.

**Acceptance for the phase:** with `npm run build` done and `SHIFT_FRONTEND_DIST` pointed at `frontend/dist`, a single `uvicorn webapp.api.main:app` process (a) serves the SPA at `/` and the JSON API under the API namespace, (b) requires login, (c) gates generate/edit/confirm/user-mgmt by role, (d) lets an admin confirm a month into an immutable, checksummed archive that a viewer can download but cannot edit, and (e) starts on Windows from `deploy\start.bat`. Determinism of the solver is untouched (this phase adds no code on the solve path).

**Non-goals (P4):** AD/SSO (v1 = local accounts; see Decisions §1–2); HTTPS/TLS termination (LAN-internal HTTP for v1; reverse-proxy TLS is a Decision); heatmap/dashboard; any change to `run_schedule`, the solver, the 8 hardcoded-logic items in spec §3.5, or the materialize/freeze/render pipeline; password-reset email or account self-service (admin manages users).

---

## Architecture

```
                         ┌─────────────────────────────────────────┐
  Browser (LAN only) ──► │  Single uvicorn process (Windows host)   │
                         │  webapp.api.main:app                     │
  GET /            ─────►│   SPA fallback ─► frontend/dist/index.html│  P4a
  GET /assets/*    ─────►│   StaticFiles(frontend/dist)             │  P4a
  POST /auth/login ─────►│   auth router  (set httpOnly cookie)     │  P4b
  GET  /auth/me    ─────►│   auth router                            │  P4b
  POST /jobs       ─────►│   require_role("admin")                  │  P4b gate
  POST /rosters/.. ─────►│   require_role("admin","editor")         │  P4b gate
  POST /rosters/{id}/confirm ─► require_role("admin") ─► archives   │  P4c
  GET  /archives   ─────►│   require_role(any) (viewer-safe list)   │  P4c
  GET  /archives/{id}/excel ─► download confirmed xlsx bytes        │  P4c
                         │            │                              │
                         │            ▼                              │
                         │   SQLite  webapp_data/shift.db            │
                         │   + users  + archives (additive tables)   │
                         └─────────────────────────────────────────┘
   deploy\start.bat  ──► venv + pip -r webapp/requirements.txt ──► uvicorn --host 0.0.0.0 --port 8000
   deploy\backup.bat ──► python deploy/backup.py  (sqlite .backup + archive dump → target dir)
```

- **Same-origin everywhere.** In dev, the Vite proxy (`frontend/vite.config.ts`) forwards `/jobs`, `/rosters`, `/masters`, `/master-sets` to `:8000`. In prod there is no proxy: the one process serves both. `frontend/src/api/http.ts` already uses `BASE = import.meta.env.VITE_API_BASE ?? ''` → relative paths → same origin. **`VITE_API_BASE` must stay unset for prod builds.**
- **Additive schema.** `users` and `archives` are added exactly like `init_master_db`: a new `init_auth_db(conn)` + `init_archive_db(conn)` called from `webapp/api/db.py::init_db`. The existing `rosters` table already has `status TEXT CHECK(status IN('draft','confirmed'))` and `confirmed_at` — P4c reuses them, no migration of roster columns needed.
- **Stdlib-only auth.** Hashing: `hashlib.pbkdf2_hmac('sha256', pw, salt, ITERATIONS)`; verify with `hmac.compare_digest`. Token: `b64url(payload) + '.' + b64url(HMAC_SHA256(secret, payload))` where `payload = {"uid":..,"role":..,"exp":<epoch>}`. No JWT/passlib/itsdangerous/python-jose dependency. Secret from `SHIFT_AUTH_SECRET` (persisted on first run if unset — see P4b Task 3).
- **Confirm reuses the shipped renderer.** `POST /rosters/{rid}/confirm` performs the exact sequence already in `main.py::get_roster_excel` (`build_roster_grid` → `roster_warnings` → `_format_warnings` → `render_directiona`) to produce bytes, then stores `(roster_id, year, month, xlsx_bytes, sha256, archived_at)` and flips `rosters.status`. The renderer is deterministic, so re-confirm of an unchanged roster yields the same checksum (asserted in a test).
- **Windows-safety.** All path joins use `os.path.join` / `pathlib.Path`; all text writes pass explicit `encoding=` and `newline=''` where CSV byte-fidelity matters (already true in `materialize.py`); xlsx archive bytes are stored/served as binary BLOBs; `.bat` files are authored with CRLF; the DB path is an env-configurable absolute Windows path.

---

## Tech Stack

- **Backend:** Python 3.13, FastAPI, Starlette `StaticFiles` + a catch-all route, `uvicorn[standard]`. Auth = **stdlib** `hashlib`, `hmac`, `secrets`, `base64`, `json`, `time`. SQLite via the existing `webapp/api/db.py` connection helper. Tests: `pytest` + `fastapi.testclient.TestClient` (Starlette), files under `tests/` (root `pytest.ini`; `norecursedirs = archive .claude .venv`).
- **Frontend:** existing Vite + React 18 + TS + TanStack Query + Zustand. New: a `LoginGate` component + `authApi.ts` + an `useAuth` hook + role-based control hiding. Tests: Vitest + @testing-library/react + user-event + jsdom (existing `src/test/setup.ts`). **No new frontend dependency.**
- **Deploy:** `deploy/` shell — Windows `.bat` (primary), an optional NSSM note, an optional `docker-compose.yml` (alternative). No new runtime deps; `requirements.txt` pinned.

Commands:
- Backend single test: `python -m pytest tests/test_static_spa.py -q`
- Backend auth suite: `python -m pytest tests/test_auth.py tests/test_auth_roles.py -q`
- Backend confirm/archive: `python -m pytest tests/test_confirm_archive.py tests/test_backup.py -q`
- Full backend (fast): `python -m pytest -q -m "not slow"`
- Frontend login UI: `cd frontend && npx vitest run src/auth`
- Frontend types: `cd frontend && npm run typecheck`
- Prod build: `cd frontend && npm run build` (emits `frontend/dist`)

---

## File Structure (new/changed)

```
webapp/api/
  static.py                 # NEW P4a: mount_spa(app, dist_dir) — StaticFiles + SPA fallback
  auth/
    __init__.py             # NEW P4b
    schema.py               # NEW P4b: init_auth_db(conn) + USERS table DDL
    passwords.py            # NEW P4b: hash_password / verify_password (pbkdf2_hmac)
    tokens.py               # NEW P4b: sign_token / verify_token (hmac), secret resolution
    service.py              # NEW P4b: create_user / authenticate / get_user
    deps.py                 # NEW P4b: current_user / require_role(*roles) dependencies
    routes.py               # NEW P4b: /auth/login, /auth/logout, /auth/me, /auth/users (admin)
    bootstrap.py            # NEW P4b: ensure_admin() first-run + `python -m webapp.api.auth.bootstrap`
  archive/
    __init__.py             # NEW P4c
    schema.py               # NEW P4c: init_archive_db(conn) + ARCHIVES table DDL
    service.py              # NEW P4c: confirm_roster / list_archives / get_archive_bytes
    routes.py               # NEW P4c: POST /rosters/{rid}/confirm, GET /archives, GET /archives/{id}/excel
  db.py                     # CHANGED: init_db also calls init_auth_db + init_archive_db
  main.py                   # CHANGED: include auth+archive routers, mount_spa LAST, gate endpoints
  config.py                 # CHANGED: frontend_dist, auth_secret_path, token_ttl, admin bootstrap env

frontend/src/
  auth/
    authApi.ts              # NEW P4b: login/logout/me (same-origin, credentials: 'include')
    useAuth.ts              # NEW P4b: TanStack-Query-backed session + role helpers
    LoginGate.tsx           # NEW P4b: wraps App; shows login form until authenticated
    LoginGate.test.tsx      # NEW P4b
    roles.ts                # NEW P4b: can(role, capability) pure helper + tests
    roles.test.ts           # NEW P4b
  main.tsx                  # CHANGED: wrap <App/> in <LoginGate>
  api/http.ts               # CHANGED: send credentials + 401 → AuthError (additive)

deploy/
  build_frontend.bat        # NEW P4d
  start.bat                 # NEW P4d  (CRLF)
  backup.bat                # NEW P4d  (CRLF)
  backup.py                 # NEW P4d  (tested Python fallback)
  install_service.md        # NEW P4d  (NSSM note)
  docker-compose.yml        # NEW P4d  (OPTIONAL alternative)
  README.md                 # NEW P4d  (install/host/port/firewall/backup + §13 checklist)

webapp/requirements.txt     # CHANGED: pinned; comment that python-multipart is intentionally NOT used

tests/
  test_static_spa.py        # NEW P4a
  test_auth.py              # NEW P4b (hashing, token round-trip, login/bad-creds)
  test_auth_roles.py        # NEW P4b (role-gating 401/403)
  test_confirm_archive.py   # NEW P4c
  test_backup.py            # NEW P4c
```

---

# P4a — Production same-origin serving

> Goal: one process serves the built SPA + the JSON API, with API routes winning over the SPA fallback. Implemented as a `mount_spa(app, dist_dir)` helper mounted **after** all API routers.

### Task P4a-1 — `mount_spa` helper + StaticFiles + SPA fallback (TDD)

- [ ] **Write the test first.** `tests/test_static_spa.py`. Build a throwaway `dist/` fixture so the test never depends on a real `npm run build`:

```python
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div>'
        '<script src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('spa')", encoding="utf-8")
    monkeypatch.setenv("SHIFT_FRONTEND_DIST", str(dist))
    # Import after env is set so config picks up the dist dir.
    import importlib
    import webapp.api.config as config
    importlib.reload(config)
    import webapp.api.main as main
    importlib.reload(main)
    return TestClient(main.app)


def test_root_serves_spa_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="root"' in r.text


def test_spa_query_route_serves_index(client):
    # ?view=masters is a client-side route — must still return index.html.
    r = client.get("/?view=masters")
    assert r.status_code == 200
    assert 'id="root"' in r.text


def test_unknown_spa_path_falls_back_to_index(client):
    r = client.get("/some/deep/client/route")
    assert r.status_code == 200
    assert 'id="root"' in r.text


def test_asset_is_served_with_js_mimetype(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_health_is_json_not_spa(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_api_route_is_404_json_not_index(client):
    # API namespace 404s must stay JSON 404 — they must NOT be swallowed by the
    # SPA fallback (otherwise the client can never detect a missing roster/job).
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404
    assert "id=\"root\"" not in r.text
```

- [ ] **Watch it fail** (`mount_spa` does not exist).
- [ ] **Implement** `webapp/api/static.py`:
  - `mount_spa(app, dist_dir)`: if `dist_dir` is falsy or missing, return without mounting (dev mode — Vite serves the SPA; tests for API-only still pass).
  - Mount `StaticFiles(directory=os.path.join(dist_dir, "assets"))` at `/assets`.
  - Register a catch-all `@app.get("/{full_path:path}")` that returns `FileResponse(index.html)` for any path **not** under the API namespace. Guard with an explicit prefix allowlist so the catch-all never shadows JSON 404s:
    ```python
    API_PREFIXES = ("health", "auth", "jobs", "rosters", "masters", "master-sets", "archives")
    # in the catch-all: if full_path == "" or first segment not in API_PREFIXES -> index.html
    # else: raise HTTPException(404)  (let the real API 404 surface as JSON)
    ```
  - Serve root-level static files (`favicon.ico`, `vite.svg`) by checking `dist_dir` for the exact file before falling back to index.
- [ ] In `webapp/api/config.py` add `frontend_dist: Optional[str] = os.environ.get("SHIFT_FRONTEND_DIST") or None`.
- [ ] In `webapp/api/main.py`, **after** all `app.include_router(...)` and all `@app.get`/`@app.post` API routes, call `mount_spa(app, settings.frontend_dist)`. The catch-all must be registered last so Starlette matches the explicit API routes first.
- [ ] **Watch it pass.** Run `python -m pytest tests/test_static_spa.py -q`.
- [ ] **Commit:** `feat(p4a): serve built SPA same-origin with API-aware fallback`

### Task P4a-2 — document the prod build + same-origin contract

- [ ] Update `frontend/.env.example` to state `VITE_API_BASE=` (empty) for prod, with a comment that dev uses the Vite proxy.
- [ ] Add a short "Production build" section to `webapp/README.md`: `cd frontend && npm run build` → `frontend/dist`; set `SHIFT_FRONTEND_DIST`; run uvicorn; dev==prod, no CORS.
- [ ] **Commit:** `docs(p4a): document same-origin prod build (VITE_API_BASE empty)`

---

# P4b — Auth (local accounts + roles), stdlib-only

> Goal: login → signed session cookie; a `require_role` dependency; first-run admin bootstrap; gate existing endpoints; a React login gate + role-based UI hiding. **No new Python dependency.**

### Task P4b-1 — password hashing (stdlib pbkdf2) (TDD)

- [ ] **Test first.** `tests/test_auth.py` (part 1):

```python
from webapp.api.auth.passwords import hash_password, verify_password


def test_hash_is_salted_and_verifies():
    h = hash_password("correct horse")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", h) is True
    assert verify_password("wrong", h) is False


def test_two_hashes_of_same_password_differ():
    # per-user random salt → different encoded hashes
    assert hash_password("pw") != hash_password("pw")


def test_verify_is_constant_time_and_handles_garbage():
    assert verify_password("x", "not-a-valid-encoding") is False
```

- [ ] **Implement** `webapp/api/auth/passwords.py`: encode as `pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>`, `iter = 240_000` (constant `ITERATIONS`), salt = `secrets.token_bytes(16)`, verify parses the 4 fields and uses `hmac.compare_digest`. Garbage encoding → `False` (never raises).
- [ ] **Commit:** `feat(p4b): stdlib pbkdf2 password hashing`

### Task P4b-2 — signed session token (stdlib hmac) (TDD)

- [ ] **Test first.** `tests/test_auth.py` (part 2):

```python
import time
from webapp.api.auth.tokens import sign_token, verify_token, TokenError


SECRET = b"test-secret-bytes"


def test_token_round_trips_uid_and_role():
    tok = sign_token({"uid": 7, "role": "admin"}, SECRET, ttl_seconds=3600)
    claims = verify_token(tok, SECRET)
    assert claims["uid"] == 7 and claims["role"] == "admin"


def test_tampered_payload_is_rejected():
    tok = sign_token({"uid": 7, "role": "viewer"}, SECRET, ttl_seconds=3600)
    head, sig = tok.split(".")
    forged = head[:-1] + ("A" if head[-1] != "A" else "B") + "." + sig
    with pytest.raises(TokenError):
        verify_token(forged, SECRET)


def test_wrong_secret_is_rejected():
    tok = sign_token({"uid": 1, "role": "admin"}, SECRET, ttl_seconds=3600)
    with pytest.raises(TokenError):
        verify_token(tok, b"other-secret")


def test_expired_token_is_rejected():
    tok = sign_token({"uid": 1, "role": "admin"}, SECRET, ttl_seconds=-1)
    with pytest.raises(TokenError):
        verify_token(tok, SECRET)
```
(add `import pytest` at top of file)

- [ ] **Implement** `webapp/api/auth/tokens.py`:
  - `sign_token(claims, secret, ttl_seconds)`: `payload = {**claims, "exp": int(time.time()) + ttl_seconds}`; `body = b64url(json.dumps(payload, separators=(",",":")).encode())`; `sig = b64url(hmac.new(secret, body, hashlib.sha256).digest())`; return `f"{body}.{sig}"`.
  - `verify_token(token, secret)`: split on `.`; recompute sig; `hmac.compare_digest`; decode payload; check `exp > now`; raise `TokenError` on any failure (bad shape, bad sig, expired). Never trust the payload before the signature check.
- [ ] **Commit:** `feat(p4b): stdlib hmac-signed session tokens`

### Task P4b-3 — users table, service, secret persistence, bootstrap (TDD)

- [ ] **Test first.** extend `tests/test_auth.py` (part 3) with an in-memory/temp DB via the existing `connect`/`init_db`:

```python
from webapp.api.db import connect, init_db
from webapp.api.auth import service


@pytest.fixture()
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    return c


def test_create_and_authenticate(conn):
    service.create_user(conn, login_id="alice", password="pw123456", role="editor", name="Alice")
    u = service.authenticate(conn, "alice", "pw123456")
    assert u["role"] == "editor" and u["login_id"] == "alice"
    assert service.authenticate(conn, "alice", "wrong") is None
    assert service.authenticate(conn, "nobody", "pw") is None


def test_login_id_is_unique(conn):
    service.create_user(conn, login_id="bob", password="pw123456", role="viewer")
    with pytest.raises(service.DuplicateUser):
        service.create_user(conn, login_id="bob", password="pw999999", role="viewer")


def test_role_is_validated(conn):
    with pytest.raises(ValueError):
        service.create_user(conn, login_id="x", password="pw123456", role="superuser")


def test_ensure_admin_is_idempotent(conn):
    from webapp.api.auth.bootstrap import ensure_admin
    a = ensure_admin(conn, login_id="admin", password="changeme123")
    b = ensure_admin(conn, login_id="admin", password="changeme123")
    assert a == b  # second call is a no-op, returns the same user id
    assert service.authenticate(conn, "admin", "changeme123")["role"] == "admin"
```

- [ ] **Implement** `webapp/api/auth/schema.py` `init_auth_db(conn)`:
  ```sql
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    login_id TEXT NOT NULL UNIQUE,
    name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN('admin','editor','viewer')),
    created_at TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0
  );
  ```
- [ ] Wire `init_auth_db(conn)` into `webapp/api/db.py::init_db` (alongside `init_master_db`).
- [ ] **Implement** `webapp/api/auth/service.py`: `create_user` (validate role ∈ {admin,editor,viewer}, hash pw, `DuplicateUser` on `UNIQUE` violation, `created_at` = ISO-8601 UTC), `authenticate` (lookup by `login_id`, `verify_password`, ignore `disabled=1`, return a dict or `None`), `get_user(conn, uid)`, `list_users`, `set_password`, `set_disabled`.
- [ ] **Implement** secret resolution in `webapp/api/auth/tokens.py` (or `config.py`): `resolve_secret()` reads `SHIFT_AUTH_SECRET`; if unset, read/create a `webapp_data/.auth_secret` file (`secrets.token_bytes(32)`, written with `0o600` where supported). This keeps sessions valid across restarts without committing a secret.
- [ ] **Implement** `webapp/api/auth/bootstrap.py`: `ensure_admin(conn, login_id, password)` creates the admin only if `users` is empty (idempotent); a `__main__` block (`python -m webapp.api.auth.bootstrap`) reads `SHIFT_ADMIN_ID` / `SHIFT_ADMIN_PW` env (refuse to run with a blank/short password — fail loudly) and prints a one-line confirmation. Called from `start.bat`.
- [ ] **Commit:** `feat(p4b): users table, auth service, secret persistence, admin bootstrap`

### Task P4b-4 — login/logout/me routes + `require_role` dependency (TDD)

- [ ] **Test first.** `tests/test_auth_roles.py`. Use a `TestClient` against `main.app` with a temp DB (override `get_db`), seed an admin + editor + viewer:

```python
def test_login_sets_cookie_and_me_returns_role(client_with_users):
    c = client_with_users
    r = c.post("/auth/login", json={"login_id": "admin", "password": "adminpw123"})
    assert r.status_code == 200
    assert "session" in r.cookies  # httpOnly session cookie set
    me = c.get("/auth/me")
    assert me.status_code == 200 and me.json()["role"] == "admin"


def test_bad_credentials_401(client_with_users):
    r = client_with_users.post("/auth/login", json={"login_id": "admin", "password": "nope"})
    assert r.status_code == 401


def test_me_without_session_401(client_with_users):
    fresh = client_with_users  # no login performed yet in this case
    r = fresh.get("/auth/me")
    assert r.status_code == 401


def test_bearer_fallback_works_for_cli(client_with_users, admin_token):
    r = client_with_users.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
```

- [ ] **Implement** `webapp/api/auth/deps.py`:
  - `current_user(request, conn=Depends(get_db))`: read token from the `session` cookie OR `Authorization: Bearer`; `verify_token`; load user; raise `HTTPException(401)` if missing/invalid. Returns the user dict.
  - `require_role(*roles)`: returns a dependency that calls `current_user` then raises `HTTPException(403)` if `user["role"]` not in `roles`. Admin is NOT implicitly all-powerful unless `"admin"` is in the list — but for convenience, define the role gates with admin explicitly included where appropriate (below).
- [ ] **Implement** `webapp/api/auth/routes.py` (`APIRouter`):
  - `POST /auth/login` (JSON body `{login_id,password}`, **not** form — no python-multipart): authenticate → `sign_token({"uid","role"}, secret, ttl)` → `Response.set_cookie("session", token, httponly=True, samesite="strict", max_age=ttl, path="/")` → return `{uid,login_id,role,name}`. Bad creds → 401.
  - `POST /auth/logout`: clear the cookie.
  - `GET /auth/me`: `Depends(current_user)` → return the user public fields.
  - `GET /auth/users` / `POST /auth/users` / `PUT /auth/users/{id}` (password/disable) — `Depends(require_role("admin"))`.
- [ ] Include the auth router in `main.py` (before `mount_spa`).
- [ ] **Watch pass.** `python -m pytest tests/test_auth.py tests/test_auth_roles.py -q`.
- [ ] **Commit:** `feat(p4b): /auth login/logout/me + admin user mgmt + require_role`

### Task P4b-5 — gate existing endpoints by role (TDD)

Role policy (spec §10):
- **admin** = generate (`POST /jobs`), masters edit (`POST/PUT/DELETE /masters/**`, clone, 予定申請 import), confirm, user mgmt.
- **editor** = roster manual edits + re-solve (`/rosters/{id}/edits|undo|redo|resolve|freeze`) — admin also allowed.
- **viewer** = read confirmed rosters + download archives only.

- [ ] **Test first.** extend `tests/test_auth_roles.py`:

```python
def test_viewer_cannot_generate(client_with_users, viewer_cookie):
    r = client_with_users.post("/jobs", json={"year": 2026, "month": 6}, cookies=viewer_cookie)
    assert r.status_code == 403


def test_editor_can_edit_but_not_confirm(client_with_users, editor_cookie, draft_rid):
    ok = client_with_users.post(f"/rosters/{draft_rid}/edits", json={...}, cookies=editor_cookie)
    assert ok.status_code in (200, 409)          # edit allowed (409 only on version race)
    no = client_with_users.post(f"/rosters/{draft_rid}/confirm", cookies=editor_cookie)
    assert no.status_code == 403                 # confirm is admin-only


def test_unauthenticated_is_401_on_protected(client_with_users):
    assert client_with_users.post("/jobs", json={"year": 2026, "month": 6}).status_code == 401
```

- [ ] **Implement.** Add `dependencies=[Depends(require_role(...))]` to the existing routes in `main.py`:
  - `POST /jobs` → `require_role("admin")`.
  - `POST /jobs/{id}/freeze`, `/rosters/{id}/edits|undo|redo|resolve` → `require_role("admin","editor")`.
  - `GET /rosters/{id}`, `/rosters/{id}/grid`, `/jobs/{id}`, `/jobs/{id}/result`, `/jobs/{id}/excel`, `/rosters/{id}/excel` → `require_role("admin","editor")` (drafts are not viewer-visible; viewers use `/archives`).
  - All `/masters/**` write routes + clone + 予定申請 import → `require_role("admin")`; master **reads** → `require_role("admin","editor")`.
  - Apply gates at the router level where possible (`APIRouter(dependencies=[...])`) to avoid per-route drift; document the matrix in a module docstring.
- [ ] **Watch pass.**
- [ ] **Commit:** `feat(p4b): role-gate jobs/rosters/masters endpoints`

### Task P4b-6 — frontend role helper (pure) (TDD)

- [ ] **Test first.** `frontend/src/auth/roles.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { can } from './roles';

describe('can', () => {
  it('admin can do everything', () => {
    for (const cap of ['generate','editRoster','editMasters','confirm','manageUsers','viewArchive'] as const)
      expect(can('admin', cap)).toBe(true);
  });
  it('editor edits rosters but cannot confirm or manage users', () => {
    expect(can('editor', 'editRoster')).toBe(true);
    expect(can('editor', 'confirm')).toBe(false);
    expect(can('editor', 'manageUsers')).toBe(false);
  });
  it('viewer can only view archive', () => {
    expect(can('viewer', 'viewArchive')).toBe(true);
    expect(can('viewer', 'editRoster')).toBe(false);
    expect(can('viewer', 'generate')).toBe(false);
  });
});
```

- [ ] **Implement** `frontend/src/auth/roles.ts`: a `Role` union + `Capability` union + a `CAP_MATRIX` table + `can(role, cap)` lookup. Mirror the backend matrix exactly (the backend stays authoritative; this only hides controls).
- [ ] **Commit:** `feat(p4b): client role capability helper`

### Task P4b-7 — login gate + session hook + control hiding (TDD)

- [ ] **Test first.** `frontend/src/auth/LoginGate.test.tsx`: mock `authApi` (`me` rejects with 401 first, then a login resolves to `{role:'admin'}`); assert (a) the login form renders when unauthenticated, (b) submitting calls `login` and then the children render, (c) a bad login surfaces the error message (never swallowed).
- [ ] **Implement**:
  - `frontend/src/auth/authApi.ts`: `login`, `logout`, `me` using `http.ts` (`postJson`/`getJson`). Ensure `http.ts` requests send the cookie — same-origin `fetch` includes cookies by default, but add `credentials: 'same-origin'` explicitly and map HTTP 401 to a new `AuthError` (additive change to `http.ts`, with a unit test that 401 → `AuthError`).
  - `frontend/src/auth/useAuth.ts`: TanStack Query `['auth','me']`; exposes `{user, role, login, logout, isLoading}`.
  - `frontend/src/auth/LoginGate.tsx`: while loading → spinner; if `me` 401 → render the login form; on success render `children`. Show the logged-in user + logout in a corner. Use `can(role, …)` to hide the generate button, masters nav (`?view=masters`), edit toolbar, and confirm button for roles that lack the capability.
  - `frontend/src/main.tsx`: wrap `<App />` in `<LoginGate>`.
- [ ] **Watch pass.** `cd frontend && npx vitest run src/auth && npm run typecheck`.
- [ ] **Commit:** `feat(p4b): login gate, session hook, role-based control hiding`

---

# P4c — Confirm-lock + monthly archive + backup

> Goal: admin confirms a roster → status flips to `confirmed` and the rendered Direction-A Excel bytes are stored (checksummed) in `archives`; viewers list/download confirmed months only; a backup script copies the DB + archives.

### Task P4c-1 — archives table + confirm service (TDD)

- [ ] **Test first.** `tests/test_confirm_archive.py`:

```python
def test_confirm_flips_status_and_writes_archive(conn, frozen_draft_rid):
    from webapp.api.archive import service
    rec = service.confirm_roster(conn, frozen_draft_rid, user_id="admin")
    row = conn.execute("SELECT status, confirmed_at FROM rosters WHERE id=?",
                       (frozen_draft_rid,)).fetchone()
    assert row["status"] == "confirmed" and row["confirmed_at"]
    arch = conn.execute("SELECT year, month, xlsx_bytes, checksum FROM archives WHERE roster_id=?",
                        (frozen_draft_rid,)).fetchone()
    assert arch["xlsx_bytes"][:2] == b"PK"            # xlsx is a zip
    import hashlib
    assert arch["checksum"] == hashlib.sha256(arch["xlsx_bytes"]).hexdigest()
    assert rec["checksum"] == arch["checksum"]


def test_reconfirm_is_deterministic_same_checksum(conn, frozen_draft_rid):
    from webapp.api.archive import service
    a = service.confirm_roster(conn, frozen_draft_rid, user_id="admin")["checksum"]
    b = service.confirm_roster(conn, frozen_draft_rid, user_id="admin")["checksum"]
    assert a == b   # deterministic renderer → identical bytes on re-confirm
```

- [ ] **Implement** `webapp/api/archive/schema.py` `init_archive_db(conn)`:
  ```sql
  CREATE TABLE IF NOT EXISTS archives (
    id INTEGER PRIMARY KEY,
    roster_id INTEGER NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
    year INTEGER NOT NULL, month INTEGER NOT NULL,
    xlsx_bytes BLOB NOT NULL, checksum TEXT NOT NULL,
    archived_at TEXT NOT NULL, archived_by TEXT
  );
  CREATE INDEX IF NOT EXISTS ix_arch_year_month ON archives(year, month);
  ```
  Wire `init_archive_db` into `db.py::init_db`.
- [ ] **Implement** `webapp/api/archive/service.py`:
  - `confirm_roster(conn, rid, user_id)`: reuse the exact render path from `main.py::get_roster_excel` — `build_roster_grid` → `roster_warnings` → `_format_warnings` → `render_directiona` — to produce `xlsx`. Compute `sha256`. Upsert the `archives` row for this roster (replace prior archive on re-confirm so the checksum test holds). Set `rosters.status='confirmed'`, `confirmed_at = ISO now`. Return `{roster_id, year, month, checksum, archived_at}`.
  - `list_archives(conn)` → `[{id, roster_id, year, month, checksum, archived_at}]` (no BLOB).
  - `get_archive_bytes(conn, archive_id)` → `(bytes, year, month)` or `None`.
  - Factor the shared render into a small helper so `get_roster_excel` and `confirm_roster` call one function (avoid drift — spec §6 single-source rule).
- [ ] **Commit:** `feat(p4c): archives table + confirm_roster (render+checksum+status flip)`

### Task P4c-2 — confirm/archive routes + viewer visibility (TDD)

- [ ] **Test first.** extend `tests/test_confirm_archive.py` with `TestClient`:

```python
def test_admin_confirm_then_viewer_can_list_and_download(client, admin_cookie, viewer_cookie, frozen_draft_rid):
    assert client.post(f"/rosters/{frozen_draft_rid}/confirm", cookies=admin_cookie).status_code == 200
    lst = client.get("/archives", cookies=viewer_cookie)
    assert lst.status_code == 200 and len(lst.json()) == 1
    aid = lst.json()[0]["id"]
    dl = client.get(f"/archives/{aid}/excel", cookies=viewer_cookie)
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_viewer_cannot_see_or_edit_draft(client, viewer_cookie, frozen_draft_rid):
    assert client.get(f"/rosters/{frozen_draft_rid}", cookies=viewer_cookie).status_code == 403
    assert client.post(f"/rosters/{frozen_draft_rid}/confirm", cookies=viewer_cookie).status_code == 403
```

- [ ] **Implement** `webapp/api/archive/routes.py`:
  - `POST /rosters/{rid}/confirm` → `require_role("admin")` → `confirm_roster`. (Register on the existing roster router or a new one included in `main.py`.)
  - `GET /archives` → `require_role("admin","editor","viewer")` → `list_archives`.
  - `GET /archives/{id}/excel` → same roles → bytes with the RFC-5987 `Content-Disposition` filename (`勤務表_{year}年{month}月.xlsx`, reuse the existing `quote(...)` pattern from `main.py`).
- [ ] **Watch pass.**
- [ ] **Commit:** `feat(p4c): confirm + archive list/download routes (viewer-safe)`

### Task P4c-3 — backup script (Python fallback, tested) + .bat (TDD)

- [ ] **Test first.** `tests/test_backup.py`:

```python
def test_backup_copies_db_and_dumps_archives(tmp_path):
    from webapp.api.db import connect, init_db
    from webapp.api.archive import service
    src = tmp_path / "shift.db"
    conn = connect(str(src)); init_db(conn)
    # ... seed a confirmed roster + archive ...
    target = tmp_path / "backup"
    from deploy.backup import run_backup
    manifest = run_backup(db_path=str(src), target_dir=str(target))
    # DB copied + a per-archive .xlsx dumped + a manifest listing checksums
    assert (target / "shift.db").exists()
    assert any(p.suffix == ".xlsx" for p in target.iterdir())
    assert manifest["db_bytes"] > 0 and manifest["archive_count"] >= 1
```

- [ ] **Implement** `deploy/backup.py`:
  - `run_backup(db_path, target_dir)`: create a timestamped `target_dir` (ISO, Windows-safe name — colons replaced); use the **SQLite online backup API** (`sqlite3.Connection.backup`) to copy the DB consistently (safe even if the server is running); also dump each `archives` row to `{year}-{month:02d}_勤務表.xlsx`; write a `manifest.json` (db size, archive checksums, timestamp). Return the manifest dict.
  - A `__main__` block reading `SHIFT_DB_PATH` + a `--target` arg (default a `backup\` sibling).
- [ ] **Author** `deploy/backup.bat` (CRLF): activate venv, `python deploy\backup.py --target "<configured backup medium>"`, intended to be run by Windows Task Scheduler daily.
- [ ] **Watch pass.** `python -m pytest tests/test_backup.py -q`.
- [ ] **Commit:** `feat(p4c): tested python backup (sqlite .backup + archive dump) + backup.bat`

---

# P4d — Windows deployment packaging

> Goal: a `deploy/` folder that lets hospital IT install + run the single-process app on Windows with minimal dependencies; Docker is an optional alternative.

### Task P4d-1 — pin requirements (no new heavy deps)

- [ ] **Edit** `webapp/requirements.txt`: pin tested versions; add a comment block:
  ```
  # Auth is stdlib-only (hashlib.pbkdf2_hmac + hmac) — NO passlib/jose/itsdangerous.
  # python-multipart is intentionally NOT included: login + 予定申請 import both use
  # raw JSON / raw request body, never multipart/form-data.
  fastapi==<pin>
  uvicorn[standard]==<pin>
  httpx==<pin>           # test client only
  # (openpyxl / ortools / pandas etc. come from the existing shift_scheduler requirements)
  ```
  Pin to the versions currently resolved in `.venv` (read them; do not invent).
- [ ] **Commit:** `chore(p4d): pin webapp requirements; document stdlib-auth + no-multipart`

### Task P4d-2 — frontend build + start scripts (Windows, CRLF)

- [ ] **Author** `deploy/build_frontend.bat` (CRLF): `cd frontend` → `npm ci` → `npm run build` (asserts `VITE_API_BASE` is empty for same-origin) → leaves `frontend/dist`. Echo the dist path that `SHIFT_FRONTEND_DIST` should point to.
- [ ] **Author** `deploy/start.bat` (CRLF):
  - Create/activate a venv (`py -3 -m venv .venv` then `.venv\Scripts\activate`).
  - `pip install -r webapp\requirements.txt`.
  - Set env: `SHIFT_DB_PATH` (fixed absolute Windows path, e.g. `C:\shift\data\shift.db`), `SHIFT_FRONTEND_DIST=...\frontend\dist`, `SHIFT_AUTH_SECRET` (or rely on the persisted `.auth_secret` file), `SHIFT_ADMIN_ID` / `SHIFT_ADMIN_PW` for first run.
  - `python -m webapp.api.auth.bootstrap` (idempotent admin creation).
  - `python -m uvicorn webapp.api.main:app --host 0.0.0.0 --port 8000` (LAN-bound; firewall restricts to the subnet — see README). Document that `--host 0.0.0.0` binds all interfaces and the **Windows Firewall rule is what scopes it to the LAN**.
  - No `--reload` (single deterministic process).
- [ ] **Smoke-document** the manual run order in the README (Task P4d-4).
- [ ] **Commit:** `feat(p4d): Windows build_frontend.bat + start.bat (venv, bootstrap, LAN uvicorn)`

### Task P4d-3 — NSSM service note + optional docker-compose

- [ ] **Author** `deploy/install_service.md`: how to register the process as a Windows service with NSSM (`nssm install ShiftScheduler "...\python.exe" "-m uvicorn webapp.api.main:app --host 0.0.0.0 --port 8000"`, set the working dir + the `SHIFT_*` env, AppStdout/AppStderr log files, auto-start). Note the alternative: Task Scheduler "at startup".
- [ ] **Author** `deploy/docker-compose.yml` (OPTIONAL): a single `app` service (build the frontend in a multi-stage image, run uvicorn, mount a `webapp_data` volume). A prominent comment: **Docker Desktop on Windows needs WSL2/admin and is heavyweight — the `.bat`/NSSM path is the recommended default; this compose file is only for sites that already run Docker.**
- [ ] **Commit:** `docs(p4d): NSSM service note + optional docker-compose alternative`

### Task P4d-4 — deploy README + IT-coordination checklist (spec §13)

- [ ] **Author** `deploy/README.md`:
  - **Architecture in one line:** one Python process serves SPA + API; SQLite file DB; LAN-only.
  - **Install location:** e.g. `C:\shift\` (app), `C:\shift\data\` (DB + `.auth_secret`), backup medium TBD with IT.
  - **Fixed host/port:** `0.0.0.0:8000` on the install machine; users reach `http://<hostname-or-IP>:8000/`. **Host/IP/port are IT-coordinated (Decision §3).**
  - **Windows Firewall:** add an inbound rule allowing TCP 8000 **from the LAN subnet only** (scope = Local subnet / the clinical VLAN). Do NOT expose externally (spec §13).
  - **First run:** build_frontend → set env → start.bat (bootstraps admin) → log in → admin creates editor/viewer users.
  - **Backup:** schedule `deploy\backup.bat` daily (Task Scheduler) to the IT-agreed medium; verify `manifest.json` checksums.
  - **§13 IT-coordination checklist (copy from the spec):** install location; fixed hostname/IP; firewall (LAN-only); backup medium; power / always-on; OS-update policy; who holds the admin credential; data-stays-in-LAN confirmation.
  - **Updates:** stop service → `git pull` (or copy build) → `build_frontend.bat` → restart.
- [ ] **Commit:** `docs(p4d): deploy README + §13 IT-coordination checklist`

---

## Self-Review

**Spec coverage**
- §10 auth → P4b (users/roles/hash/login/`require_role`/bootstrap/UI hiding). ✅
- §10 confirm-lock → P4c-1/2 (`status draft→confirmed`, admin-only). ✅
- §10 monthly archive → P4c-1/2 (`archives` BLOB + checksum + list/download, viewer-safe). ✅
- §10 backup → P4c-3 (sqlite `.backup` + archive dump, tested + `.bat`). ✅
- §13 deployment/IT checklist → P4d (start.bat/NSSM/firewall/README checklist). ✅
- §5 data model (`users`, `archives`) → matches (P4 adds `disabled`, `checksum`, `archived_by` — additive, documented).
- §4 same-origin single process → P4a. ✅
- Determinism guarantee (spec §3.2, §11) → **no code added on the solve path**; confirm only *renders* the already-frozen roster. ✅

**Placeholder scan**
- Test bodies with `{...}` / `# ... seed ...` (e.g. `test_editor_can_edit_but_not_confirm`, `test_backup...`) are **intentional fixtures to fill at implementation time**, not shippable code. Every such spot is inside a test and flagged with a comment. No placeholders exist in described production modules.
- `<pin>` in requirements is a deliberate instruction to read real versions from `.venv` — do not commit the literal `<pin>`.

**Type consistency**
- Token claims `{uid:int, role:str, exp:int}` consistent between `sign_token`/`verify_token`/`current_user`.
- Roles are the single closed set `{admin,editor,viewer}` in: DB `CHECK`, `service.create_user` validation, `require_role`, frontend `roles.ts`. The frontend `CAP_MATRIX` must mirror the backend gate matrix (called out as a drift risk — keep them in sync; backend is authoritative).
- `archives.checksum` is `sha256 hexdigest` everywhere (service return, DB column, test assertion).

**Windows-safety**
- `.bat`/`backup.bat`/`start.bat` authored with CRLF; `.gitattributes` note if needed so they aren't normalized to LF.
- All paths via `os.path.join`/`pathlib`; DB + dist + backup paths are env-configurable absolute Windows paths.
- xlsx stored/served as binary BLOB; backup uses the SQLite online-backup API (consistent while the server runs — important on Windows where the file may be locked).
- `.auth_secret` written with restrictive perms where supported; documented that on Windows the directory ACL is the real guard.
- uvicorn bound `0.0.0.0` + **Windows Firewall LAN-scope** is the access control (documented; not left implicit).
- No `python-multipart`: login + 予定申請 both use JSON/raw body — confirmed against the existing `requests_import` raw-body pattern.

**Test-first discipline:** every task lists write-test → watch-fail → implement → watch-pass → commit, with real pytest/Vitest code and runnable commands.

---

## Decisions for the operator (must confirm — NOT decided in this plan)

1. **Is viewer login needed for v1, or admin/editor-only first?** Spec §12 allows a single-admin in-house trial before opening to viewers. The plan ships all three roles, but the rollout can disable viewer accounts initially (create only admin/editor) and turn on viewer access later — **no code change required**, just don't create viewer users. Confirm whether viewers are in scope for the first production cutover.
2. **AD / SSO integration?** v1 is **local accounts** (this plan). If hospital IT requires Active Directory / SSO (LDAP bind or SAML/OIDC), that is a **future phase** — the `authenticate()` seam is where it would plug in. Confirm whether local accounts are acceptable for v1.
3. **Exact install machine, fixed hostname/IP, port, and backup medium (IT-coordinated).** The README leaves `C:\shift\`, `0.0.0.0:8000`, and "backup medium TBD" as placeholders. IT must fix: the always-on host, its hostname/IP, the port (default 8000), the firewall LAN scope, and the backup destination (network share / external drive) + retention. (spec §13, §15.)
4. **Session token transport: httpOnly cookie (chosen) vs Bearer-in-localStorage.** This plan uses an **httpOnly `session` cookie** (XSS-safer, automatic same-origin) with a `Authorization: Bearer` fallback for tests/CLI. On a plain-HTTP LAN the cookie cannot be `Secure`; if IT can provide TLS (reverse proxy or self-signed cert trusted on clients), set `Secure` + keep `SameSite=Strict`. Confirm the TLS posture.
5. **Token TTL + idle/refresh policy.** Default proposed: 12h TTL, re-login on expiry (no refresh tokens in v1). Confirm acceptable session length for ward use.
6. **Auth secret storage.** Default: a `.auth_secret` file under `webapp_data\` (auto-generated). Confirm IT is OK with a file-based secret vs an env-injected `SHIFT_AUTH_SECRET`. Rotating it invalidates all sessions (acceptable).
7. **Password policy + admin credential custody.** Bootstrap refuses blank/short passwords; confirm the minimum length and who holds the initial admin credential.

---

## Suggested execution order

P4a (serving — unblocks dev==prod) → P4b (auth — gates everything) → P4c (confirm/archive/backup — depends on auth roles) → P4d (Windows packaging — depends on all of the above being runnable). Each task is independently testable and committed; P4a and the P4d requirements-pin (P4d-1) can be done first in parallel if two workers are available, since they don't depend on auth.

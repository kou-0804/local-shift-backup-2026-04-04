"""P4b-4/5: auth routes + role gating, exercised through the real app.

These tests need REAL auth (no admin override), so every test module here is
marked ``real_auth`` to opt out of the conftest autouse admin override.
"""
import pytest
from fastapi.testclient import TestClient

import webapp.api.main as main
from webapp.api.db import connect, init_db
from webapp.api.auth import service
from webapp.api.auth.tokens import sign_token

pytestmark = pytest.mark.real_auth

SECRET = b"roles-test-secret"


@pytest.fixture()
def client_with_users(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "auth_secret_env", "roles-test-secret")
    conn = connect(str(tmp_path / "roles.db"))
    init_db(conn)
    service.create_user(conn, login_id="admin", password="adminpw123", role="admin", name="A")
    service.create_user(conn, login_id="ed", password="editorpw123", role="editor", name="E")
    service.create_user(conn, login_id="vw", password="viewerpw123", role="viewer", name="V")
    conn.commit()
    main.app.dependency_overrides[main.get_db] = lambda: conn
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


def _uid(conn_login):
    pass


@pytest.fixture()
def admin_token():
    return sign_token({"uid": 1, "role": "admin"}, SECRET, ttl_seconds=3600)


def _cookie(client, login_id, password):
    r = client.post("/auth/login", json={"login_id": login_id, "password": password})
    assert r.status_code == 200, r.text
    return {"session": r.cookies["session"]}


def test_login_sets_cookie_and_me_returns_role(client_with_users):
    c = client_with_users
    r = c.post("/auth/login", json={"login_id": "admin", "password": "adminpw123"})
    assert r.status_code == 200
    assert "session" in r.cookies
    me = c.get("/auth/me")
    assert me.status_code == 200 and me.json()["role"] == "admin"


def test_bad_credentials_401(client_with_users):
    r = client_with_users.post("/auth/login", json={"login_id": "admin", "password": "nope"})
    assert r.status_code == 401


def test_me_without_session_401(client_with_users):
    # A fresh client with no Cookie jar entry.
    c = TestClient(main.app)
    r = c.get("/auth/me")
    assert r.status_code == 401


def test_bearer_fallback_works_for_cli(client_with_users):
    tok = sign_token({"uid": 1, "role": "admin"}, SECRET, ttl_seconds=3600)
    r = client_with_users.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_logout_clears_cookie(client_with_users):
    c = client_with_users
    c.post("/auth/login", json={"login_id": "admin", "password": "adminpw123"})
    assert c.get("/auth/me").status_code == 200
    c.post("/auth/logout")
    # After logout the session cookie is cleared; a fresh client has no session.
    fresh = TestClient(main.app)
    assert fresh.get("/auth/me").status_code == 401


def test_admin_can_list_and_create_users(client_with_users):
    cookie = _cookie(client_with_users, "admin", "adminpw123")
    lst = client_with_users.get("/auth/users", cookies=cookie)
    assert lst.status_code == 200 and len(lst.json()) == 3
    created = client_with_users.post(
        "/auth/users", cookies=cookie,
        json={"login_id": "new", "password": "newpw1234", "role": "viewer", "name": "N"})
    assert created.status_code == 201


def test_non_admin_cannot_manage_users(client_with_users):
    cookie = _cookie(client_with_users, "ed", "editorpw123")
    assert client_with_users.get("/auth/users", cookies=cookie).status_code == 403


# --- P4b-5: role-gate jobs/rosters/masters ----------------------------------

def _client_as(login_id, password):
    """A TestClient whose cookie jar holds a fresh session for `login_id`."""
    c = TestClient(main.app)
    r = c.post("/auth/login", json={"login_id": login_id, "password": password})
    assert r.status_code == 200, r.text
    return c


def test_unauthenticated_is_401_on_protected(client_with_users):
    assert client_with_users.post("/jobs", json={"year": 2026, "month": 6}).status_code == 401
    assert client_with_users.get("/rosters/999").status_code == 401


def test_viewer_cannot_generate(client_with_users):
    c = _client_as("vw", "viewerpw123")
    assert c.post("/jobs", json={"year": 2026, "month": 6}).status_code == 403


def test_viewer_cannot_read_draft_roster(client_with_users):
    c = _client_as("vw", "viewerpw123")
    assert c.get("/rosters/999").status_code == 403


def test_editor_passes_gate_to_404_on_missing_roster(client_with_users):
    # Gate allows editor -> request falls through to the real 404, NOT 403.
    c = _client_as("ed", "editorpw123")
    assert c.get("/rosters/999").status_code == 404


def test_admin_can_generate_gate(client_with_users, monkeypatch):
    # Replace the runner so we don't spin the real solver; we only test the gate.
    from shift_scheduler.src.models.schedule_result import ScheduleResult
    monkeypatch.setattr(main, "RUNNER", lambda y, m, data_dir: ScheduleResult(
        year=y, month=m, staff=[], day_assignments={}, night_assignments={},
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={},
        validation_errors=[], workbook_bytes=b"PK"))
    c = _client_as("admin", "adminpw123")
    assert c.post("/jobs", json={"year": 2026, "month": 6}).status_code == 201


def test_editor_cannot_write_masters_but_can_read(client_with_users):
    c = _client_as("ed", "editorpw123")
    assert c.put("/masters/1/training", json=[]).status_code == 403
    assert c.get("/master-sets").status_code == 200


def test_viewer_cannot_read_masters(client_with_users):
    c = _client_as("vw", "viewerpw123")
    assert c.get("/master-sets").status_code == 403

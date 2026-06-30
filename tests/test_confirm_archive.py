"""P4c: confirm-lock + monthly archive (service + routes).

Route tests need REAL auth (admin vs viewer), so marked real_auth.
"""
import hashlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as main
from webapp.api.db import connect, init_db
from webapp.api.rosters import freeze_roster
from webapp.api.auth import service as auth_service


def _seed_frozen(conn):
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "佐藤(海)"}],
        day_assignments={1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}},
        night_assignments={}, requests={}, on_call_assignments={},
        daikyu_counts={}, off_counts={"T001": 9}, validation_errors=[],
        daily_location_needs={2: {"ク": 1}})
    techs = [SimpleNamespace(id="T001", name="佐藤(海)", status="在籍",
                             note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return rid


@pytest.fixture()
def conn(tmp_path):
    c = connect(str(tmp_path / "confirm.db"))
    init_db(c)
    return c


@pytest.fixture()
def frozen_draft_rid(conn):
    return _seed_frozen(conn)


# --- P4c-1: service ---------------------------------------------------------

def test_confirm_flips_status_and_writes_archive(conn, frozen_draft_rid):
    from webapp.api.archive import service
    rec = service.confirm_roster(conn, frozen_draft_rid, user_id="admin")
    row = conn.execute("SELECT status, confirmed_at FROM rosters WHERE id=?",
                       (frozen_draft_rid,)).fetchone()
    assert row["status"] == "confirmed" and row["confirmed_at"]
    arch = conn.execute("SELECT year, month, xlsx_bytes, checksum FROM archives WHERE roster_id=?",
                        (frozen_draft_rid,)).fetchone()
    assert arch["xlsx_bytes"][:2] == b"PK"            # xlsx is a zip
    assert arch["checksum"] == hashlib.sha256(arch["xlsx_bytes"]).hexdigest()
    assert rec["checksum"] == arch["checksum"]
    assert rec["year"] == 2026 and rec["month"] == 6


def test_reconfirm_is_deterministic_same_checksum(conn, frozen_draft_rid):
    from webapp.api.archive import service
    a = service.confirm_roster(conn, frozen_draft_rid, user_id="admin")["checksum"]
    b = service.confirm_roster(conn, frozen_draft_rid, user_id="admin")["checksum"]
    assert a == b
    # Exactly one archive row survives re-confirm.
    n = conn.execute("SELECT COUNT(*) FROM archives WHERE roster_id=?",
                     (frozen_draft_rid,)).fetchone()[0]
    assert n == 1


def test_list_and_get_bytes(conn, frozen_draft_rid):
    from webapp.api.archive import service
    service.confirm_roster(conn, frozen_draft_rid, user_id="admin")
    lst = service.list_archives(conn)
    assert len(lst) == 1 and "xlsx_bytes" not in lst[0]
    payload = service.get_archive_bytes(conn, lst[0]["id"])
    assert payload is not None and payload[0][:2] == b"PK"
    assert service.get_archive_bytes(conn, 99999) is None


# --- P4c-2: routes (viewer-safe) --------------------------------------------

@pytest.fixture()
def app_clients(conn, monkeypatch):
    """A confirmed-capable app: admin + viewer users seeded, get_db overridden."""
    monkeypatch.setattr(main.settings, "auth_secret_env", "confirm-test-secret")
    auth_service.create_user(conn, login_id="admin", password="adminpw123", role="admin")
    auth_service.create_user(conn, login_id="vw", password="viewerpw123", role="viewer")
    conn.commit()
    main.app.dependency_overrides[main.get_db] = lambda: conn
    try:
        yield
    finally:
        main.app.dependency_overrides.clear()


def _as(login_id, password):
    c = TestClient(main.app)
    r = c.post("/auth/login", json={"login_id": login_id, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.mark.real_auth
def test_admin_confirm_then_viewer_can_list_and_download(app_clients, frozen_draft_rid):
    admin = _as("admin", "adminpw123")
    assert admin.post(f"/rosters/{frozen_draft_rid}/confirm").status_code == 200
    viewer = _as("vw", "viewerpw123")
    lst = viewer.get("/archives")
    assert lst.status_code == 200 and len(lst.json()) == 1
    aid = lst.json()[0]["id"]
    dl = viewer.get(f"/archives/{aid}/excel")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in dl.headers["content-disposition"]


@pytest.mark.real_auth
def test_viewer_cannot_confirm_or_see_draft(app_clients, frozen_draft_rid):
    viewer = _as("vw", "viewerpw123")
    assert viewer.get(f"/rosters/{frozen_draft_rid}").status_code == 403
    assert viewer.post(f"/rosters/{frozen_draft_rid}/confirm").status_code == 403


@pytest.mark.real_auth
def test_confirm_unknown_roster_404(app_clients):
    admin = _as("admin", "adminpw123")
    assert admin.post("/rosters/999999/confirm").status_code == 404


@pytest.mark.real_auth
def test_download_unknown_archive_404(app_clients, frozen_draft_rid):
    admin = _as("admin", "adminpw123")
    assert admin.get("/archives/999999/excel").status_code == 404

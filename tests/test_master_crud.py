# tests/test_master_crud.py
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from webapp.api.main import app
from webapp.api.db import get_db
from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters import crud
from webapp.api.masters.materialize import materialize_masters

DATA = "shift_scheduler/data"
MASTER_FILES = [
    "技師マスタ_確定版.csv", "スキルマスタ_確定版.csv", "公休数マスタ_確定版.csv",
    "勤務場所マスタ_確定版.csv", "特殊配置ルール_確定版.csv", "業務拡大マスタ_確定版.csv",
    "夜勤回数_確定版.csv", "夜勤スキル一覧.csv",
]


def _seed_conn():
    # check_same_thread=False: TestClient runs sync endpoints in a worker thread.
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_master_db(conn)
    import_dir(conn, DATA, name="現行", created_by="t")
    return conn


@pytest.fixture
def conn():
    c = _seed_conn()
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_db] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_list_staff_returns_imported_rows(client):
    r = client.get("/masters/1/staff")
    assert r.status_code == 200
    assert len(r.json()) == 72


def test_create_staff_rejects_bad_id(client):
    r = client.post("/masters/1/staff", json={
        "tech_id": "X1", "name": "試験　太郎", "gender": "男",
        "experience_years": 3, "night_ok": "○", "status": "在籍", "oncall_ok": "○"})
    assert r.status_code == 422


def test_create_staff_accepts_valid_row(client):
    r = client.post("/masters/1/staff", json={
        "tech_id": "T999", "name": "試験　太郎", "gender": "男",
        "experience_years": 3, "night_ok": "○", "status": "在籍", "oncall_ok": "×"})
    assert r.status_code == 201
    assert len(client.get("/masters/1/staff").json()) == 73


def test_update_skill_cell_constrains_rank(client):
    r = client.put("/masters/1/skill/T001", json={"病院MR": "E"})
    assert r.status_code == 422


def test_update_skill_cell_ok(client):
    r = client.put("/masters/1/skill/T001", json={"病院MR": "B"})
    assert r.status_code == 200


def test_delete_then_list(client):
    assert client.delete("/masters/1/holiday_targets/2027-03").status_code == 200


def test_clone_creates_child_set(client):
    r = client.post("/masters/1/clone", json={"created_by": "t"})
    assert r.status_code == 201
    new_id = r.json()["master_set_id"]
    assert new_id == 2


def test_clone_then_materialize_is_byte_identical(conn):
    # A no-op clone must deep-copy rows + profiles faithfully, so the clone
    # materializes to bytes identical to the source set (and thus the source CSVs).
    new_id = crud.clone_master_set(conn, 1, created_by="t")
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, new_id, dest_dir=tmp)
        for fn in MASTER_FILES:
            got = open(os.path.join(tmp, fn), "rb").read()
            want = open(os.path.join(DATA, fn), "rb").read()
            assert got == want, f"clone byte mismatch in {fn}"

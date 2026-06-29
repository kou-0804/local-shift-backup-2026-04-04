# tests/test_master_write_endpoints.py
"""P3a-2 master WRITE endpoints: /master-sets list + 5 replace-style PUTs.

Gates (mandatory):
  (a) no-op round-trip: clone -> PUT each writable master with the SAME data read
      from GET -> materialize -> byte-identical to the source CSVs.
  (b) value-change: a single edit via PUT is reflected in the materialized CSV AND
      the file still parses via its production loader.
"""
import csv
import io
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from webapp.api.main import app
from webapp.api.db import get_db
from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
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


def _read_csv(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return list(csv.reader(io.StringIO(raw.decode("utf-8"))))


def _clone(client):
    return client.post("/masters/1/clone", json={"created_by": "t"}).json()["master_set_id"]


# --- 1. /master-sets list ---------------------------------------------------

def test_list_master_sets_returns_seed(client):
    r = client.get("/master-sets")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["master_set_id"] == 1
    assert row["name"] == "現行"
    assert row["parent_set_id"] is None
    assert row["created_at"]  # non-empty ISO timestamp


def test_list_master_sets_includes_clone(client):
    nid = _clone(client)
    body = client.get("/master-sets").json()
    ids = {r["master_set_id"]: r for r in body}
    assert nid in ids
    assert ids[nid]["parent_set_id"] == 1


# --- (a) no-op round-trip: every writable master, byte-identical -------------

def test_noop_put_roundtrip_is_byte_identical(client, conn):
    nid = _clone(client)

    loc = client.get(f"/masters/{nid}/location").json()
    pb = client.get(f"/masters/{nid}/power_balance").json()
    assert client.put(f"/masters/{nid}/location_set",
                      json={"locations": loc, "power_balance": pb}).status_code == 200

    sr = client.get(f"/masters/{nid}/special_rules").json()
    assert client.put(f"/masters/{nid}/special_rules", json=sr).status_code == 200

    tr = client.get(f"/masters/{nid}/training").json()
    assert client.put(f"/masters/{nid}/training", json=tr).status_code == 200

    nq = client.get(f"/masters/{nid}/night_quota").json()
    assert client.put(f"/masters/{nid}/night_quota?year_month=2026-07",
                      json=nq).status_code == 200

    no = client.get(f"/masters/{nid}/night_overrides").json()
    assert client.put(f"/masters/{nid}/night_overrides", json=no).status_code == 200

    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, nid, dest_dir=tmp)
        for fn in MASTER_FILES:
            got = open(os.path.join(tmp, fn), "rb").read()
            want = open(os.path.join(DATA, fn), "rb").read()
            assert got == want, f"BYTE MISMATCH in {fn}"


# --- (b) value-change reflected + loader still parses -----------------------

def test_change_location_weekday_reflected_and_parses(client, conn):
    from shift_scheduler.src.loaders.location_loader import LocationLoader
    from shift_scheduler.src.loaders.power_balance_loader import PowerBalanceLoader
    nid = _clone(client)
    loc = client.get(f"/masters/{nid}/location").json()
    pb = client.get(f"/masters/{nid}/power_balance").json()
    assert loc[0]["loc_code"] == "病院MR" and loc[0]["mon"] == "3"
    loc[0]["mon"] = "4"
    assert client.put(f"/masters/{nid}/location_set",
                      json={"locations": loc, "power_balance": pb}).status_code == 200
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, nid, dest_dir=tmp)
        path = os.path.join(tmp, "勤務場所マスタ_確定版.csv")
        rows = _read_csv(path)
        assert rows[1][0] == "病院MR" and rows[1][3] == "4"
        locs = LocationLoader(path).load()
        hosp = next(l for l in locs if l.code == "病院MR")
        assert hosp.required_count[0] == 4
        assert PowerBalanceLoader(path).load()  # power-balance section still parses


def test_change_special_rule_reflected_and_parses(client, conn):
    from shift_scheduler.src.loaders.rule_loader import RuleLoader
    nid = _clone(client)
    sr = client.get(f"/masters/{nid}/special_rules").json()
    assert sr[0]["rule_id"] == "SR-01"
    sr[0]["required_count"] = "3"
    assert client.put(f"/masters/{nid}/special_rules", json=sr).status_code == 200
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, nid, dest_dir=tmp)
        path = os.path.join(tmp, "特殊配置ルール_確定版.csv")
        rows = _read_csv(path)
        sr01 = next(r for r in rows if r and r[0] == "SR-01")
        assert sr01[4] == "3"
        rules = RuleLoader(path).load()
        r01 = next(r for r in rules if r.rule_id == "SR-01")
        assert r01.required_count == 3


def test_change_training_reflected_and_parses(client, conn):
    from shift_scheduler.src.loaders.staff_loader import StaffLoader
    from shift_scheduler.src.loaders.data_loader import DataLoader
    nid = _clone(client)
    tr = client.get(f"/masters/{nid}/training").json()
    assert tr[0]["modality"] == "病院MR"
    tr[0]["trainee_text"] = "平野裕, 星"  # valid subset that still resolves
    assert client.put(f"/masters/{nid}/training", json=tr).status_code == 200
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, nid, dest_dir=tmp)
        path = os.path.join(tmp, "業務拡大マスタ_確定版.csv")
        rows = _read_csv(path)
        assert rows[1][2] == "平野裕, 星"
        staff = StaffLoader(os.path.join(tmp, "技師マスタ_確定版.csv")).load()
        rules = DataLoader(tmp).load_training_rules(staff)
        assert any(r["modality"] == "病院MR" for r in rules)


def test_change_night_quota_reflected_and_parses(client, conn):
    from shift_scheduler.src.loaders.staff_loader import StaffLoader
    from shift_scheduler.src.loaders.data_loader import DataLoader
    nid = _clone(client)
    nq = client.get(f"/masters/{nid}/night_quota").json()
    target_id = nq[0]["tech_id"]
    old = nq[0]["count"]
    nq[0]["count"] = old + 5
    assert client.put(f"/masters/{nid}/night_quota?year_month=2026-07",
                      json=nq).status_code == 200
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, nid, dest_dir=tmp)
        path = os.path.join(tmp, "夜勤回数_確定版.csv")
        rows = _read_csv(path)
        assert rows[2][1] == str(old + 5)               # first staff row reflects edit
        total = next(r for r in rows if r and r[0] == "合計")
        assert int(total[1]) == 93 - old + (old + 5)    # 合計 regenerated
        assert any(r and r[0] == "必要当直者数" for r in rows)  # footer regenerated
        name_to_id = {s.name: s.id for s in
                      StaffLoader(os.path.join(tmp, "技師マスタ_確定版.csv")).load()}
        counts = DataLoader(tmp).load_night_counts("2026-07", name_to_id)
        assert counts.get(target_id) == old + 5


def test_change_night_override_reflected_and_parses(client, conn):
    from shift_scheduler.src.loaders.data_loader import DataLoader
    import shutil
    nid = _clone(client)
    no = client.get(f"/masters/{nid}/night_overrides").json()
    idx = next(i for i, r in enumerate(no) if r["sname"] == "石川　和弥")
    no[idx]["night_cath"] = "TRUE"
    assert client.put(f"/masters/{nid}/night_overrides", json=no).status_code == 200
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(conn, nid, dest_dir=tmp)
        path = os.path.join(tmp, "夜勤スキル一覧.csv")
        rows = _read_csv(path)
        row = next(r for r in rows if r and r[0] == "石川　和弥")
        assert row[2] == "TRUE"
        # parses via its loader (DataLoader.load_all applies the override)
        shutil.copyfile(os.path.join(DATA, "予定申請.csv"),
                        os.path.join(tmp, "予定申請_202607.csv"))
        staff_list, *_ = DataLoader(tmp).load_all("2026-07")
        ishikawa = next(s for s in staff_list if s.name == "石川　和弥")
        assert ishikawa.night_cath is True


# --- validation (422) -------------------------------------------------------

def test_location_set_rejects_bad_active(client):
    loc = client.get("/masters/1/location").json()
    loc[0]["active"] = "Y"
    r = client.put("/masters/1/location_set",
                   json={"locations": loc, "power_balance": []})
    assert r.status_code == 422
    assert r.json()["detail"]["field"] == "active"


def test_location_set_rejects_negative_weekday(client):
    loc = client.get("/masters/1/location").json()
    loc[0]["mon"] = "-1"
    r = client.put("/masters/1/location_set",
                   json={"locations": loc, "power_balance": []})
    assert r.status_code == 422


def test_location_set_rejects_unknown_pb_reference(client):
    loc = client.get("/masters/1/location").json()
    pb = [{"loc_code": "存在しない場所", "min_rank": "A",
           "min_count": "1", "cd_cap": "", "d_solo_ban": ""}]
    r = client.put("/masters/1/location_set",
                   json={"locations": loc, "power_balance": pb})
    assert r.status_code == 422
    assert r.json()["detail"]["field"] == "loc_code"


def test_special_rules_rejects_bad_rule_id(client):
    sr = client.get("/masters/1/special_rules").json()
    sr[0]["rule_id"] = "XX-99"
    r = client.put("/masters/1/special_rules", json=sr)
    assert r.status_code == 422
    assert r.json()["detail"]["field"] == "rule_id"


def test_special_rules_advisory_warns_not_rejects(client):
    sr = client.get("/masters/1/special_rules").json()
    sr[0]["rank_cond"] = "D同士禁止"  # documented-but-unenforced -> advisory only
    r = client.put("/masters/1/special_rules", json=sr)
    assert r.status_code == 200
    assert r.json()["warnings"]


def test_training_rejects_unresolved_names(client):
    tr = client.get("/masters/1/training").json()
    tr[0]["trainee_text"] = "幽霊太郎"
    r = client.put("/masters/1/training", json=tr)
    assert r.status_code == 422
    assert "幽霊太郎" in str(r.json())


def test_training_accepts_rank_a_sentinel(client):
    tr = client.get("/masters/1/training").json()
    # every instructor is the ランクA保持者 sentinel in seed data -> must pass
    assert all("ランクA保持者" in row["instructor_text"] for row in tr)
    r = client.put("/masters/1/training", json=tr)
    assert r.status_code == 200


def test_night_overrides_rejects_bad_state(client):
    no = client.get("/masters/1/night_overrides").json()
    idx = next(i for i, r in enumerate(no) if r["sname"] == "石川　和弥")
    no[idx]["night_mr"] = "MAYBE"
    r = client.put("/masters/1/night_overrides", json=no)
    assert r.status_code == 422

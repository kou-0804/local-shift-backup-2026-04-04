"""P4c-3: tested Python backup (sqlite online .backup + archive dump)."""
import hashlib
import json
from types import SimpleNamespace


def _seed_confirmed(db_path):
    from webapp.api.db import connect, init_db
    from webapp.api.archive import service
    from webapp.api.rosters import freeze_roster
    from shift_scheduler.src.models.schedule_result import ScheduleResult

    conn = connect(db_path)
    init_db(conn)
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
    service.confirm_roster(conn, rid, user_id="admin")
    return conn  # kept open: backup must work while the server is running


def test_backup_copies_db_and_dumps_archives(tmp_path):
    src = tmp_path / "shift.db"
    conn = _seed_confirmed(str(src))
    try:
        target = tmp_path / "backup"
        from deploy.backup import run_backup
        manifest = run_backup(db_path=str(src), target_dir=str(target))

        assert (target / "shift.db").exists()
        assert any(p.suffix == ".xlsx" for p in target.iterdir())
        assert manifest["db_bytes"] > 0 and manifest["archive_count"] >= 1

        # The dumped xlsx must match the checksum the archive recorded.
        m = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert m["archive_count"] == len(m["archives"]) >= 1
        for a in m["archives"]:
            data = (target / a["file"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == a["checksum"]
    finally:
        conn.close()


def test_backup_db_is_a_valid_sqlite_copy(tmp_path):
    import sqlite3
    src = tmp_path / "shift.db"
    conn = _seed_confirmed(str(src))
    try:
        target = tmp_path / "backup"
        from deploy.backup import run_backup
        run_backup(db_path=str(src), target_dir=str(target))
        # The online-backup copy is openable and carries the confirmed roster.
        c2 = sqlite3.connect(str(target / "shift.db"))
        n = c2.execute("SELECT COUNT(*) FROM archives").fetchone()[0]
        c2.close()
        assert n >= 1
    finally:
        conn.close()

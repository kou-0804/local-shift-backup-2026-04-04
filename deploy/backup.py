"""Tested backup: SQLite online .backup + per-archive xlsx dump + manifest.

``run_backup`` writes ``shift.db`` (a consistent online-backup copy, safe even
while uvicorn holds the DB open on Windows), one ``{year}-{month:02d}_勤務表.xlsx``
per archive, and a ``manifest.json`` (db size + per-archive SHA-256) DIRECTLY
into ``target_dir``. The CLI/.bat supplies a timestamped target dir so daily runs
do not overwrite each other.

Run: ``python deploy/backup.py --target D:\\backup\\shift`` (reads SHIFT_DB_PATH).
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime


def run_backup(db_path: str, target_dir: str) -> dict:
    os.makedirs(target_dir, exist_ok=True)

    # 1) Consistent DB copy via the SQLite online-backup API (works while the
    #    server is running / the file is locked — important on Windows).
    db_dest = os.path.join(target_dir, "shift.db")
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(db_dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    db_bytes = os.path.getsize(db_dest)

    # 2) Dump each archived month's xlsx as a loose file (human-recoverable).
    reader = sqlite3.connect(db_path)
    reader.row_factory = sqlite3.Row
    archives = []
    try:
        rows = reader.execute(
            "SELECT id, year, month, xlsx_bytes, checksum FROM archives "
            "ORDER BY year, month, id"
        ).fetchall()
    finally:
        reader.close()
    for r in rows:
        fname = f"{r['year']}-{r['month']:02d}_勤務表.xlsx"
        with open(os.path.join(target_dir, fname), "wb") as fh:
            fh.write(r["xlsx_bytes"])
        archives.append({"id": r["id"], "year": r["year"], "month": r["month"],
                         "checksum": r["checksum"], "file": fname})

    # 3) Manifest for verification (IT can diff checksums against the live DB).
    manifest = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source_db": os.path.abspath(db_path),
        "db_file": "shift.db",
        "db_bytes": db_bytes,
        "archive_count": len(archives),
        "archives": archives,
    }
    with open(os.path.join(target_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup the shift DB + archives.")
    parser.add_argument("--db", default=os.environ.get("SHIFT_DB_PATH", "webapp_data/shift.db"))
    parser.add_argument("--target", default=None,
                        help="Backup destination dir (default: backup/<timestamp>).")
    args = parser.parse_args()
    target = args.target
    if not target:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")  # Windows-safe (no colons)
        target = os.path.join("backup", ts)
    manifest = run_backup(db_path=args.db, target_dir=target)
    print(f"backup ok: {manifest['archive_count']} archive(s), "
          f"{manifest['db_bytes']} db bytes -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

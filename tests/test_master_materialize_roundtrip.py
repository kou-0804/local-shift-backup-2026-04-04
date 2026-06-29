# tests/test_master_materialize_roundtrip.py
import os
import sqlite3
import tempfile

from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters.materialize import materialize_masters

DATA = "shift_scheduler/data"
MASTER_FILES = [
    "技師マスタ_確定版.csv", "スキルマスタ_確定版.csv", "公休数マスタ_確定版.csv",
    "勤務場所マスタ_確定版.csv", "特殊配置ルール_確定版.csv", "業務拡大マスタ_確定版.csv",
    "夜勤回数_確定版.csv", "夜勤スキル一覧.csv",
]


def _mem():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_master_db(c)
    return c


def test_materialize_is_byte_identical_to_source():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(c, msid, dest_dir=tmp)
        for fn in MASTER_FILES:
            got = open(os.path.join(tmp, fn), "rb").read()
            want = open(os.path.join(DATA, fn), "rb").read()
            assert got == want, f"BYTE MISMATCH in {fn}: {len(got)} vs {len(want)} bytes"


def test_materialize_is_deterministic():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        materialize_masters(c, msid, dest_dir=a)
        materialize_masters(c, msid, dest_dir=b)
        for fn in MASTER_FILES:
            assert open(os.path.join(a, fn), "rb").read() == \
                   open(os.path.join(b, fn), "rb").read()

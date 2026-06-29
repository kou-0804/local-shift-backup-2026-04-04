import json
from types import SimpleNamespace

from shift_scheduler.src.grid_derivation import build_grid
from shift_scheduler.src.loaders.data_loader import DataLoader

P2A1 = json.load(open("tests/golden/2026-06_p2a1.json", encoding="utf-8"))
P2A2 = json.load(open("tests/golden/2026-06_p2a2.json", encoding="utf-8"))
DAY = {int(d): v for d, v in P2A1["day_assignments"].items()}
NIGHT = {int(d): v for d, v in P2A1["night_assignments"].items()}
REQ = {int(d): v for d, v in P2A1["requests"].items()}
OFF = P2A1["expected_off_counts"]
DAIKYU = P2A1["expected_daikyu_counts"]

# Full Staff objects are needed (note -> nuc_tx_ids); load once.
TECHS = DataLoader(data_dir="shift_scheduler/data").load_all("2026-06")[0]


def _grid():
    return build_grid(
        2026, 6, TECHS, DAY, NIGHT, REQ,
        off_counts=OFF, daikyu_counts=DAIKYU, on_call_assignments=None,
    )


def test_rows_cells_match_p2a1_expected_cells():
    grid = _grid()
    by_id = {r["staff_id"]: r for r in grid["rows"]}
    mismatches = []
    for sid, by_day in P2A1["expected_cells"].items():
        row = by_id.get(sid)
        assert row is not None, f"missing row {sid}"
        for d_str, expected in by_day.items():
            got = row["cells"][int(d_str)]
            if got != expected:
                mismatches.append((sid, d_str, expected, got))
    assert not mismatches, f"{len(mismatches)} cell mismatches, first 5: {mismatches[:5]}"


def test_stats_and_has_work_match_p2a2_golden():
    grid = _grid()
    by_id = {r["staff_id"]: r for r in grid["rows"]}
    for sid, expected_stats in P2A2["expected_stats"].items():
        row = by_id[sid]
        assert row["has_work"] == P2A2["expected_has_work"][sid], sid
        if expected_stats is None:
            assert row["stats"] is None, sid
        else:
            assert row["stats"] == expected_stats, sid


def test_stats_columns_and_weekdays_shape():
    grid = _grid()
    assert grid["stats_columns"] == P2A2["stats_columns"]
    assert grid["days_in_month"] == 30
    assert grid["weekdays"][1] in "月火水木金土日"
    # 2026-06-01 is a Monday
    assert grid["weekdays"][1] == "月"


def test_kouho_daikyu_injected_after_counting_overwrites_parsed():
    # 公休/代休 must come from off/daikyu counts, NOT from string parsing.
    grid = _grid()
    for r in grid["rows"]:
        if r["stats"] is not None:
            assert r["stats"]["公休"] == OFF.get(r["staff_id"], 0)
            assert r["stats"]["代休"] == DAIKYU.get(r["staff_id"], 0)


def test_oncall_rows_present_when_supplied():
    techs = [SimpleNamespace(id="T001", name="甲 (海)", status="在籍", note="",
                             night_hb=False),
             SimpleNamespace(id="T002", name="乙", status="在籍", note="",
                             night_hb=False)]
    grid = build_grid(2026, 6, techs, {}, {}, {},
                      on_call_assignments={1: {"第1拘束": "T001", "第2拘束": "T002"}})
    labels = [r["label"] for r in grid["oncall_rows"]]
    assert labels == ["第1拘束", "第2拘束"]
    # parens/spaces stripped per excel_generator.py:210-232
    assert grid["oncall_rows"][0]["cells"][1] == "甲海"


def test_cells_fast_path_restricts_to_affected_staff():
    grid = build_grid(2026, 6, TECHS, DAY, NIGHT, REQ,
                      off_counts=OFF, daikyu_counts=DAIKYU,
                      cells={(P2A1["active_staff_ids"][0], 5)})
    ids = {r["staff_id"] for r in grid["rows"]}
    assert ids == {P2A1["active_staff_ids"][0]}
    # the row is still fully derived so its stats are correct
    assert len(grid["rows"][0]["cells"]) == 30

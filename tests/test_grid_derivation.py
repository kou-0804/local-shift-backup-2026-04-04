import json
from shift_scheduler.src.grid_derivation import derive_cell_text, cell_fill, DISPLAY_ONLY_FIXED

with open("tests/golden/2026-06_p2a1.json", encoding="utf-8") as f:
    FIX = json.load(f)

# rebuild int-keyed dicts from the fixture
DAY = {int(d): v for d, v in FIX["day_assignments"].items()}
NIGHT = {int(d): v for d, v in FIX["night_assignments"].items()}
REQ = {int(d): v for d, v in FIX["requests"].items()}
NUC = set(FIX["nuc_tx_ids"])
DAYS = FIX["days_in_month"]


def test_derive_cell_text_matches_golden_for_every_cell():
    mismatches = []
    for sid, by_day in FIX["expected_cells"].items():
        # build_grid applies display-only overrides (e.g. 矢野/T003 の MR) AFTER
        # derive_cell_text. This pure per-cell layer doesn't, so skip those cells.
        override_label = DISPLAY_ONLY_FIXED.get(sid, {}).get("label")
        for d_str, expected in by_day.items():
            if override_label is not None and expected == override_label:
                continue
            d = int(d_str)
            got = derive_cell_text(sid, d, DAY, NIGHT, REQ, NUC)
            if got != expected:
                mismatches.append((sid, d, expected, got))
    assert not mismatches, f"{len(mismatches)} cell mismatches, first 5: {mismatches[:5]}"


def test_cell_fill_known_values():
    assert cell_fill("病CT夜") == "FFFF00"   # night → yellow (substring '夜' tested first)
    assert cell_fill("○") == "FFC0CB"        # 明け → pink
    assert cell_fill("休") == "D3D3D3"        # off → grey

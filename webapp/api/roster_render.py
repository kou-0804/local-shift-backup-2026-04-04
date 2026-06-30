"""Single-source render path for a frozen roster -> Direction-A Excel bytes.

Both ``main.py::get_roster_excel`` (live download) and
``archive/service.py::confirm_roster`` (immutable snapshot) call
``render_roster_excel`` so the two can never drift (spec §6 single-source rule).
The renderer is deterministic, so re-rendering an unchanged roster yields
byte-identical output (asserted by the re-confirm checksum test).

This module deliberately depends only on ``rosters`` (roster_ops) and the
``excel_directiona`` renderer — never on ``main`` — to avoid an import cycle.
"""
from webapp.api import rosters as roster_ops
from shift_scheduler.src.excel_directiona import render_directiona


def format_warnings(rc: dict, month: int) -> list:
    """recompute_stats の構造化警告を検証シート用の日本語文字列へ整形。
    実際の recompute_stats キー（coverage / night_hb_gaps）に合わせる。"""
    out = []
    for u in rc.get("coverage", []):
        day = int(u["date"].split("-")[2])
        out.append(f"{month}月{day}日: [{u['location']}] の配置人数が不足しています "
                   f"(目標: {u['required']}人 / 実際: {u['assigned']}人)")
    for day in rc.get("night_hb_gaps", []):
        out.append(f"{month}月{int(day)}日: "
                   "夜勤メンバーにHB対応可能者がいないため代替処理を行いました")
    return out


def render_roster_excel(conn, rid):
    """Return ``(xlsx_bytes, roster_dict)`` for a frozen roster.

    grid -> recompute_stats(live) -> render_directiona, exactly as the live
    download path. ``roster_dict`` carries year/month/version/status for callers.
    """
    grid, d = roster_ops.build_roster_grid(conn, rid)
    rc = roster_ops.roster_warnings(d)
    xlsx = render_directiona(grid, warnings=format_warnings(rc, d["month"]))
    return xlsx, d

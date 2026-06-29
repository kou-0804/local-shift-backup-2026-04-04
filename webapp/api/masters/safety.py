"""Load-bearing-ID safety gate + advisory warnings.

§3.5 of the spec hardcodes specific staff IDs into CP-SAT ``model.Add`` floors.
If a master edit renames/removes one of these IDs the constraint silently
no-ops (a bad solve, not an error). This gate verifies they all exist BEFORE
generation, so re-numbering fails loudly instead.

Load-bearing IDs (do not edit without updating the scheduler — §3.5):
  T001 病CT専従/連勤免除; T013+T025 月6回ク相互排他; T072 館山専任
  (+ backups T006/T022/T023); T002 第4火曜PET; T022 月曜DX.
"""
LOAD_BEARING_IDS = ["T001", "T013", "T025", "T072", "T002", "T022", "T006", "T023"]

# Locations whose ≥B rank derives night eligibility (data_loader.py:33-47).
_NIGHT_LOCS = {"病院MR", "CLMR", "ア", "心", "HB"}
_RANK_VALUE = {"-": 0, "": 0, "D": 1, "C": 2, "B": 3, "A": 4}
_B_THRESHOLD = _RANK_VALUE["B"]

# rank_cond strings documented in the master but parsed to NONE / not enforced
# by the scheduler (dead branch — spec §3.4 / masters map).
_UNENFORCED_RANK_CONDS = {"D同士禁止", "CD上限", "CD単独禁止"}


class SafetyError(Exception):
    """Raised when generation must be blocked (missing load-bearing ID)."""


def assert_load_bearing_ids(conn, master_set_id: int) -> None:
    """Raise SafetyError naming EVERY missing load-bearing ID; else return None."""
    present = {r["tech_id"] for r in conn.execute(
        "SELECT tech_id FROM ms_staff WHERE master_set_id=?", (master_set_id,))}
    missing = [tid for tid in LOAD_BEARING_IDS if tid not in present]
    if missing:
        raise SafetyError(
            f"生成不可: コード固定の技師ID {missing} が技師マスタに存在しません。"
            "これらはスケジューラの §3.5 ハードコード制約に対応します。"
            "IDの振り直し・削除を元に戻してください（§3.5 参照）。")


def night_eligibility_warnings(conn, master_set_id, tech_id, loc_code,
                               old_rank, new_rank):
    """Advisory: a rank edit that crosses the ≥B night-eligibility threshold for a
    night-deriving location changes whether this tech can take MR/Cath/Angio/HB
    night shifts. Non-blocking — returned in the CRUD response."""
    if loc_code not in _NIGHT_LOCS:
        return []
    old_ok = _RANK_VALUE.get((old_rank or "").strip(), 0) >= _B_THRESHOLD
    new_ok = _RANK_VALUE.get((new_rank or "").strip(), 0) >= _B_THRESHOLD
    if old_ok == new_ok:
        return []
    direction = "付与" if new_ok else "喪失"
    return [f"技師 {tech_id} の {loc_code} ランク変更 ({old_rank}→{new_rank}) により"
            f"夜勤対応資格 (MR/心カテ/アンギオ/HB) が{direction}されます。確認してください。"]


def special_rule_warnings(rank_cond: str):
    """Advisory: these rank_cond strings are documented but parsed to NONE and
    NOT enforced by the scheduler (dead branch). Non-blocking."""
    if (rank_cond or "").strip() in _UNENFORCED_RANK_CONDS:
        return [f"ランク条件 '{rank_cond}' はマスタに記載されていますが、"
                "スケジューラでは現在未適用（未実装）です。配置には反映されません。"]
    return []

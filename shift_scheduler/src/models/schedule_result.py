from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ScheduleResult:
    """run_schedule() の構造化結果。workbook_bytes 以外は JSON 化可能。"""
    year: int
    month: int
    staff: List[Dict[str, str]]                       # [{"id","name"}], 技師マスタ順
    day_assignments: Dict[int, Dict[str, List[str]]]  # {day: {loc_code: [staff_id]}}
    night_assignments: Dict[int, List[str]]           # {day: [staff_id]}
    requests: Dict[int, Dict[str, str]]               # {day: {staff_id: symbol}}
    on_call_assignments: Dict                          # {day: {第1拘束/第2拘束: staff_id}}
    daikyu_counts: Dict[str, int]
    off_counts: Dict[str, int]
    validation_errors: List[str]
    workbook_bytes: bytes = b""
    daily_location_needs: dict = field(default_factory=dict)  # {date or day: {loc_code: required}}
    # P2b partial-lock re-solve: surfaced off the object directly (NEVER in as_dict()
    # — they must stay excluded like daily_location_needs/workbook_bytes so the parity
    # golden gate is unaffected and an empty lock set leaks nothing).
    unlockable_locks: list = field(default_factory=list)  # forces with no var (reported)
    lock_conflicts: list = field(default_factory=list)    # assumption-infeasibility cells

    def as_dict(self) -> dict:
        """決定的・JSON 化可能な辞書（workbook_bytes は除外、リストはソート）。"""
        return {
            "year": self.year,
            "month": self.month,
            "staff": self.staff,
            "day_assignments": {
                str(d): {loc: sorted(ids) for loc, ids in locs.items()}
                for d, locs in self.day_assignments.items()
            },
            "night_assignments": {
                str(d): sorted(ids) for d, ids in self.night_assignments.items()
            },
            "requests": {
                str(d): dict(sm) for d, sm in self.requests.items()
            },
            "on_call_assignments": {
                str(d): v for d, v in self.on_call_assignments.items()
            },
            "daikyu_counts": dict(self.daikyu_counts),
            "off_counts": dict(self.off_counts),
            "validation_errors": list(self.validation_errors),
        }

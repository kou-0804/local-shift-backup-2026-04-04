from dataclasses import dataclass
from datetime import date
from .skill import SkillRank

@dataclass
class NightAssignment:
    """夜勤割当結果"""
    date: date
    staff_id: str
    role: str  # 'MR', 'アンギオ', '心カテ'

@dataclass
class DayAssignment:
    """日勤配置結果"""
    date: date
    location_code: str
    staff_id: str
    rank: SkillRank

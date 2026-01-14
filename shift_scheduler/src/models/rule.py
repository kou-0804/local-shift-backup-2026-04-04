from dataclasses import dataclass
from typing import Optional
from .skill import SkillRank

@dataclass
class SpecialRule:
    """特殊配置ルール"""
    rule_id: str
    location_code: str
    target_weekday: Optional[int]  # 0=Mon, ... 6=Sun, None=All
    target_week: Optional[int]     # 1=1st week, ... None=All
    required_count: int
    rank_condition: Optional[SkillRank]
    rank_count: int
    source_location: Optional[str]
    source_rank: Optional[SkillRank]
    note: str = ""

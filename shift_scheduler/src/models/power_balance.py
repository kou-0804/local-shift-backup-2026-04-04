from dataclasses import dataclass
from typing import Optional
from .skill import SkillRank

@dataclass
class PowerBalance:
    """パワーバランス設定"""
    location_code: str
    min_rank: Optional[SkillRank] = None
    min_count: Optional[int] = None
    cd_cap: Optional[int] = None
    d_solo_ban: bool = False
    
    # Validation helper maybe?

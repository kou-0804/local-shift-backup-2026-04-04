from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class Location:
    """勤務場所"""
    code: str
    name: str
    category: str
    required_count: Dict[int, int]  # {weekday: count}
    gender_constraint: Optional[str]
    display_order: int
    is_active: bool
    
    def get_required_count(self, weekday: int) -> int:
        return self.required_count.get(weekday, 0)

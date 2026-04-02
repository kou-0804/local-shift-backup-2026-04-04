from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class Gender(Enum):
    """性別"""
    MALE = '男'
    FEMALE = '女'
    
    @classmethod
    def from_string(cls, s: str) -> 'Gender':
        if s == '男':
            return cls.MALE
        elif s == '女':
            return cls.FEMALE
        raise ValueError(f"Unknown gender: {s}")

@dataclass
class Staff:
    """技師"""
    id: str
    name: str
    gender: Gender
    experience_years: int
    can_night_shift: bool
    status: str
    note: str = ""
    can_oncall: bool = True
    
    # 夜勤スキル（導出値）
    night_mr: bool = False
    night_angio: bool = False
    night_cath: bool = False
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if not isinstance(other, Staff):
            return False
        return self.id == other.id

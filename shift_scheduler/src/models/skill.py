from enum import Enum

class SkillRank(Enum):
    """スキルランク"""
    A = 4  # エキスパート
    B = 3  # 一人前
    C = 2  # 標準
    D = 1  # 新人
    NONE = 0  # スキルなし
    
    @classmethod
    def from_string(cls, s: str) -> 'SkillRank':
        mapping = {'A': cls.A, 'B': cls.B, 'C': cls.C, 'D': cls.D, '-': cls.NONE}
        # Strip whitespace just in case
        return mapping.get(s.strip() if s else '', cls.NONE)
    
    def __ge__(self, other):
        if not isinstance(other, SkillRank):
            return NotImplemented
        return self.value >= other.value
        
    def __gt__(self, other):
        if not isinstance(other, SkillRank):
            return NotImplemented
        return self.value > other.value

    def __le__(self, other):
        if not isinstance(other, SkillRank):
            return NotImplemented
        return self.value <= other.value
        
    def __lt__(self, other):
        if not isinstance(other, SkillRank):
            return NotImplemented
        return self.value < other.value

    def __str__(self):
        reverse_mapping = {v: k for k, v in {'A': 4, 'B': 3, 'C': 2, 'D': 1, '-': 0}.items()}
        return reverse_mapping.get(self.value, '-')

from dataclasses import dataclass

@dataclass
class SkillEntry:
    """スキルエントリ"""
    staff_id: str
    location_code: str
    rank: SkillRank

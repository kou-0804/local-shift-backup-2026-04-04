from dataclasses import dataclass
from datetime import date

@dataclass
class Request:
    """予定申請"""
    staff_id: str
    date: date
    symbol: str
    note: str = ""

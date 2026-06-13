import pandas as pd
from typing import Dict, List
from ..models.skill import SkillRank, SkillEntry

class SkillLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self, staff_ids: List[str]) -> Dict[str, Dict[str, SkillRank]]:
        """
        Returns a dict: {staff_id: {location_code: SkillRank}}
        """
        df = pd.read_csv(self.file_path, encoding='utf-8-sig')
        skills = {}
        
        # Valid location columns are those not in the initial metadata columns.
        # 技師ID および氏名・備考などの非スキル列はスキル場所として扱わない。
        # （目視確認用に氏名列を一時追加してもスケジューリングに影響しないようにする）
        META_COLS = {'技師ID', '氏名', '名前', '備考', 'メモ', 'note'}
        location_codes = [c for c in df.columns if c not in META_COLS]

        for _, row in df.iterrows():
            staff_id = str(row['技師ID'])
            if staff_id not in staff_ids:
                # Only load skills for known staff (optional check)
                pass
                
            staff_skills = {}
            for loc_code in location_codes:
                rank_str = str(row[loc_code])
                staff_skills[loc_code] = SkillRank.from_string(rank_str)
            
            skills[staff_id] = staff_skills
            
        return skills

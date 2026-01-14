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
        
        # Valid location columns are those not in the initial metadata columns
        # In the CSV: 技師ID, 病院MR, ...
        # So all columns except 技師ID are location codes
        location_codes = [c for c in df.columns if c != '技師ID']

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

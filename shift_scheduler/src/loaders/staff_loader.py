import pandas as pd
from typing import List
from ..models.staff import Staff, Gender

class StaffLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> List[Staff]:
        # 'utf-8-sig' handles the BOM
        df = pd.read_csv(self.file_path, encoding='utf-8-sig')
        staff_list = []
        
        for _, row in df.iterrows():
            try:
                # Handle boolean conversion for night shift capability
                can_night_shift = str(row['夜勤可否']).strip() == '○'
                
                can_oncall = True
                if '拘束可否' in df.columns:
                    val = str(row['拘束可否']).strip()
                    if val == '×':
                        can_oncall = False
                
                staff = Staff(
                    id=str(row['技師ID']),
                    name=str(row['氏名']),
                    gender=Gender.from_string(str(row['性別'])),
                    experience_years=int(row['経験年数']),
                    can_night_shift=can_night_shift,
                    status=str(row['在籍状況']),
                    note=str(row['備考']) if pd.notna(row['備考']) else "",
                    can_oncall=can_oncall
                )
                staff_list.append(staff)
            except Exception as e:
                print(f"Error loading staff row {row}: {e}")
                
        return staff_list

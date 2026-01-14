import pandas as pd
from typing import List, Dict
from ..models.location import Location

class LocationLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> List[Location]:
        df = pd.read_csv(self.file_path, encoding='utf-8-sig')
        locations = []
        
        for _, row in df.iterrows():
            try:
                # Stop if we hit the power balance section or empty line
                code = str(row['場所コード'])
                if pd.isna(row['場所コード']) or code.startswith('---') or code == 'nan':
                    continue
                    
                # Ensure required columns are integers
                if pd.isna(row['月']):
                    continue
                    
                # Parse required counts: 月, 火, ...
                required_count = {
                    0: int(row['月']),
                    1: int(row['火']),
                    2: int(row['水']),
                    3: int(row['木']),
                    4: int(row['金']),
                    5: int(row['土']),
                    6: int(row['日'])
                }
                
                gender_constraint = None
                if str(row['性別制約']) == '女性のみ':
                    gender_constraint = 'female'
                elif str(row['性別制約']) == '男性のみ': # Just in case
                    gender_constraint = 'male'
                    
                location = Location(
                    code=code,
                    name=str(row['場所名']),
                    category=str(row['カテゴリ']),
                    required_count=required_count,
                    gender_constraint=gender_constraint,
                    display_order=int(row['表示順']),
                    is_active=str(row['有効']) == '○'
                )
                locations.append(location)
            except Exception as e:
                # Silently skip rows that don't match the location structure (e.g. Power Balance rows)
                # print(f"Skipping row: {e}")
                pass
                
        return locations

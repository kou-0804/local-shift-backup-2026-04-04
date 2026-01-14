import pandas as pd
from typing import List
from ..models.power_balance import PowerBalance
from ..models.skill import SkillRank

class PowerBalanceLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> List[PowerBalance]:
        rules = []
        try:
            # We need to find where the Power Balance section starts
            # Since Pandas read_csv with skiprows might be tricky if we don't know line number exactly,
            # let's read file lines first to find the header.
            with open(self.file_path, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
            
            start_line = -1
            for i, line in enumerate(lines):
                if '---パワーバランス設定---' in line:
                    start_line = i
                    break
            
            if start_line == -1:
                return []
                
            # The header is usually 2 lines after start_line?
            # Line 21: ---...
            # Line 22: ,,,
            # Line 23: Header
            
            # Let's look for the header "場所コード,最低ランク"
            header_line = -1
            for i in range(start_line, len(lines)):
                if '場所コード' in lines[i] and '最低ランク' in lines[i]:
                    header_line = i
                    break
            
            if header_line == -1:
                return []
                
            # Now read csv from header_line
            # We can use pd.read_csv with skiprows
            df = pd.read_csv(self.file_path, encoding='utf-8-sig', skiprows=header_line)
            
            for _, row in df.iterrows():
                try:
                    code = str(row['場所コード'])
                    if pd.isna(code) or code == 'nan':
                        continue
                        
                    # Parse Min Rank
                    min_rank_str = str(row['最低ランク']) if not pd.isna(row['最低ランク']) else None
                    min_rank = SkillRank.from_string(min_rank_str) if min_rank_str else None
                    
                    # Parse Min Count
                    min_count = int(row['最低人数']) if not pd.isna(row['最低人数']) else None
                    
                    # Parse CD Cap
                    cd_cap = int(row['CD上限']) if not pd.isna(row['CD上限']) else None
                    
                    # Parse D Ban
                    d_ban_str = str(row['D単独禁止']) if not pd.isna(row['D単独禁止']) else ''
                    d_ban = (d_ban_str == '○')
                    
                    rule = PowerBalance(
                        location_code=code,
                        min_rank=min_rank,
                        min_count=min_count,
                        cd_cap=cd_cap,
                        d_solo_ban=d_ban
                    )
                    rules.append(rule)
                    
                except Exception as e:
                    # skip invalid rows
                    continue
                    
        except Exception as e:
            print(f"Error loading power balance rules: {e}")
            return []

        return rules

import pandas as pd
from typing import List, Optional
from ..models.rule import SpecialRule
from ..models.skill import SkillRank

class RuleLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> List[SpecialRule]:
        df = pd.read_csv(self.file_path, encoding='utf-8-sig')
        rules = []
        
        weekday_map = {'月': 0, '火': 1, '水': 2, '木': 3, '金': 4, '土': 5, '日': 6}
        
        for _, row in df.iterrows():
            try:
                rule_id = str(row['ルールID'])
                if pd.isna(row['ルールID']) or rule_id.startswith('---') or rule_id == 'nan':
                    continue
                    
                # Skip legend rows (RuleID often contains explanations in legends)
                if not rule_id.startswith('SR-'):
                    continue

                # Parse weekday
                weekday_str = str(row['対象曜日'])
                target_weekdays = []
                
                if weekday_str == '水金':
                    target_weekdays = [2, 4] # Wed, Fri
                elif weekday_str in weekday_map:
                    target_weekdays = [weekday_map[weekday_str]]
                elif weekday_str == '-':
                    target_weekdays = [None] # All days
                else:
                    # Treat unknown/empty as None (All Days) or ignore?
                    # Previous logic was implicit None. Keep as None but warn if needed.
                    target_weekdays = [None]

                # Parse week
                week_str = str(row['対象週'])
                target_week = int(week_str) if week_str.isdigit() else None
                
                # Parse Rank
                rank_cond = None
                rank_str = str(row['ランク条件'])
                if rank_str and rank_str != '-':
                    rank_cond = SkillRank.from_string(rank_str)
                    
                rank_count = 0
                rank_cnt_str = str(row['ランク人数'])
                if rank_cnt_str.isdigit():
                    rank_count = int(rank_cnt_str)
                    
                source_loc = None
                src_loc_str = str(row['選出元場所'])
                if src_loc_str and src_loc_str != '-':
                    source_loc = src_loc_str
                    
                source_rank = None
                src_rank_str = str(row['選出元ランク'])
                if src_rank_str and src_rank_str != '-':
                    source_rank = SkillRank.from_string(src_rank_str)

                for wd in target_weekdays:
                    rule = SpecialRule(
                        rule_id=str(row['ルールID']),
                        location_code=str(row['場所コード']),
                        target_weekday=wd,
                        target_week=target_week,
                        required_count=int(row['必要人数']),
                        rank_condition=rank_cond,
                        rank_count=rank_count,
                        source_location=source_loc,
                        source_rank=source_rank,
                        note=str(row['備考']) if pd.notna(row['備考']) else ""
                    )
                    rules.append(rule)
            except Exception as e:
                print(f"Error loading rule row {row}: {e}")
                
        return rules

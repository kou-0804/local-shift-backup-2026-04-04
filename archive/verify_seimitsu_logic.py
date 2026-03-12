
import sys
import os
import csv
from datetime import date
from enum import Enum

# Add project root match Main
sys.path.append('/Users/kohei/Desktop/local-shift ver1')

from shift_scheduler.src.models.staff import Staff, Gender
from shift_scheduler.src.models.skill import SkillRank
from shift_scheduler.src.models.location import Location
from shift_scheduler.src.models.rule import SpecialRule
from shift_scheduler.src.models.power_balance import PowerBalance

def load_staff_manual(path):
    staff_list = []
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Debug print headers if needed
                # print(row.keys())
                s = Staff(
                    id=row.get('技師ID'),
                    name=row.get('氏名'),
                    gender=Gender.from_string(row.get('性別')),
                    experience_years=int(row.get('経験年数', 0)),
                    can_night_shift=(row.get('夜勤可否') == '○'),
                    status=row.get('在籍状況'),
                    note=row.get('備考', '')
                )
                if not s.id: continue # Skip empty rows
                staff_list.append(s)
            except Exception as e:
                print(f"Skipping staff row: {row} - {e}")
    return staff_list

def load_skills_manual(path, staff_list):
    skills = {}
    with open(path, 'r', encoding='utf-8-sig') as f: # Use utf-8-sig for BOM
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get('技師ID')
            if not sid: continue
            s_skills = {}
            for k, v in row.items():
                if k == '技師ID': continue
                s_skills[k] = SkillRank.from_string(v)
            skills[sid] = s_skills
    return skills

def load_pb_rules_manual(path):
    # PB rules are in Location file, checking second section logic is complex without pandas/loader
    # I will just manually create the relevant PB Rule for '精' based on what I saw in tool output
    # 場所コード,最低ランク,最低人数,CD上限,D単独禁止
    # 精,B,1,,×
    return [PowerBalance(location_code='精', min_rank=SkillRank.B, min_count=1, cd_cap=None, d_solo_ban=False)]

def verify_seimitsu():
    print("Verifying Seimitsu (精) logic (Manual Load)...")
    
    data_dir = '/Users/kohei/Desktop/local-shift ver1/shift_scheduler/data'
    
    # 1. Load Staff
    staff_path = os.path.join(data_dir, "技師マスタ_確定版.csv")
    staff_list = load_staff_manual(staff_path)
    print(f"Loaded {len(staff_list)} staff.")
    
    # 2. Load Skills
    skill_path = os.path.join(data_dir, "スキルマスタ_確定版.csv")
    skills = load_skills_manual(skill_path, staff_list)
    
    # 3. PB Rules (Mocked based on known file content)
    pb_rules = load_pb_rules_manual(None)
    
    # 4. Target Date: 2026-01-05 (Monday)
    target_date = date(2026, 1, 5)
    print(f"\nTarget Date: {target_date} ({target_date.strftime('%A')})")
    
    # 5. Filter Available Staff for '精'
    l_code = '精'
    candidates = []
    
    weekday = target_date.weekday() # 0 = Mon
    
    print(f"Scanning candidates for location '{l_code}' on Weekday {weekday}...")
    
    for s in staff_list:
        if s.status != '在籍': continue
        
        s_skills = skills.get(s.id, {})
        rank = s_skills.get(l_code, SkillRank.NONE)
        
        # Logic Replication
        if rank == SkillRank.NONE:
            continue
            
        # Logic from day_scheduler.py
        if l_code == '精':
            # Weekday 2=Wed, 4=Fri.
            if weekday in [2, 4]:
                if rank < SkillRank.A: continue
            else:
                # User Request: Allow B, C, D. Exclude A.
                if rank == SkillRank.A: continue
                if rank == SkillRank.NONE: continue
                
        candidates.append((s, rank))
        
    print(f"\nFound {len(candidates)} candidates for '精' (Monday):")
    
    # Verify PB Override
    pb_rule = next((pb for pb in pb_rules if pb.location_code == '精'), None)
    
    qualified_final = []
    
    if pb_rule and pb_rule.min_rank and pb_rule.min_count:
         print(f"\nPower Balance Rule for '精': MinRank={pb_rule.min_rank}, MinCount={pb_rule.min_count}")
         
         skip_min_rank = False
         if l_code == '精':
              if weekday in [0, 1, 3, 5]: # Mon, Tue, Thu, Sat
                  skip_min_rank = True
         print(f"  -> Skip Min Rank logic applied? {skip_min_rank}")
         
         for s, rank in candidates:
             if skip_min_rank:
                 qualified_final.append(s)
             else:
                 if rank >= pb_rule.min_rank:
                     qualified_final.append(s)
    else:
        qualified_final = [s for s, r in candidates]

    print(f"\nFinal Qualified Staff Count (after PB Logic): {len(qualified_final)}")
    
    # Print breakdown
    rank_counts = {'A':0, 'B':0, 'C':0, 'D':0, 'NONE':0}
    for s in qualified_final:
        r = skills.get(s.id, {}).get('精', SkillRank.NONE)
        r_str = str(r) # 'A', 'B'...
        rank_counts[r_str] = rank_counts.get(r_str, 0) + 1
        
    print("Rank Breakdown of Final Qualified:")
    print(rank_counts)

if __name__ == "__main__":
    verify_seimitsu()

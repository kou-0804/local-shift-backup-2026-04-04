import sys
import os
from datetime import date, timedelta
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.loaders.staff_loader import StaffLoader
from shift_scheduler.src.loaders.skill_loader import SkillLoader
from shift_scheduler.src.loaders.location_loader import LocationLoader
from shift_scheduler.src.loaders.rule_loader import RuleLoader
from shift_scheduler.src.loaders.power_balance_loader import PowerBalanceLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.models.skill import SkillRank

def verify():
    data_dir = 'shift_scheduler/data'
    loader = DataLoader(data_dir)
    staff_list = StaffLoader(os.path.join(data_dir, "技師マスタ_確定版.csv")).load()
    skills = SkillLoader(os.path.join(data_dir, "スキルマスタ_確定版.csv")).load([s.id for s in staff_list])
    locations = LocationLoader(os.path.join(data_dir, "勤務場所マスタ_確定版.csv")).load()
    rules = RuleLoader(os.path.join(data_dir, "特殊配置ルール_確定版.csv")).load()
    pb_rules = PowerBalanceLoader(os.path.join(data_dir, "勤務場所マスタ_確定版.csv")).load()
    training_rules = loader.load_training_rules(staff_list)
    
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2026, 4, training_rules)
    
    # Try a specific day: 2026-04-06 (Monday)
    d = date(2026, 4, 6)
    req_map = {}
    night_map = {}
    
    # Check if instructors exist for MR
    mr_instructors = [s.id for s in staff_list if skills.get(s.id, {}).get('病院MR', SkillRank.NONE) == SkillRank.A]
    print(f"MR Instructors available: {mr_instructors}")
    
    day_assignments, info = scheduler._schedule_one_day(d, req_map, night_map, {}, {s.id: {} for s in staff_list}, {s.id: 0 for s in staff_list})
    
    print(f"--- Assignments for {d} ---")
    for a in day_assignments:
        if a.location_code.startswith('(') or a.location_code in ['病院MR', 'CLMR', 'ア', '心', 'HB', 'DR']:
            print(f"  {a.location_code}: {a.staff_id} (Rank: {skills.get(a.staff_id, {}).get(a.location_code, 'N/A') if not a.location_code.startswith('(') else 'Trainee'})")

if __name__ == '__main__':
    verify()

import sys
import os
from datetime import date, timedelta
import pandas as pd
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.loaders.staff_loader import StaffLoader
from shift_scheduler.src.loaders.skill_loader import SkillLoader
from shift_scheduler.src.loaders.location_loader import LocationLoader
from shift_scheduler.src.loaders.rule_loader import RuleLoader
from shift_scheduler.src.loaders.power_balance_loader import PowerBalanceLoader
from shift_scheduler.src.loaders.request_loader import RequestLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.models.skill import SkillRank

def verify():
    data_dir = 'shift_scheduler/data'
    loader = DataLoader(data_dir)
    
    # Reload components
    staff_path = os.path.join(data_dir, "技師マスタ_確定版.csv")
    staff_list = StaffLoader(staff_path).load()
    staff_ids = [s.id for s in staff_list]
    
    skill_path = os.path.join(data_dir, "スキルマスタ_確定版.csv")
    skills = SkillLoader(skill_path).load(staff_ids)
    
    loc_path = os.path.join(data_dir, "勤務場所マスタ_確定版.csv")
    locations = LocationLoader(loc_path).load()
    
    rule_path = os.path.join(data_dir, "特殊配置ルール_確定版.csv")
    rules = RuleLoader(rule_path).load()
    
    pb_rules = PowerBalanceLoader(loc_path).load()
    
    training_rules = loader.load_training_rules(staff_list)
    
    # Load actual requests matching what main.py does
    name_to_id = {s.name: s.id for s in staff_list}
    request_loader = RequestLoader(data_dir)
    requests = request_loader.load("2026-04", name_to_id=name_to_id)
    # Re-map requests to (staff_id, date) -> symbol
    req_map = {(r.staff_id, r.date): r.symbol for r in requests}
    
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2026, 4, training_rules)
    
    endo_id = 'T066'
    backups = ['T007', 'T023', 'T024']
    staff_by_id = {s.id: s for s in staff_list}
    
    print("--- Tateyama Assignment Verification (April 2026) ---")
    
    for day in range(1, 31):
        d = date(2026, 4, day)
        if d.weekday() == 6: continue # Skip Sundays
        
        # We need to simulate the day 
        # For simplicity, we ignore night shifts here (or mock them)
        night_map = {}
        
        day_assignments, info = scheduler._schedule_one_day(d, req_map, night_map, {}, {s.id: {} for s in staff_list}, {s.id: 0 for s in staff_list})
        
        tate_assign = [a for a in day_assignments if a.location_code == '館山']
        
        if not tate_assign:
            print(f"{d} ({d.strftime('%a')}): None (Warning: 館山 assignment expected)")
            continue
            
        ass_id = tate_assign[0].staff_id
        ass_name = staff_by_id.get(ass_id).name
        req = req_map.get((endo_id, d), "")
        
        status = "OK"
        if ass_id == endo_id:
            if req in ['★', '★連', '☆', '☆小', '☆デ', '◆', '出/☆', '研(聴)', '退職', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)']:
                status = "NG (Endo should be off)"
        else:
            if ass_id not in backups:
                status = f"NG (Unexpected person: {ass_name})"
            elif req not in ['★', '★連', '☆', '☆小', '☆デ', '◆', '出/☆', '研(聴)', '退職', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)']:
                status = f"INFO (Endo replaced despite no request? Check availability)"
        
        print(f"{d} ({d.strftime('%a')}): {ass_name:10} (Endo Req: {req:5}) -> {status}")

if __name__ == '__main__':
    verify()

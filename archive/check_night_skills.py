import sys
from shift_scheduler.src.loaders.request_loader import RequestLoader
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.night_skill_deriver import NightSkillDeriver

loader = DataLoader('shift_scheduler/data')
staff_list, locations, skills, requests, rules, pb_rules = loader.load_all('2026-05')

active_staff = [s for s in staff_list if s.can_night_shift and s.status == '在籍']
day_availability = {d: active_staff[:] for d in range(1, 32)}

# Load requests prohibiting night shifts
HOLIDAY_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '○', '出/☆', '研(聴)', '退職'}
SPECIAL_NO_NIGHT = {'講', '会議', '全会', '業配', '業出'}

for r in requests:
    if r.date.month == 5:
        symbol = r.symbol
        d = r.date.day
        
        # Determine if staff is prohibited from night on Day D
        prohibited = False
        if symbol in HOLIDAY_SYMBOLS or symbol in SPECIAL_NO_NIGHT or symbol in ['17業', '17休']:
            prohibited = True
        
        # Remove from availability
        if prohibited:
            day_availability[d] = [s for s in day_availability[d] if s.id != r.staff_id]
            
        # Check previous day prohibition (if Day D has Holiday/17gyou, Day D-1 is prohibited)
        if symbol in HOLIDAY_SYMBOLS or symbol in ['17業', '17休']:
            if d - 1 >= 1:
                day_availability[d-1] = [s for s in day_availability[d-1] if s.id != r.staff_id]

# Check coverage
for d, staff_avail in day_availability.items():
    mr = sum(1 for s in staff_avail if s.night_mr)
    angio = sum(1 for s in staff_avail if s.night_angio)
    cath = sum(1 for s in staff_avail if s.night_cath)
    if mr == 0 or angio == 0 or cath == 0:
        print(f"FAILED on Day {d}: MR={mr}, Angio={angio}, Cath={cath}")
        print(f"  Available staff sum: {len(staff_avail)}")

print("Done checking.")

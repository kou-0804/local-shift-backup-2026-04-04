import sys
import os
from datetime import date, timedelta
import jpholiday

# Mocking the environment to use the real logic
sys.path.append(os.getcwd())
from shift_scheduler.src.data_loader import DataLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler

loader = DataLoader('shift_scheduler/data')
staff = loader.load_staff()
skills = loader.load_skills()
locs = loader.load_locations()
reqs_all = loader.load_requests(2026, 5, staff)
nights_raw = loader.load_night_requirements()

# Get the night assignments exactly as the main script does
ns = NightScheduler(staff, nights_raw, reqs_all, 2026, 5, skills)
night_assignments, _, prev_n = ns.schedule()
full_n = night_assignments + prev_n

# Create DayScheduler
ds = DayScheduler(staff, locs, 2026, 5, skills, reqs_all, full_n, {}, [], 10)

# Simulate current state on May 20th
# We need to know the 'total_work_count' and 'consecutive_work_days' as of May 19th.
# Hard to get perfectly without running the whole month, but let's see if T002 is AVAILABLE at all.

req_map = {(r.staff_id, r.date): r.symbol for r in reqs_all}
night_map = {(na.staff_id, na.date): True for na in full_n}

target_date = date(2026, 5, 20)

def check_availability(s_id, d):
    s = next(x for x in staff if x.id == s_id)
    # This mirrors the logic in _schedule_one_day
    req = req_map.get((s.id, d))
    if night_map.get((s.id, d), False): return "Night"
    if night_map.get((s.id, d - timedelta(days=1)), False): return "Ake"
    if req in ds.HOLIDAY_SYMS: return f"Holiday ({req})"
    
    # Check consecutive day limit
    # For T002, 5/18, 5/19 were work.
    c_days = 2 # assumed
    
    forced_future = 0
    CONDITIONAL_HOLIDAY_SYMS = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
    for offset in range(1, 10):
        check_d = d + timedelta(days=offset)
        is_n = night_map.get((s.id, check_d))
        is_a = night_map.get((s.id, check_d - timedelta(days=1)))
        req_sym = req_map.get((s.id, check_d))
        is_working_req = False
        if req_sym and req_sym not in ['休', '○', '★', '★連', '☆', '☆小', '☆デ', '◆', '退職', '17休']:
            if req_sym in CONDITIONAL_HOLIDAY_SYMS:
                is_pub = (check_d.month == 1 and check_d.day in [1, 2, 3]) or jpholiday.is_holiday(check_d) or check_d.weekday() == 6
                if not is_pub: is_working_req = True
            else: is_working_req = True
        if is_n or is_a or is_working_req: forced_future += 1
        else: break
    
    if c_days >= 6 or (c_days + 1 + forced_future > 6):
        return f"Consecutive Limit (c={c_days}, future={forced_future})"
    
    return "Available"

print(f"T002 availability on 5/20: {check_availability('T002', target_date)}")

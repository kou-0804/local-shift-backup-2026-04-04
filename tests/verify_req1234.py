
import sys
import os
from datetime import date
from unittest.mock import MagicMock

# Ensure we can import src
sys.path.append(os.getcwd())

from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler
from shift_scheduler.src.models.staff import Staff
from shift_scheduler.src.models.location import Location
from shift_scheduler.src.models.assignment import NightAssignment
from shift_scheduler.src.models.skill import SkillRank
from shift_scheduler.src.models.request import Request

def verify_requirements():
    print("=== Starting Verification for Requirements 1-4 & Refinements ===")
    
    # --- Setup Mocks ---
    # Staff: 5 people
    staff_list = []
    for i in range(1, 6):
        s = MagicMock()
        s.id = f'S{i}'
        s.name = f'Staff{i}'
        s.gender = MagicMock()
        s.gender.value = '女' # Assume female for simplicity
        s.can_night_shift = True
        s.status = '在籍'
        # Night Skills
        s.night_mr = True
        s.night_angio = True
        s.night_cath = True
        staff_list.append(s)
        
    # Locations
    loc_shu = MagicMock(spec=Location)
    loc_shu.code = '出' # Day Shift
    loc_shu.is_active = True
    loc_shu.get_required_count.return_value = 0 # Controlled by specific test logic or override
    loc_shu.gender_constraint = None

    loc_late = MagicMock(spec=Location)
    loc_late.code = '超遅' # Super Late
    loc_late.is_active = True
    loc_late.get_required_count.return_value = 0
    loc_late.gender_constraint = None
    
    locations = [loc_shu, loc_late]
    
    # Skills: All capable
    skills = {}
    for s in staff_list:
        skills[s.id] = {
            '出': SkillRank.A,
            '超遅': SkillRank.A,
            'MG': SkillRank.A
        }

    rules = []
    pb_rules = []
    
    # Instantiate DayScheduler
    # Only for Dec 2025
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2025, 12)
    
    # --- Test Case 1: Req 3 (No Super Late if Next Night) & Req 4 (Holiday after Post-Night) ---
    print("\n--- Testing Req 3 & 4: Night Interaction ---")
    
    # Setup Night Assignments including PREVIOUS MONTH (Nov 29, 30)
    # S2 has Night on Nov 29 (Sat).
    # -> Dec 1 (Mon): 2 days after Night. Should be Enforced Holiday (Req 4 Fix).
    
    night_assignments = [
        NightAssignment(date=date(2025, 12, 3), staff_id='S1', role='MR'),
        NightAssignment(date=date(2025, 11, 29), staff_id='S2', role='MR')
    ]
    
    # Dec 1 (Mon) -> Need 1 '出'.
    # S2 available? No, should be enforced holiday.
    loc_shu.get_required_count = MagicMock(side_effect=lambda w: 1 if w == 0 else 0) # Mon=1
    
    # Dec 2 (Tue) -> Need 1 '超遅'.
    loc_late.get_required_count = MagicMock(side_effect=lambda w: 1 if w == 1 else 0) # Tue=1
    
    # Dec 5 (Fri) -> Need 1 '出'.
    loc_shu.get_required_count = MagicMock(side_effect=lambda w: 1 if w == 4 else 0) # Fri=1
    
    requests = []
    
    # Run Schedule
    assignments = scheduler.schedule(requests, night_assignments)
    
    # Check Dec 2 (Tue) for S1
    d2_assigns = [a for a in assignments if a.date == date(2025, 12, 2)]
    s1_d2 = next((a for a in d2_assigns if a.staff_id == 'S1'), None)
    
    print(f"Dec 2 Assignment for S1 (Next Day Night): {s1_d2.location_code if s1_d2 else 'None'}")
    if s1_d2 and s1_d2.location_code == '超遅':
        print("[FAIL] Req 3: S1 assigned to Super Late before Night Shift!")
    else:
        print("[PASS] Req 3: S1 NOT assigned to Super Late before Night Shift.")
        
    # Check Dec 5 (Fri) for S1 - 2 days after Night
    d5_assigns = [a for a in assignments if a.date == date(2025, 12, 5)]
    s1_d5 = next((a for a in d5_assigns if a.staff_id == 'S1'), None)
    
    print(f"Dec 5 Assignment for S1 (2 Days after Night): {s1_d5.location_code if s1_d5 else 'None'}")
    if s1_d5 and s1_d5.location_code != '休': # Should be '休' or None (if excluded)
         # Note: New logic returns '休'.
         if s1_d5.location_code == '休':
             print("[PASS] Req 4: S1 has Enforced Holiday Assignment ('休').")
         else:
             print(f"[FAIL] Req 4: S1 assigned to {s1_d5.location_code} instead of Holiday!")
    elif not s1_d5:
         # If simpler logic just excludes, this is also acceptable but we prefer '休' now?
         # The new logic returns '休'. So None would be odd unless not in available list initially.
         print("[WARN] Req 4: S1 has NO assignment (Expected '休').")
    
    # Check Dec 1 (Mon) for S2 (Month Boundary Check)
    d1_assigns = [a for a in assignments if a.date == date(2025, 12, 1)]
    s2_d1 = next((a for a in d1_assigns if a.staff_id == 'S2'), None)
    
    print(f"Dec 1 Assignment for S2 (Prev Month Night Nov 29): {s2_d1.location_code if s2_d1 else 'None'}")
    if s2_d1 and s2_d1.location_code == '休':
        print("[PASS] Req 4 Fix: Month Boundary Handled (Enforced Holiday).")
    else:
        print(f"[FAIL] Req 4 Fix: Month Boundary NOT Handled! {s2_d1}")


    # --- Test Case 2: Req 2 (Strict Staffing) ---
    print("\n--- Testing Req 2: Strict Staffing (Max Limit) ---")
    # Date: Dec 1 (Mon). Need 1 '出'. 5 Staff available.
    # Should assign EXACTLY 1.
    
    loc_shu.get_required_count = MagicMock(return_value=1)
    loc_late.get_required_count = MagicMock(return_value=0)
    
    scheduler2 = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2025, 12)
    # Mock date generation to only include Dec 1
    scheduler2.dates = [date(2025, 12, 1)]
    
    asgs_strict = scheduler2.schedule([], [])
    # Count valid assignments only (exclude '休' if any)
    valid_asgs = [a for a in asgs_strict if a.location_code not in ['休']]
    count = len(valid_asgs)
    
    print(f"Dec 1 Assignments (Req=1, Staff=5): {count}")
    if count == 1:
        print("[PASS] Req 2: Assigned exactly 1 person.")
    else:
        print(f"[FAIL] Req 2: Validation failed. Count={count}")


    # --- Test Case 3: Req 1 (Equalize '出') ---
    print("\n--- Testing Req 1: Equalize '出' on Holidays ---")
    
    s_small = staff_list[:3]
    skills_small = {s.id: skills[s.id] for s in s_small}
    
    scheduler4 = DayScheduler(s_small, locations, rules, skills_small, pb_rules, 2025, 12)
    # Only run for 3 Sundays
    scheduler4.dates = [date(2025, 12, 7), date(2025, 12, 14), date(2025, 12, 21)]
    
    # Need '出' on Sundays
    loc_shu.code = '出'
    
    asgs_eq = scheduler4.schedule([], [])
    
    counts = {s.id: 0 for s in s_small}
    for a in asgs_eq:
        if a.location_code == '出':
            counts[a.staff_id] += 1
            
    print(f"Counts for 3 Sundays (Total 6 slots): {counts}")
    vals = list(counts.values())
    if max(vals) - min(vals) <= 1:
         print("[PASS] Req 1: Assignments Distributed Evenly.")
    else:
         print(f"[FAIL] Req 1: Uneven distribution! {counts}")


    # --- Test Case 4: Night Scheduler Intervals ---
    print("\n--- Testing Req C: Night Shift Intervals ---")
    # Setup: 15 Staff (Enough to allow sparse schedule).
    # Quota for S1 = 2.
    # Should place shifts far apart.
    
    ns_staff_list = []
    for i in range(1, 16):
        s = MagicMock()
        s.id = f'S{i}'
        s.can_night_shift = True
        s.night_mr = True
        s.night_angio = True
        s.night_cath = True
        ns_staff_list.append(s)
        
    night_scheduler = NightScheduler(ns_staff_list, 2025, 12)
    night_quotas = {'S1': 2}
    
    # No requests
    ns_res = night_scheduler.schedule([], night_quotas)
    
    # Check days
    s1_days = sorted([a.date.day for a in ns_res if a.staff_id == 'S1'])
    print(f"S1 Night Shifts (Quota 2): {s1_days}")
    
    if len(s1_days) >= 2:
        gap = s1_days[1] - s1_days[0]
        print(f"Gap: {gap} days")
        if gap >= 7:
            print("[PASS] Req C: Interval is large (>= 7 days).")
        else:
            print("[FAIL] Req C: Interval is too short (< 7 days). Optimization failed.")
    else:
        print("[WARN] S1 assigned fewer than 2 shifts.")


if __name__ == "__main__":
    verify_requirements()

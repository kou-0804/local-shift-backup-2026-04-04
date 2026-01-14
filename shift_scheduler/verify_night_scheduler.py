from datetime import date
from typing import List, Dict
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler
from shift_scheduler.src.models.request import Request
from shift_scheduler.src.models.staff import Staff

def run_verification():
    # 1. Load Data
    dl = DataLoader('shift_scheduler/data')
    # Use actual master data, but dummy request/quota data will be created below
    # because the CSVs are missing request/quota content for now.
    staff_list, locations, skills, _, rules = dl.load_all('2025-12')
    
    # 2. Setup Dummy Request/Quota Data
    # 38 night staff
    night_staff = [s for s in staff_list if s.can_night_shift]
    print(f"Night Staff Count: {len(night_staff)}")
    
    # Analysis of Skill Capacity
    mr_staff = [s for s in night_staff if s.night_mr]
    angio_staff = [s for s in night_staff if s.night_angio]
    cath_staff = [s for s in night_staff if s.night_cath]
    
    print(f"Skill Counts: MR={len(mr_staff)}, Angio={len(angio_staff)}, Cath={len(cath_staff)}")
    
    # We need 31 shifts for each skill.
    # MR is the bottleneck (10 staff). They need ~3.1 shifts each.
    
    quotas = {s.id: 0 for s in night_staff}
    total_shifts = 93
    
    # 1. Assign minimum requirements to specialized staff
    # For MR staff (10 people), we need at least 31 shifts.
    # Give 4 shifts to 5 people, 3 shifts to 5 people. Total 35 shifts.
    mr_count = len(mr_staff)
    for i, s in enumerate(mr_staff):
        if i < 5:
            quotas[s.id] = 4
            total_shifts -= 4
        else:
            quotas[s.id] = 3
            total_shifts -= 3
        
    # 2. Distribute remaining slots to others
    # Current allocated: 10 * 3 = 30. Remaining to alloc: 93 - 30 = 63.
    # Staff without quota so far: 38 - 10 = 28.
    
    # Simple round-robin for remaining
    remaining_staff_ids = [s.id for s in night_staff] # All staff
    import itertools
    cycle_staff = itertools.cycle(remaining_staff_ids)
    
    # We need to fill up to 93 total allocated
    # Current sum = 30.
    # Need to add 63 more.
    count = 0
    limit = 93 - sum(quotas.values())
    
    for s_id in cycle_staff:
        if count >= limit:
            break
        # Don't give too many to one person (e.g. max 5)
        if quotas[s_id] < 5:
            quotas[s_id] += 1
            count += 1
            
    print(f"Quotas sum: {sum(quotas.values())} (Should be 93)")
    
    # Dummy Requests
    requests = []
    # Add some random holidays
    for s in night_staff[:5]:
        requests.append(Request(s.id, date(2025, 12, 5), '★')) # Holiday on 5th
        
    # Add '17業' (No night on day and previous day)
    # T002 has '17業' on 12/10 -> No night on 12/10 and 12/9
    requests.append(Request(night_staff[0].id, date(2025, 12, 10), '17業'))
    
    # 3. Run Scheduler
    scheduler = NightScheduler(staff_list, 2025, 12)
    try:
        assignments = scheduler.schedule(requests, quotas)
        
        print(f"Successfully scheduled {len(assignments)} assignments.")
        
        # Verify Hard Constraints
        verify_constraints(assignments, requests, quotas, night_staff)
        
    except Exception as e:
        print(f"Scheduling Failed: {e}")
        import traceback
        traceback.print_exc()

def verify_constraints(assignments, requests, quotas, night_staff):
    # NH-01 check
    from collections import Counter
    counts = Counter([a.date for a in assignments])
    for d, c in counts.items():
        if c != 3:
            print(f"NH-01 Failed: Date {d} has {c} staff")
            
    # NH-08 check (17業)
    # T002 (night_staff[0]) on 12/10 is '17業'
    target_id = night_staff[0].id
    target_date = date(2025, 12, 10)
    prev_date = date(2025, 12, 9)
    
    for a in assignments:
        if a.staff_id == target_id:
            if a.date == target_date:
                print(f"NH-08 Failed: {target_id} assigned on 17業 day {target_date}")
            if a.date == prev_date:
                print(f"NH-08 Failed: {target_id} assigned on previous day of 17業 {prev_date}")
                
    print("Verification Logic Finished.")

if __name__ == "__main__":
    run_verification()

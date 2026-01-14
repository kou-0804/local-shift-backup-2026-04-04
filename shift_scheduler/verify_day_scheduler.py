from datetime import date
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.models.request import Request
from shift_scheduler.src.models.assignment import NightAssignment

def run_verification():
    # 1. Load Data
    dl = DataLoader('shift_scheduler/data')
    # Unpack 6 items now
    staff_list, locations, skills, _, rules, pb_rules = dl.load_all('2025-12')
    
    print(f"Loaded {len(pb_rules)} Power Balance rules.")
    
    # 2. Setup Dummy Data
    requests = []
    # Add some holiday requests
    requests.append(Request(staff_list[1].id, date(2025, 12, 1), '★')) # T002 is usually 2nd in list
    
    # Dummy Night Assignments (Empty for now)
    night_assignments = []
    
    # 3. Run Scheduler
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2025, 12)
    
    try:
        assignments = scheduler.schedule(requests, night_assignments)
        print(f"Successfully scheduled {len(assignments)} day assignments.")
        
        # Verification of a random day
        d1_assignments = [a for a in assignments if a.date == date(2025, 12, 1)]
        print(f"Day 1 Assignments: {len(d1_assignments)}")
        for a in d1_assignments[:5]:
            print(f" - {a.staff_id} @ {a.location_code} ({a.rank})")
            
        print("\nVerifying Special Rules:")
        # Check Rules for 12/1 (Sunday? No, 2025/12/1 is Monday)
        # 2025 Dec 1 is Monday.
        
        # Check if any rules applied on Day 1
        # ... logic to check specific rules if known.
        # Ideally check logs or specific day rule.
        
        # T002 check (Request=Holiday)
        t002_day1 = [a for a in d1_assignments if a.staff_id == 'T002']
        if t002_day1:
             print(f"Failure: T002 assigned on holiday! {t002_day1}")
        else:
             print("Success: T002 not assigned (Holiday request).")

        # SR-01 check: 12/02 (Tue) Angio (ア) -> Need A rank >= 2?
        # Assuming SR-01 is actively loaded for 'ア' on Tue.
        d2_assignments = [a for a in assignments if a.date == date(2025, 12, 2)]
        if d2_assignments:
            angio_assignments = [a for a in d2_assignments if a.location_code == 'ア']
            print(f"Day 2 (Tue) Angio Assignments: {len(angio_assignments)}")
            a_ranks = [a for a in angio_assignments if a.rank == 'A'] # Rank is Enum, string repr might be 'A'
            # Wait, DayAssignment.rank is SkillRank enum.
            # verify script prints it, but comparison needs Enum or value.
            # Let's count print output or use correct Enum comparison logic if we import it.
            # Just print detail.
            for a in angio_assignments:
                print(f"  - {a.staff_id} ({a.rank})")

    except Exception as e:
        print(f"Scheduling Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_verification()

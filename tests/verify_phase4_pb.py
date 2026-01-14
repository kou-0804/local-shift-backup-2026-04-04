from datetime import date
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.models.request import Request
from shift_scheduler.src.models.skill import SkillRank

def verify_phase4():
    # 1. Load Data
    dl = DataLoader('shift_scheduler/data')
    staff_list, locations, skills, _, rules, pb_rules = dl.load_all('2025-12')
    
    # 2. Run Scheduler
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2025, 12)
    
    try:
        # No requests/night assignments for base test
        assignments = scheduler.schedule([], [])
        print(f"Total Assignments: {len(assignments)}")
        
        # Verify PB-04 (Portable D Pair)
        # Check all days
        portable_violations = 0
        ct_violations = 0
        
        for d in range(1, 32):
            day_d = date(2025, 12, d)
            day_assigns = [a for a in assignments if a.date == day_d]
            
            # Check Portable
            p_assigns = [a for a in day_assigns if a.location_code == 'ポ']
            p_d_ranks = [a for a in p_assigns if a.rank == SkillRank.D]
            if len(p_d_ranks) >= 2:
                print(f"[FAIL] Day {d}: Portable has {len(p_d_ranks)} D staff.")
                portable_violations += 1
                
            # Check CT
            ct_assigns = [a for a in day_assigns if a.location_code == 'CT']
            ct_cd_ranks = [a for a in ct_assigns if a.rank in [SkillRank.C, SkillRank.D]]
            required = 4 if day_d.weekday() <= 4 else 3 # Approx from Master (Mon-Fri=4, Sat=3)
            # Actually easier to check "At least 1 Non-CD"
            if len(ct_cd_ranks) == len(ct_assigns) and len(ct_assigns) >= 2:
                 print(f"[FAIL] Day {d}: CT has ONLY CD staff (Count {len(ct_assigns)}).")
                 ct_violations += 1

        if portable_violations == 0:
            print("[Pass] PB-04: No Portable D-Pair violations.")
        if ct_violations == 0:
            print("[Pass] PB-05: No CT CD-Only violations.")

    except Exception as e:
        print(f"Scheduling Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_phase4()

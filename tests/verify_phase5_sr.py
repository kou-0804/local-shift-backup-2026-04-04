from datetime import date
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.models.skill import SkillRank

def verify_phase5():
    # 1. Load All Data
    dl = DataLoader('shift_scheduler/data')
    staff_list, locations, skills, _, rules, pb_rules = dl.load_all('2025-12')
    
    # 2. Run Scheduler
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2025, 12)
    
    try:
        assignments = scheduler.schedule([], [])
        print(f"Total Assignments: {len(assignments)}")
        
        # 1. Angio (ア) Rules
        # Tue: A >= 2
        # Thu: Count == 2
        for d in range(1, 32):
            day_d = date(2025, 12, d)
            weekday = day_d.weekday() # 0=Mon
            
            day_assigns = [a for a in assignments if a.date == day_d]
            angio = [a for a in day_assigns if a.location_code == 'ア']
            
            # Tue (1)
            if weekday == 1:
                # Expect A >= 2 (if Master says so OR Rule says so)
                # Let's check if rule applies.
                # Assuming SR-01 exists.
                a_count = len([a for a in angio if a.rank == SkillRank.A])
                if angio and a_count < 2:
                     # Check if it was supposed to be enforced?
                     # If the rule exists in CSV, it should be enforced.
                     # We'll just log warning/failure if low.
                     print(f"[Check] Day {d} (Tue) Angio A-Rank: {a_count}")
                     if a_count < 2: print("  -> SUSPICIOUS (Expected >= 2)")
            
            # Thu (3)
            if weekday == 3:
                # Expect Count 2? Or whatever rule says.
                if len(angio) == 2:
                     pass # OK
                else:
                     # Maybe Master says 2? 
                     print(f"[Check] Day {d} (Thu) Angio Count: {len(angio)}")

        # 2. HB 1st Fri (A>=2)
        # 1st Friday of Dec 2025 is Dec 5th.
        d5_hb = [a for a in assignments if a.date == date(2025, 12, 5) and a.location_code == 'HB']
        if d5_hb:
             a_count = len([a for a in d5_hb if a.rank == SkillRank.A])
             print(f"[Check] Dec 5 (1st Fri) HB A-Rank: {a_count}")
             if a_count >= 2:
                 print("[Pass] HB 1st Fri Rule met.")
             else:
                 print("[FAIL] HB 1st Fri Rule NOT met.")

        # 3. OP 1st Fri (Select from HB A)
        # Dec 5th.
        d5_op = [a for a in assignments if a.date == date(2025, 12, 5) and a.location_code == 'OP']
        if d5_op:
            staff_ids = [a.staff_id for a in d5_op]
            # Check if any has HB Rank A
            valid = False
            for sid in staff_ids:
                rank = skills.get(sid, {}).get('HB', SkillRank.NONE)
                if rank == SkillRank.A:
                    valid = True
            
            if valid:
                print(f"[Pass] OP 1st Fri: Assigned staff {staff_ids} has HB-A rank.")
            else:
                print(f"[FAIL] OP 1st Fri: Assigned staff {staff_ids} does NOT have HB-A rank.")

    except Exception as e:
        print(f"Scheduling Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_phase5()

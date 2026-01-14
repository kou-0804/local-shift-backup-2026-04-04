from datetime import date
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.models.request import Request
from shift_scheduler.src.models.assignment import NightAssignment

def verify_phase3():
    # 1. Load Data
    dl = DataLoader('shift_scheduler/data')
    staff_list, locations, skills, _, rules, pb_rules = dl.load_all('2025-12')
    
    # 2. Setup Data (Use actual 2025-12 data if mostly available, or dummy if needed)
    # We will use dummy requests to test specific constraints
    
    # Dummy Night Assignments (Empty for basic test)
    night_assignments = []
    
    # Dummy Requests for DH-07, DH-04 test
    # T001: Holiday on day 1
    # T002: ‘勤’ on day 2 -> Should become '勤務表作成'
    # T003: '17業' on day 3 -> Late forbidden
    
    requests = []
    # Use Staff Objects
    s1 = staff_list[0]
    s2 = staff_list[1]
    s3 = staff_list[2]
    
    requests.append(Request(s1.id, date(2025, 12, 1), '★'))
    requests.append(Request(s2.id, date(2025, 12, 2), '勤'))
    requests.append(Request(s3.id, date(2025, 12, 3), '17業'))
    
    # 3. Run Scheduler
    # Note: We include pb_rules/rules but we focus on basic output verification
    scheduler = DayScheduler(staff_list, locations, rules, skills, pb_rules, 2025, 12)
    
    try:
        assignments = scheduler.schedule(requests, night_assignments)
        
        # Verify Results
        print(f"Total Assignments: {len(assignments)}")
        
        # DH-04: Holiday Check
        d1_s1 = [a for a in assignments if a.date == date(2025, 12, 1) and a.staff_id == s1.id]
        if not d1_s1:
            print("[Pass] DH-04: Staff on Holiday not assigned.")
        else:
            print(f"[FAIL] DH-04: Staff assigned on Holiday: {d1_s1}")
            
        # DH-07: Special Placement Check
        d2_s2 = [a for a in assignments if a.date == date(2025, 12, 2) and a.staff_id == s2.id]
        if d2_s2 and d2_s2[0].location_code == '勤務表作成':
             print("[Pass] DH-07: '勤' mapped to '勤務表作成'.")
        else:
             print(f"[FAIL] DH-07: '勤' failed mapping. Result: {d2_s2}")

        # DH-08: 17業 Check
        d3_s3 = [a for a in assignments if a.date == date(2025, 12, 3) and a.staff_id == s3.id]
        if d3_s3:
            loc = d3_s3[0].location_code
            if loc in ['遅番', '超遅', 'MG']:
                print(f"[FAIL] DH-08: '17業' assigned to {loc}")
            else:
                print(f"[Pass] DH-08: '17業' assigned to Safe Location: {loc}")
        else:
            print("[Pass] DH-08: '17業' not assigned (acceptable).")

    except Exception as e:
        print(f"Scheduling Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_phase3()

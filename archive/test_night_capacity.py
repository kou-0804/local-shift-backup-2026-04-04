import sys
from shift_scheduler.src.loaders.request_loader import RequestLoader
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.night_skill_deriver import NightSkillDeriver

loader = DataLoader('shift_scheduler/data')
staff_list, locations, skills, requests, rules, pb_rules = loader.load_all('2026-05')
name_to_id = {s.name: s.id for s in staff_list}
night_counts = loader.load_night_counts('2026-05', name_to_id=name_to_id)

print(f"Loaded night counts: {night_counts}")
total_quota = sum(night_counts.values())
print(f"Total Night Quota: {total_quota}")
print(f"Required shifts (31 days * 3): {31 * 3}")

# Check staff availability for night shifts based on requests
active_staff = [s.id for s in staff_list if s.status == '在籍']
day_availability = {d: [] for d in range(1, 32)}

for d in range(1, 32):
    for sid in active_staff:
        if night_counts.get(sid, 0) > 0:
            day_availability[d].append(sid)

for r in requests:
    if r.date.month == 5 and r.symbol in ['★', '☆', '◆', '休', '17休']: # Holiday requests
        d = r.date.day
        if r.staff_id in day_availability[d]:
            day_availability[d].remove(r.staff_id)

for d, staff in day_availability.items():
    if len(staff) < 3:
        print(f"WARNING: Only {len(staff)} staff available on Day {d}!")

min_staff = min(len(s) for s in day_availability.values())
print(f"Minimum staff available on any day: {min_staff}")

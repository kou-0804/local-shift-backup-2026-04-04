from datetime import date
from shift_scheduler.src.data_loader import DataLoader
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler

loader = DataLoader('shift_scheduler/data')
staff = loader.load_staff()
reqs = loader.load_requests(2026, 5, staff)
skills = loader.load_skills()
locs = loader.load_locations()
nights = loader.load_night_requirements()

night_sched = NightScheduler(staff, nights, reqs, 2026, 5, skills)
night_assignments, _, _ = night_sched.schedule()

day_sched = DayScheduler(staff, locs, 2026, 5, skills, reqs, night_assignments, {}, [], 10)
days, _ = day_sched.schedule(reqs, night_assignments)

may20_t002 = [a for a in days if a.date == date(2026, 5, 20) and a.staff_id == 'T002']
print(f"May 20th T002 assignment: {may20_t002}")


import main
from shift_scheduler.src.data_loader import DataLoader
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from datetime import date

loader = DataLoader('shift_scheduler/data')
staff = loader.load_staff()
reqs = loader.load_requests(2026, 5, staff)
skills = loader.load_skills()
locs = loader.load_locations()
nights = loader.load_night_requirements()

from shift_scheduler.src.models.skill import SpecialRules
ns = NightScheduler(staff, nights, reqs, 2026, 5, skills)
n_assigns, _, prev_n = ns.schedule()
full_n = n_assigns + prev_n

ds = DayScheduler(staff, locs, 2026, 5, skills, reqs, full_n, {}, [], 10)
# We need `workday_budget` and `total_work_count`
# We just want to check available_staff generation
# Wait, let's just trace DayScheduler on a specific day by mocking the loop inside `_schedule_one_day`
d = date(2026, 5, 20)
print(ds._qualifies_for_location('T002', 'DR'))

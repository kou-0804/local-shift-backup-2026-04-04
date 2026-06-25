from shift_scheduler.src.loaders.request_loader import RequestLoader
from shift_scheduler.src.loaders.data_loader import DataLoader

loader = DataLoader('shift_scheduler/data')
staff_list, locations, skills, requests, rules, pb_rules = loader.load_all('2026-05')

yaki_count = {d: 0 for d in range(1, 32)}
for r in requests:
    if r.date.month == 5 and r.symbol == '夜希':
        yaki_count[r.date.day] += 1

for d, count in yaki_count.items():
    if count >= 3:
        print(f"Day {d} has {count} 夜希 requests!")

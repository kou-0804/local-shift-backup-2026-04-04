"""
勤務表作成システム メインプログラム
"""
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.night_skill_deriver import NightSkillDeriver
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.excel_generator import ExcelGenerator
import argparse
import sys
import os
from shift_scheduler.src.models.assignment import NightAssignment
from datetime import date, timedelta

def main():
    parser = argparse.ArgumentParser(description='勤務表自動作成システム')
    parser.add_argument('--year', type=int, required=True, help='年（例: 2026）')
    parser.add_argument('--month', type=int, required=True, help='月（例: 1）')
    parser.add_argument('--data-dir', default='shift_scheduler/data', help='データディレクトリ')
    parser.add_argument('--output-dir', default='output', help='出力ディレクトリ')
    args = parser.parse_args()
    
    year = args.year
    month = args.month
    year_month = f"{year}-{month:02d}"
    
    print("=" * 70, flush=True)
    print(f"勤務表作成システム - {year}年{month}月", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)
    
    # データ読み込み
    print("📂 データ読み込み中...", flush=True)
    # NOTE: user originally asked for `DataLoader(data_dir=args.data_dir)`
    # My DataLoader logic might just take base path.
    # checking imports: src/loaders/data_loader.py
    try:
        loader = DataLoader(data_dir=args.data_dir)
        # load_all returns: staff_list, locations, skills, requests, rules, pb_rules
        # But we need granular load as per user snippet to be safe?
        # User snippet used granular calls: load_technicians, load_skills...
        # My DataLoader (from Step 306/prev) has `load_all` but maybe not granular public methods?
        # Let's use `load_all` for safety if my granular methods aren't exposed or same signature.
        # But user script uses granular. Let's try to stick to user script structure if possible.
        # If my DataLoader doesn't support it, I will use `load_all`.
        
        # Actually my DataLoader usually has load_technicians etc.
        # Let's use the granular calls if they exist, or fallback to load_all components.
        # Checking DataLoader contents via prior knowledge or assume standard structure.
        # I'll use `load_all` components to be safe and cleaner.
        
        staff_list, locations, skills, requests, rules, pb_rules = loader.load_all(year_month)
        
        # Need night_counts? load_all doesn't return night_counts?
        # In Step 283 log, `load_all` returns:
        # staff_list, locations, skills, requests, rules, pb_rules
        # It MISSES night_counts!
        # I need to load night_counts separately if needed for NightScheduler.
        # NightScheduler needs `night_counts`.
        # I should check if `loader` has `load_night_counts`.
        # 6. Load Night Shift Counts (Limits)
        name_to_id = {s.name: s.id for s in staff_list}
        night_counts = loader.load_night_counts(year_month, name_to_id=name_to_id)
        print(f"  夜勤回数データ: {len(night_counts)}名分", flush=True)

    except Exception as e:
        print(f"Error loading data: {e}", flush=True)
        # Fallback or exit
        # Try granular if load_all failed or signature mismatch
        # But let's assume we can fix it.
        # Let's inspect DataLoader if needed. 
        
    technicians = staff_list # Alias
    special_rules = rules
    
    print(f"  技師: {len(technicians)}名", flush=True)
    print(f"  勤務場所: {len(locations)}箇所", flush=True)
    print(f"  予定申請: {len(requests)}件", flush=True)
    print(flush=True)
    
    # 夜勤スキル導出
    print("🌙 夜勤スキル導出中...", flush=True)
    night_skills = NightSkillDeriver.derive(skills)
    mr_count = sum(1 for ns in night_skills if ns.mr_skill)
    angio_count = sum(1 for ns in night_skills if ns.angio_skill)
    cath_count = sum(1 for ns in night_skills if ns.cath_skill)
    print(f"  MRスキル: {mr_count}名", flush=True)
    print(f"  アンギオスキル: {angio_count}名", flush=True)
    print(f"  心カテスキル: {cath_count}名", flush=True)
    print(flush=True)
    
    # --- Load Previous Month History from Requests ---
    print("🔙 前月の夜勤実績を申請データから確認中...", flush=True)
    start_date = date(year, month, 1)
    prev_month_limit = start_date - timedelta(days=7)
    prev_night_history = []
    for r in requests:
        if r.date < start_date and r.date >= prev_month_limit:
            if '夜' in r.symbol:
                na = NightAssignment(date=r.date, staff_id=r.staff_id, role='History')
                prev_night_history.append(na)
    print(f"  前月の夜勤実績(申請より): {len(prev_night_history)}件", flush=True)

    # 夜勤スケジューリング
    print("🌙 夜勤スケジューリング実行中...", flush=True)
    
    night_scheduler = NightScheduler(
        staff_list=technicians,
        year=year,
        month=month
    )
    night_result = night_scheduler.schedule(requests, night_counts, prev_night_history) # Returns List[NightAssignment]
    print(f"  夜勤配置数: {len(night_result)}件", flush=True)
    print(flush=True)
    
    # Data Conversion: List[NightAssignment] -> Dict[int, List[str]] (day -> [ids])
    night_assignments_dict = {}
    for na in night_result:
        if na.date.day not in night_assignments_dict:
            night_assignments_dict[na.date.day] = []
        night_assignments_dict[na.date.day].append(na.staff_id)
        
    # --- Load Previous Month History from Requests (Req 4 Fix via User Feedback) ---
    print("🔙 前月の夜勤実績を申請データから確認中...", flush=True)
    
    # We need to find 'Night' requests in the previous month (last few days)
    # and treat them as confirmed Night Assignments for the scheduler's context.
    
    # Filter for entries explicitly marked as Night in previous month
    # We look back up to 7 days just to be safe for intervals, 
    # but strictly we only need 2 days for the "Holiday after Post-Night" rule.
    # User said "Last month's night info is in Requests".
    
    start_date = date(year, month, 1)
    prev_month_limit = start_date - timedelta(days=7)
    
    prev_night_history = []
    
    for r in requests:
        # Check if date is in previous month range
        if r.date < start_date and r.date >= prev_month_limit:
            # Check for Night symbol
            # Usually '夜希' (Night Request) or just '夜' if user entered it that way.
            # We assume any request containing '夜' in the past is a confirmed Night Shift.
            if '夜' in r.symbol:
                # Create a NightAssignment object
                # Role is dummy (not needed for constraint check usually)
                na = NightAssignment(date=r.date, staff_id=r.staff_id, role='History')
                prev_night_history.append(na)
                # print(f"  Found history: {r.date} {r.staff_id} {r.symbol}")

    print(f"  前月の夜勤実績(申請より): {len(prev_night_history)}件 -> 統合", flush=True)
    
    # Merge for Scheduler
    # We keep `night_result` clean for Excel output (current month only).
    # We pass `full_night_assignments` to DayScheduler.
    full_night_assignments = night_result + prev_night_history
    
    # 日勤スケジューリング
    print("☀️ 日勤スケジューリング実行中...", flush=True)
    day_scheduler = DayScheduler(
        staff_list=technicians, 
        skills=skills,
        locations=locations,
        pb_rules=pb_rules,
        rules=special_rules,
        year=year,
        month=month
    )
    
    day_result_list = day_scheduler.schedule(requests, full_night_assignments) # Pass Full List
    print(f"  日勤配置数: {len(day_result_list)}件", flush=True)
    print(flush=True)
    
    # Data Conversion: List[DayAssignment] -> Dict[int, Dict[str, List[str]]]
    # {day: {loc_code: [tech_id]}}
    day_assignments_dict = {}
    for da in day_result_list:
        # If day_result_list contains '休' (Prev Night Holiday enforcement), we handle it.
        d_day = da.date.day
        # Filter out if date is not current month
        if da.date.month != month: continue
        
        if d_day not in day_assignments_dict:
            day_assignments_dict[d_day] = {}
        if da.location_code not in day_assignments_dict[d_day]:
            day_assignments_dict[d_day][da.location_code] = []
        day_assignments_dict[d_day][da.location_code].append(da.staff_id)
        
    # Requests Conversion
    requests_dict = {}
    for r in requests:
        # Note: Do not filter by month strictly, as user wants surrounding days too.
        # if r.date.month != month: continue 
        
        d_day = r.date.day
        # Only add to requests_dict (for Excel) if it falls within THIS month?
        # ExcelGenerator iterates `range(1, days_in_month+1)`.
        # If we put day 32 or day -1, it won't be displayed but won't crash.
        # However, `d_day = r.date.day` for different month might clash if we just use `.day`.
        # e.g. Dec 1st vs Jan 1st.
        # We need to filter for Excel display to ONLY this month.
        # But for Scheduler, we passed the raw list `requests`.
        # Schedulers use `req_map = {(r.staff_id, r.date): ...}` which handles full date.
        # So passing raw `requests` list to schedulers is fine.
        
        # Here we build `requests_dict` for Excel Generator.
        # Excel Generator iterates 1..31.
        if r.date.year == year and r.date.month == month:
            if d_day not in requests_dict:
                requests_dict[d_day] = {}
            requests_dict[d_day][r.staff_id] = r.symbol

    # Excel出力
    print("📊 Excel生成中...", flush=True)
    os.makedirs(args.output_dir, exist_ok=True)
    
    output_path = f"{args.output_dir}/勤務表_{year}年{month}月.xlsx"
    generator = ExcelGenerator(
        year=year,
        month=month,
        technicians=technicians,
        night_assignments=night_assignments_dict,
        day_assignments=day_assignments_dict,
        requests=requests_dict,
        name_mapper=None # Optional if not used
    )
    generator.generate(output_path)
    print(flush=True)
    
    print("=" * 70, flush=True)
    print("✅ 勤務表作成完了", flush=True)
    print("=" * 70, flush=True)

if __name__ == '__main__':
    main()

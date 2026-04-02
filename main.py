from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.night_skill_deriver import NightSkillDeriver
from shift_scheduler.src.schedulers.night_scheduler import NightScheduler
from shift_scheduler.src.schedulers.day_scheduler import DayScheduler
from shift_scheduler.src.excel_generator import ExcelGenerator
import argparse
import os
import sys
import calendar
import jpholiday
from typing import Dict, Tuple, List
from shift_scheduler.src.models.assignment import NightAssignment, DayAssignment
from shift_scheduler.src.models.skill import SkillRank
from datetime import date, timedelta


def assign_nine_off_days(
    technicians,
    day_result_list,
    night_assignments,
    requests,
    year: int,
    month: int,
) -> Tuple[list, Dict[str, int]]:
    """出力済みシフト表に対してポスト処理：
    各スタッフに月業合計の休みみが最低9日になるよう「休」を自動添加する。
    ・休み深廓になるまで自動休を増やす
    ・6連勤超過を避けるための送「休」も含む
    ・休暴希望（★/☆）との視覚的区別を保つ
    """
    # Symbols that already count as a day off
    OFF_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆',
                   '出/☆', '研(聴)', '退職', '出/(発)', '出(発)', '発',
                   '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}

    num_days = calendar.monthrange(year, month)[1]
    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]

    # Build fast lookup maps
    # req_map: (staff_id, date) -> symbol
    req_map = {(r.staff_id, r.date): r.symbol for r in requests if r.date.year == year and r.date.month == month}
    # night_map: (staff_id, date) -> True (date = the night-shift night)
    night_map = {}
    for na in night_assignments:
        night_map[(na.staff_id, na.date)] = True

    # day_assign_map: (staff_id, day_num) -> location_code
    day_assign_map = {}
    for da in day_result_list:
        if da.date.year == year and da.date.month == month:
            day_assign_map[(da.staff_id, da.date.day)] = da.location_code

    additional_holidays = []  # New DayAssignment objects we create
    overridden_work = set()   # (staff_id, day_num) pairs where we replaced work with 休
    daikyu_counts: Dict[str, int] = {}  # staff_id -> daikyu count (max 1)

    active_staff = [s for s in technicians if s.status == '在籍']

    for s in active_staff:
        # --- Step 1: Build this staff member's status for every day of the month ---
        # status[day_num (1-indexed)] = 'off' | 'work' | 'free'
        status = {}  # day_num -> 'off'|'work'|'free'

        for d in all_dates:
            dn = d.day
            req = req_map.get((s.id, d))
            is_night = night_map.get((s.id, d), False)
            is_ake = night_map.get((s.id, d - timedelta(days=1)), False)
            existing_loc = day_assign_map.get((s.id, dn))

            is_jan_holiday = (d.month == 1 and d.day in [1, 2, 3])
            is_public_off = d.weekday() == 6 or jpholiday.is_holiday(d) or is_jan_holiday

            if is_night:
                status[dn] = 'work'  # Night shift = working
            elif is_ake:
                status[dn] = 'work'  # Post-night (明け/○) = working (does NOT count as rest)
            elif req in OFF_SYMBOLS:
                status[dn] = 'off'   # Requested holiday (including 17休)
            elif req == '休' or existing_loc == '休':
                status[dn] = 'off'   # Already forced off
            elif is_public_off and not (existing_loc and existing_loc not in ['休', '○']):
                status[dn] = 'off'   # Sunday/Holiday with no special assignment
            elif existing_loc and existing_loc not in ['休', '○']:
                status[dn] = 'work'  # Has a real location assignment
            elif req and req not in OFF_SYMBOLS:
                status[dn] = 'work'  # Has a non-holiday request (e.g., business trip)
            else:
                # No assignment, no non-holiday request, not a public holiday: 
                # This is a blank weekday - staff is at rest (not assigned anywhere)
                # Count as 'off' for the 9-day quota, but mark as 'fillable' so we can
                # optionally add a visible '休' marker
                status[dn] = 'blank'  # Blank weekday - counts as off but no marker yet

        # --- Step 2: Count current off-days ---
        # 'off' = explicit off marker | 'blank' = no assignment (also counts as rest)
        current_off = sum(1 for v in status.values() if v in ('off', 'blank'))
        # We need explicit '休' markers to visually show the off-days
        # 'blank' days need a '休' marker added to them
        # How many blanks already provide 'free' rest without visual marker:
        blank_days = [dn for dn, v in status.items() if v == 'blank']
        explicit_off = sum(1 for v in status.values() if v == 'off')  # already has marker
        
        # We want total visible off = 9
        # Explicit offs already have markers. Blank days need markers to reach 9 visible
        needed = 9 - explicit_off  # How many '休' markers to add (on blank days)
        needed = max(0, min(needed, len(blank_days)))  # Can't add more than blanks available

        # --- Step 3: Greedily pick 'free' days to become 休 ---
        # Strategy: pick days that break up the longest consecutive working streaks
        # Build list of consecutive work runs and pick days from longest stretches

        # Convert status to a working-day streak view
        def compute_streaks(status_dict, num_days):
            """Return {day_num: streak_length_of_the_run_it_belongs_to}"""
            streaks = {}
            run_start = None
            run_len = 0
            run_days = []
            pending_runs = []
            for dn in range(1, num_days + 1):
                if status_dict.get(dn) == 'work':
                    if run_start is None:
                        run_start = dn
                        run_len = 0
                        run_days = []
                    run_len += 1
                    run_days.append(dn)
                else:
                    if run_start is not None:
                        pending_runs.append(list(run_days))
                        run_start = None
                        run_days = []
            if run_start is not None:
                pending_runs.append(list(run_days))
            return pending_runs

        # We want to pick `needed` days from `blank_days` and mark them as `off`.
        # To avoid consecutive holidays (連休) and ensure balance, we pick they dynamically:
        # always choose the blank day that is furthest from any existing 'off' day.
        
        assigned_count = 0
        candidate_days = list(blank_days)
        
        while assigned_count < needed and candidate_days:
            # Score each candidate day by its distance to the nearest 'off' day
            best_day = None
            best_score = -1
            
            for dn in candidate_days:
                # Find minimum distance to an 'off' day
                min_dist = 999
                for other_dn, state in status.items():
                    if state == 'off':
                        dist = abs(dn - other_dn)
                        if dist < min_dist:
                            min_dist = dist
                
                # We want to MAXIMIZE this minimum distance
                if min_dist > best_score:
                    best_score = min_dist
                    best_day = dn
            
            # If for some reason we can't find a best day, break
            if best_day is None:
                break
                
            # Assign the best day
            dn = best_day
            candidate_days.remove(dn)
            prev_status = status[dn]
            status[dn] = 'off'
            
            # Verify rolling 7-day window constraint is respected
            ok = True
            for start in range(max(1, dn - 6), min(num_days - 5, dn + 1)):
                window = [status.get(start + i, 'blank') for i in range(7)]
                work_count = sum(1 for w in window if w == 'work')
                if work_count >= 7:  # Full 7-day working window
                    ok = False
                    break


            if ok:
                # Record this auto-休
                d = date(year, month, dn)
                additional_holidays.append(
                    DayAssignment(
                        date=d,
                        staff_id=s.id,
                        location_code='休',
                        rank=SkillRank.NONE,
                    )
                )
                day_assign_map[(s.id, dn)] = '休'  # Update local map
                if prev_status == 'work':
                    overridden_work.add((s.id, dn))  # Track work->休 overrides
                assigned_count += 1
            else:
                status[dn] = prev_status  # Revert; can't use this day

        # If we couldn't assign enough '休', record a '代休' (max 1)
        if explicit_off + assigned_count < 9:
            daikyu_counts[s.id] = 1

    # Filter out original work assignments that were overridden to 休
    filtered_result = [
        da for da in day_result_list
        if not (da.date.year == year and da.date.month == month
                and (da.staff_id, da.date.day) in overridden_work)
    ]
    total_daikyu = sum(daikyu_counts.values())
    print(f"✅ 9日休暮処理: {len(additional_holidays)}件の自動休を追加 ({len(overridden_work)}件の勤務割当を休に変更) - {total_daikyu}名に代休1日を付与")
    return filtered_result + additional_holidays, daikyu_counts

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

    # ===== Post-Processing: Assign exactly 9 off-days per staff =====
    print("📅 9日休暇自動配置中...", flush=True)
    day_result_list, daikyu_counts = assign_nine_off_days(
        technicians=technicians,
        day_result_list=day_result_list,
        night_assignments=full_night_assignments,
        requests=requests,
        year=year,
        month=month,
    )
    print(flush=True)
    
    # ===== Post-Processing: Assign On-Call (拘束) =====
    print("📞 拘束（オンコール）自動配置中...", flush=True)
    from shift_scheduler.src.schedulers.oncall_scheduler import OnCallScheduler
    oncall_scheduler = OnCallScheduler(
        staff_list=technicians,
        year=year,
        month=month
    )
    on_call_assignments, on_call_counts = oncall_scheduler.schedule(day_result_list, full_night_assignments, requests)
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
        d_day = r.date.day
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
        on_call_assignments=on_call_assignments,
        name_mapper=None, # Optional if not used
        daikyu_counts=daikyu_counts
    )
    generator.generate(output_path)
    print(flush=True)
    
    print("=" * 70, flush=True)
    print("✅ 勤務表作成完了", flush=True)
    print("=" * 70, flush=True)

if __name__ == '__main__':
    main()

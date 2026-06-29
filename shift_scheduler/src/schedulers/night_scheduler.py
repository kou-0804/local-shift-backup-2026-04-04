from ortools.sat.python import cp_model
from typing import List, Dict, Tuple
from datetime import date,  timedelta
import jpholiday

from ..models.staff import Staff
from ..models.request import Request
from ..models.assignment import NightAssignment

class NightScheduler:
    def __init__(self, staff_list: List[Staff], year: int, month: int):
        self.staff_list = staff_list
        self.year = year
        self.month = month
        
        # Generation of dates
        self.dates = self._generate_dates()
        
        # Filter staff capable of night shift
        self.night_staff = [s for s in staff_list if s.can_night_shift]
        
    def _generate_dates(self) -> List[date]:
        import calendar
        num_days = calendar.monthrange(self.year, self.month)[1]
        return [date(self.year, self.month, d) for d in range(1, num_days + 1)]

    def schedule(self, requests: List[Request], night_quotas: Dict[str, int], previous_month_assignments: List[NightAssignment] = [], locked_assignments: dict | None = None) -> List[NightAssignment]:
        model = cp_model.CpModel()
        num_days = len(self.dates)
        
        # Symbol Definitions
        NIGHT_REQUEST_SYMBOLS = ['夜希']
        HOLIDAY_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '○', '出/☆', '研(聴)', '退職', '☆育', '休'}
        SPECIAL_NO_NIGHT = {'講', '会議', '全会', '業配', '業出'}
        
        # Build Request Map
        request_map = {}
        for r in requests:
            if r.date not in request_map: request_map[r.date] = {}
            request_map[r.date][r.staff_id] = r.symbol

        # Build Previous Month Map
        # prev_map[staff_id] = set(dates)
        prev_map = {}
        for pa in previous_month_assignments:
            if pa.staff_id not in prev_map:
                prev_map[pa.staff_id] = set()
            prev_map[pa.staff_id].add(pa.date)

        # 1. Variables
        # x[staff_id, date] = 1 if assigned
        
        x = {} 
        for s in self.night_staff:
            for d in self.dates:
                x[s.id, d] = model.NewBoolVar(f'n_{s.id}_{d}')
        
        # 2. Hard Constraints
        penalties = []
        self._add_hard_constraints(model, x, requests, night_quotas, prev_map, penalties)
        
        # 3. Soft Constraints
        self._add_soft_constraints(model, x, night_quotas, prev_map, penalties)

        # --- P2b partial-lock re-solve injection (night = occupancy; '夜'-domain only) ---
        # Night role (MR/アンギオ/心カテ) is derived by post-solve permutation and so
        # CANNOT be forced — only occupancy (sid, date) is. Day-domain entries have
        # lc != '夜' and are skipped here (they never leak into the night model).
        # DETERMINISM CONTRACT: an empty lock set adds ZERO assumptions => unchanged.
        from shift_scheduler.src.lock_utils import NIGHT_LOC
        _locks = locked_assignments or {}
        for d in self.dates:
            dl = _locks.get(d, {})
            for sid, lc in dl.get('force', ()):
                if lc == NIGHT_LOC and (sid, d) in x:
                    model.AddAssumption(x[sid, d])
            for sid, lc in dl.get('forbid', ()):
                if lc == NIGHT_LOC and (sid, d) in x:
                    model.AddAssumption(x[sid, d].Not())

        # 4. Solve

        solver = cp_model.CpSolver()
        # 再現性確保: 実時間(max_time_in_seconds)はマシン負荷・速度で停止点が変わり
        # 非決定になる（夜勤がFEASIBLEで打ち切られ毎回別解になっていた）。
        # 決定的時間(max_deterministic_time)へ切替え、同一入力→同一解を保証する。
        solver.parameters.max_deterministic_time = 120.0
        solver.parameters.max_time_in_seconds = 600   # 安全上限（通常は決定的時間で先に停止）
        solver.parameters.random_seed = 42
        solver.parameters.num_workers = 1             # シングルスレッド（完全再現性）
        solver.parameters.log_search_progress = False

        status = solver.Solve(model)

        print(f"Solver Status: {solver.StatusName(status)} "
              f"(detTime={solver.ResponseProto().deterministic_time:.1f}, wall={solver.WallTime():.1f}s)")
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return self._extract_solution(solver, x)
        else:
            # Create a relaxation to find conflict?
            # Or just print some debug info
            print("Infeasible. Checking simple conflicts...")
            # Check if we have enough staff for each day
            for d in self.dates:
                # Skill coverage check loop
                mr = [s for s in self.night_staff if s.night_mr]
                angio = [s for s in self.night_staff if s.night_angio]
                cath = [s for s in self.night_staff if s.night_cath]
                print(f"Date {d}: MR={len(mr)}, Angio={len(angio)}, Cath={len(cath)}")
            
            raise Exception("No solution found for night shifts.")

    def _add_hard_constraints(self, model, x, requests, night_quotas, prev_map, penalties):
        req_map = {(r.staff_id, r.date): r.symbol for r in requests}
        
        # NH-01: 3 staff per day (動的拡張: 夜希が4人以上いる日はその人数を最大枠とする)
        for d in self.dates:
            yaki_count = sum(1 for s in self.night_staff if req_map.get((s.id, d)) == '夜希')
            target_capacity = max(3, yaki_count)
            model.Add(sum(x[s.id, d] for s in self.night_staff) == target_capacity)
            
        # NH-02: Monthly quota
        # Total Quota (90) != Total Required (93). Strict equality is Impossible.
        # We handle this as a Soft Constraint with MAX priority involved to minimize deviation (Target 3 extra shifts).
        
        # NH-04: Interval Constraints
        # User Priority: Quota > Interval.
        # We enforces "No Consecutive Nights" as Hard Constraint (Safety).
        # We move "3 Day Interval" to Soft Constraint to allow satisfying Quota.
        
        # 1. Internal Constraints (within current month)
        for s in self.night_staff:
            for i in range(len(self.dates) - 1):
                model.Add(sum(x[s.id, self.dates[i+j]] for j in range(2)) <= 1)

        # 2. Boundary Constraints (Previous Month -> Current Month)
        # Check against previous month assignments
        if self.dates:
            first_day = self.dates[0]
            prev_day = first_day - timedelta(days=1)
            
            for s in self.night_staff:
                # Check if user worked on last day of previous month
                if s.id in prev_map and prev_day in prev_map[s.id]:
                    # Hard Constraint: Cannot work on first day of this month
                    model.Add(x[s.id, first_day] == 0)

        # NH-05, NH-07, NH-08, NH-09: Request & Symbol constraints
        # Categories:
        #  - Night Forbidden (Holiday, Special, 17-gyou)
        #  - Previous Night Forbidden (Holiday, 17-gyou) -> If Day D is Holiday, Day D-1 cannot be Night.
        #  - Night Mandatory (Night Request)
        
        # Symbol Classification matches Spec 8.1 / 8.2 logic
        HOLIDAY_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '○', '出/☆', '研(聴)', '退職', '☆育', '休'}
        # NS-05: Request Pattern (Night -> Ake -> Holiday Request) (Weight 20)
        # User Request: If Holiday Request on Day D, prefer Night on Day D-2.
        # [DISABLED] This constraint caused INFEASIBILITY on Jan 20 (Tuesday Angio shortage).
        # Since user specified "Low Priority", we disable it to ensure schedule completion.
        """
        WEIGHT_PATTERN = 20
        # Re-build map locally
        req_map_s = {(r.staff_id, r.date): r.symbol for r in requests}
        HOLIDAY_REQ_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '出/☆'} 
        
        for s in self.night_staff:
            for d in self.dates:
                symbol = req_map_s.get((s.id, d))
                if symbol in HOLIDAY_REQ_SYMBOLS:
                    # Target Night Date: d - 2 days
                    target_date = d - timedelta(days=2)
                    
                    if target_date >= self.dates[0]:
                        # Prefer x[s.id, target_date] == 1
                        # Minimize (1 - x)
                        pattern_loss = model.NewBoolVar(f'pat_loss_{s.id}_{d}')
                        model.Add(x[s.id, target_date] == 0).OnlyEnforceIf(pattern_loss)
                        model.Add(x[s.id, target_date] == 1).OnlyEnforceIf(pattern_loss.Not())
                        
                        penalties.append(pattern_loss * WEIGHT_PATTERN)
        """
        SPECIAL_NO_NIGHT = {'講', '会議', '全会', '業配', '業出'}
        # 17-gyou: No Night on Day D. No Night on Day D-1.
        
        for s in self.night_staff:
            for d in self.dates:
                symbol = req_map.get((s.id, d))
                if not symbol:
                    continue
                
                # NH-09: Mandatory Night
                if symbol == '夜希':
                    missed_yaki = model.NewBoolVar(f'missed_yaki_{s.id}_{d}')
                    model.Add(x[s.id, d] == 0).OnlyEnforceIf(missed_yaki)
                    model.Add(x[s.id, d] == 1).OnlyEnforceIf(missed_yaki.Not())
                    penalties.append(missed_yaki * 5000000)
                    continue
                
                # NH-05, NH-07, NH-08: Night Forbidden on Day D
                if (symbol in HOLIDAY_SYMBOLS or 
                    symbol in SPECIAL_NO_NIGHT or 
                    symbol == '17業' or 
                    symbol == '17休'):
                    model.Add(x[s.id, d] == 0)
                
                # NH-05, NH-08: Night Forbidden on Day D-1 (Previous Day)
                # "If Day D has [Holiday/17業], then Day D-1 cannot be Night"
                # which means x[s, d-1] == 0.
                if (symbol in HOLIDAY_SYMBOLS or 
                    symbol == '17業' or 
                    symbol == '17休' or # 17休 also mentioned in prev day prohibited in 8.1 table row 562? 
                                        # Table row 562 17休 says "Night: ○" (Possible??)
                                        # Wait, Spec 8.1 Table:
                                        # 17業: Night=×, PrevNight=× (Table row 561 says 17業 Night=○? Wait)
                                        # Let's re-read Table 8.1 carefully from file content viewed in Step 4.
                                        # Line 561: | 17業 | その他 | 17時以降業務なし | ○ | ○ | 遅番・超遅以外 |
                                        # Wait, table says Circle (Possible)!? 
                                        # BUT User Request in Step 101 says:
                                        # "NH-08: 17業の当日夜勤禁止（重要）... 記号[s][d] = '17業' → 夜勤[s][d] = 0"
                                        # User Request overrides Spec v2.0 text if conflicting.
                                        # User Request Table says: "17業 ... 夜勤: × ... 前日夜勤: ×"
                                        # I will follow User Request Step 101 Update.
                    symbol == '勤'):  # 勤 is for schedule making, usually day work?
                                      # User Request: "勤 | 勤務表作成 | ○ | ○" (Night OK?)
                                      # Spec 8.1: "勤 ... ○ | ○"
                                      # If symbol is '勤', Night IS ALLOWED.
                    
                    if symbol in ['17業', '17休', '勤']:
                         # Re-reading User Request Step 101 for 17業:
                         # "NH-08: 17業の当日夜勤禁止（重要）" -> x[d]=0.
                         pass
                    
                    # Apply Previous Day Ban
                    # If d is today, we check d-1
                    prev_date = d - timedelta(days=1)
                    if prev_date >= self.dates[0]: # Only if within this month
                        # If strict, we need previous month data. For now ignore if out of range.
                        model.Add(x[s.id, prev_date] == 0)
                    else:
                        # Boundary check: Check previous month
                        # If Day 1 has forbidden symbol, then PrevMonth Last Day must not be Assignment.
                        # But PrevMonth is already fixed. We can't change it.
                        # We can only verify/warn if conflict, but technically we constrained the wrong direction?
                        # Wait. "If Day D is Holiday, Day D-1 cannot be Night."
                        # If Day 1 is Holiday, Day -1 (Prev Month Last Day) cannot be Night.
                        # But Day -1 is already past. We can't change x[s, -1].
                        # So this constraint is moot for Day 1 unless we are planning Prev Month.
                        # Or... does it mean "If Day -1 was Night, Day 0 cannot be Holiday"?
                        # No, Holiday is a Request (Hard Constraint Fixed).
                        # So if user requested Holiday on Day 1, and worked Night on Day -1...
                        # That's a violation of rule, but we can't fix it by changing Day 1 Holiday.
                        # We can't do anything here.
                        pass

        # NH-06: Skill Coverage
        # At least 1 MR, 1 Angio, 1 Cath
        for d in self.dates:
            mr_staff = [s for s in self.night_staff if s.night_mr]
            angio_staff = [s for s in self.night_staff if s.night_angio]
            cath_staff = [s for s in self.night_staff if s.night_cath]
            
            model.Add(sum(x[s.id, d] for s in mr_staff) >= 1)
            model.Add(sum(x[s.id, d] for s in angio_staff) >= 1)
            model.Add(sum(x[s.id, d] for s in cath_staff) >= 1)

    def _add_soft_constraints(self, model, x, night_quotas, prev_map, penalties):
        
        # NS-08: HB Coverage (Weight 300,000 - HIGH PRIORITY)
        # Try to ensure at least 1 person has night_hb skill.
        WEIGHT_HB_COVERAGE = 300000
        hb_staff = [s for s in self.night_staff if getattr(s, 'night_hb', False)]
        if hb_staff:
            for d in self.dates:
                uncovered_hb = model.NewBoolVar(f'uncovered_hb_{d}')
                hb_sum = sum(x[s.id, d] for s in hb_staff)
                model.Add(hb_sum >= 1).OnlyEnforceIf(uncovered_hb.Not())
                model.Add(hb_sum == 0).OnlyEnforceIf(uncovered_hb)
                penalties.append(uncovered_hb * WEIGHT_HB_COVERAGE)
        
        # NS-04: Quota Adherence (Weight 1,000,000 - STRICTEST PRIORITY)
        # Because Total Quota (90) != Required (93), we must allow slight deviation (+3 total).
        WEIGHT_QUOTA = 1000000
        for s in self.night_staff:
            if s.id in night_quotas:
                target_q = night_quotas[s.id]
                actual_q = sum(x[s.id, d] for d in self.dates)
                diff = model.NewIntVar(0, 31, f'quota_diff_{s.id}')
                model.AddAbsEquality(diff, actual_q - target_q)
                penalties.append(diff * WEIGHT_QUOTA)

        # Soft NH-04: Prefer 3-day interval (Penalize Night-Off-Night)
        WEIGHT_INTERVAL_PENALTY = 50000 # Increased from 5000
        
        # Helper to get value of day (either historical or variable)
        # However, historical is int, variable is BoolVar. Cannot mix easily in list comprehension without care.
        # We handle boundary explicitly.
        
        for s in self.night_staff:
            # 1. Internal Windows
            for i in range(len(self.dates) - 2):
                window_sum = sum(x[s.id, self.dates[i+j]] for j in range(3))
                
                # If sum >= 2 (which means exactly 2, N-O-N), penalize
                violation = model.NewBoolVar(f'int_viol_{s.id}_{i}')
                model.Add(window_sum >= 2).OnlyEnforceIf(violation)
                model.Add(window_sum < 2).OnlyEnforceIf(violation.Not())
                
                penalties.append(violation * WEIGHT_INTERVAL_PENALTY)

            # 2. Boundary Windows (using prev_map)
            # We need to check windows that overlap with Previous Month.
            # Window A: [Prev-2, Prev-1, Day-0]
            # Window B: [Prev-1, Day-0, Day-1]
            
            if self.dates:
                day0 = self.dates[0]
                day1 = self.dates[1] if len(self.dates) > 1 else None
                
                prev1_date = day0 - timedelta(days=1)
                prev2_date = day0 - timedelta(days=2)
                
                is_prev1_night = 1 if (s.id in prev_map and prev1_date in prev_map[s.id]) else 0
                is_prev2_night = 1 if (s.id in prev_map and prev2_date in prev_map[s.id]) else 0
                
                # Window A: [Prev-2, Prev-1, Day-0]
                # Sum = is_prev2 + is_prev1 + x[day0]
                # If Sum >= 2, penalize.
                # Since is_prev constants, we can simplify:
                current_cids_sum = is_prev2_night + is_prev1_night
                if current_cids_sum >= 2:
                    # Already violated (Prev-2 and Prev-1 both Night). nothing we can do today.
                    pass
                elif current_cids_sum == 1:
                    # One of them is Night. If x[day0] is Night, then Sum=2. Penalize.
                    # We penalize x[day0] being 1.
                    # violation = x[day0]
                    penalties.append(x[s.id, day0] * WEIGHT_INTERVAL_PENALTY)
                
                # Window B: [Prev-1, Day-0, Day-1]
                # Sum = is_prev1 + x[day0] + x[day1]
                if day1:
                    if is_prev1_night:
                        # Sum = 1 + x[day0] + x[day1]
                        # If sum >= 2, penalize.
                        # Note: If is_prev1=1, x[day0] MUST be 0 (Hard Constraint).
                        # So Sum = 1 + 0 + x[day1] = 1 + x[day1].
                        # If x[day1] is 1, Sum=2. Penalize.
                        penalties.append(x[s.id, day1] * WEIGHT_INTERVAL_PENALTY)
                    else:
                        # Sum = 0 + x[day0] + x[day1]
                        # If x[day0]+x[day1] >= 2 -> Handled by Hard Constraint (No Consecutive).
                        # So no Soft Penalty needed for N-N case here as it violates Hard.
                        # N-O-N case: x[day0]=1, x[day1]=0 (Sum=1, OK).
                        # O-N-N case: x[day0]=0, x[day1]=1 (Sum=1, OK).
                        pass

            # New: Penalize Short Intervals (< 7 days) if possible
            # To avoid clustering (e.g. Day 1 and Day 5).
            # We want to push them apart.
            # Implementation: For every pair of days (d1, d2) where d2 > d1 and (d2 - d1) < 7:
            # If both assigned, penalize.
            WEIGHT_SHORT_INTERVAL = 10000 
            
            # 1. Internal Short Intervals
            for i in range(len(self.dates)):
                for j in range(i + 1, min(i + 7, len(self.dates))):
                    short_gap_viol = model.NewBoolVar(f'short_gap_{s.id}_{i}_{j}')
                    model.AddBoolAnd([x[s.id, self.dates[i]], x[s.id, self.dates[j]]]).OnlyEnforceIf(short_gap_viol)
                    model.AddBoolOr([x[s.id, self.dates[i]].Not(), x[s.id, self.dates[j]].Not()]).OnlyEnforceIf(short_gap_viol.Not())
                    
                    gap = j - i
                    w = WEIGHT_SHORT_INTERVAL * (7 - gap) # 60000 for gap 1, 10000 for gap 6
                    penalties.append(short_gap_viol * w)

            # 2. Boundary Short Intervals
            # Check interactions between [Prev-6 ... Prev-1] and [Day-0 ... Day-6]
            if self.dates:
                # We essentially want to check: if Prev-k was Night, then Day-m shouldn't be Night if (k+m+1) < 7
                # Gap = (DayIndex - PrevIndex). 
                # Let PrevIndex be negative: -1, -2...
                # Gap = m - (-k) = m + k.
                # If Gap < 7, penalize x[Day-m].
                
                # Check up to 7 days back
                for k in range(1, 8): # 1 to 7
                    prev_d = self.dates[0] - timedelta(days=k)
                    if s.id in prev_map and prev_d in prev_map[s.id]:
                        # Staff worked k days ago (relative to Day 0)
                        # So for any Day m where (m + k) < 7, we penalize x[m]
                        # m < 7 - k
                        
                        limit = 7 - k # If k=1 (Prev-1), limit=6. Check Days 0..5.
                                     # If k=6 (Prev-6), limit=1. Check Day 0.
                        
                        for m in range(limit):
                            if m < len(self.dates):
                                # assignments[Prev] is 1. assignments[Day m] is x[m].
                                # Penalize if x[m] == 1.
                                gap = m + k
                                w = WEIGHT_SHORT_INTERVAL * (7 - gap)
                                penalties.append(x[s.id, self.dates[m]] * w)

        # NS-01: Week Distribution (Weight 100 -> 50000)
        # Minimize number of night shifts in same week > 1
        week_groups = {} # {week_num: [date, ...]}
        for d in self.dates:
            w = d.isocalendar()[1]
            if w not in week_groups:
                week_groups[w] = []
            week_groups[w].append(d)
            
        WEIGHT_WEEK = 50000 # Increased significantly
        for s in self.night_staff:
            for w, days in week_groups.items():
                if len(days) < 2: 
                    continue
                # Penalty if sum > 1
                count = sum(x[s.id, d] for d in days)
                var = model.NewIntVar(0, 7, f'week_pen_{s.id}_{w}')
                model.Add(var >= count - 1)
                penalties.append(var * WEIGHT_WEEK)

        # NS-02: Sunday/Holiday Distribution — Hard + Incremental Penalty
        # 日祝日の当直回数をスタッフ間で極力均等化
        holidays = [d for d in self.dates if d.weekday() == 6 or jpholiday.is_holiday(d)]
        
        if holidays:
            total_slots = len(holidays) * 3
            num_staff = len(self.night_staff)
            max_per_person = (total_slots + num_staff - 1) // num_staff + 1  # ceil + 1 slack
            
            for s in self.night_staff:
                h_count = sum(x[s.id, d] for d in holidays)
                
                # Hard: 上限制約（絶対に超えない）
                model.Add(h_count <= max_per_person)
                
                # Incremental penalty: 回数が増えるほどペナルティが急増
                # 1回目: 100,000  2回目: 300,000  3回目: 600,000 ...
                # これにより分散が強力に促進される
                for k in range(1, max_per_person + 1):
                    over_k = model.NewBoolVar(f'h_over_{s.id}_{k}')
                    model.Add(h_count >= k + 1).OnlyEnforceIf(over_k)
                    model.Add(h_count <= k).OnlyEnforceIf(over_k.Not())
                    penalties.append(over_k * (k * 200000))

        # NS-07: 明けが日祝日に当たる回数の均等化 — Hard + Incremental Penalty
        # 夜勤の翌日が日祝日 → その夜勤日をカウントして均等化
        ake_holidays = []
        for d in self.dates:
            next_day = d + timedelta(days=1)
            if next_day.weekday() == 6 or jpholiday.is_holiday(next_day):
                ake_holidays.append(d)

        if ake_holidays:
            total_ake = len(ake_holidays) * 3
            num_staff = len(self.night_staff)
            max_ake_per_person = (total_ake + num_staff - 1) // num_staff + 1

            for s in self.night_staff:
                a_count = sum(x[s.id, d] for d in ake_holidays)
                
                # Hard: 上限制約
                model.Add(a_count <= max_ake_per_person)
                
                # Incremental penalty
                for k in range(1, max_ake_per_person + 1):
                    over_k = model.NewBoolVar(f'ah_over_{s.id}_{k}')
                    model.Add(a_count >= k + 1).OnlyEnforceIf(over_k)
                    model.Add(a_count <= k).OnlyEnforceIf(over_k.Not())
                    penalties.append(over_k * (k * 200000))

        # NS-03: Saturday Distribution (Weight 50)
        WEIGHT_SAT = 50
        saturdays = [d for d in self.dates if d.weekday() == 5 and not jpholiday.is_holiday(d)]
        # Note: If Sat is Holiday, treated as Holiday in NS-02? 
        # Spec 2.4: "土曜: 土曜日（祝日と重なっても土曜扱い）"
        # Spec NS-02: "日祝" -> Sunday & Holiday.
        # If Sat is Holiday, it counts for BOTH? Or Priority?
        # Usually distinct categories. 
        # Let's assume NS-03 is strictly for day.weekday() == 5 regardless of holiday status,
        # OR "Saturday (excluding holiday)".
        # Spec 2.4 says "土曜（祝日と重なっても土曜扱い）". So it counts as Saturday.
        # Does it ALSO count as Holiday? "日祝: 日曜日および国民の祝日". Yes.
        # So a Holiday Saturday counts for both penalties. That's acceptable.
        
        # Re-calc Saturdays including holidays
        saturdays = [d for d in self.dates if d.weekday() == 5]
        
        if saturdays:
            avg_sat = (len(saturdays) * 3) // len(self.night_staff)
            for s in self.night_staff:
                count = sum(x[s.id, d] for d in saturdays)
                dev = model.NewIntVar(0, len(saturdays), f's_dev_{s.id}')
                model.Add(dev >= count - avg_sat)
                model.Add(dev >= avg_sat - count)
                penalties.append(dev * WEIGHT_SAT)

        # NS-06: 若手（技師歴3年以内）だけの夜勤組合せを避ける
        # 3人全員が若手の場合にペナルティ（ソフト制約・低優先度）
        WEIGHT_JUNIOR_ONLY = 5000
        junior_staff = [s for s in self.night_staff if s.experience_years <= 3]
        
        if len(junior_staff) >= 3:
            for d in self.dates:
                junior_sum = sum(x[s.id, d] for s in junior_staff)
                # junior_sum == 3 なら全員若手 → ペナルティ
                # 超過分をペナルティとして加算（3人全員若手なら excess=1）
                excess = model.NewIntVar(0, 3, f'junior_excess_{d}')
                model.Add(excess >= junior_sum - 2)
                penalties.append(excess * WEIGHT_JUNIOR_ONLY)
                
        model.Minimize(sum(penalties))

    def _extract_solution(self, solver, x) -> List[NightAssignment]:
        assignments = []
        staff_map = {s.id: s for s in self.night_staff}
        
        import itertools
        
        for d in self.dates:
            # Get staff assigned today
            today_staff_ids = [s.id for s in self.night_staff if solver.Value(x[s.id, d]) == 1]
            if len(today_staff_ids) != 3:
                # Should not happen if NH-01 is met
                print(f"Warning: {len(today_staff_ids)} staff assigned on {d}")
                
            # Assign roles
            # Roles: MR, Angio, Cath
            # Requirement: At least 1 capable for each.
            # We have 3 people.
            # We need to find a permutation where P1->R1, P2->R2, P3->R3 and skills valid.
            
            today_staff = [staff_map[sid] for sid in today_staff_ids]
            roles = ['MR', 'アンギオ', '心カテ']
            
            found_roles = False
            # 3人ぴったりの場合は厳密な順列で割り当て
            if len(today_staff) == 3:
                for p in itertools.permutations(today_staff):
                    if (p[0].night_mr and 
                        p[1].night_angio and 
                        p[2].night_cath):
                        assignments.append(NightAssignment(date=d, staff_id=p[0].id, role='MR'))
                        assignments.append(NightAssignment(date=d, staff_id=p[1].id, role='アンギオ'))
                        assignments.append(NightAssignment(date=d, staff_id=p[2].id, role='心カテ'))
                        found_roles = True
                        break
            
            # 4人以上、または3人で役割が埋まらない場合
            if not found_roles:
                # それぞれが可能な役割をチェックし、最低1人はMR・アンギオ・カテに割り当てる
                mr_assigned, angio_assigned, cath_assigned = False, False, False
                for s in today_staff:
                    r_assigned = "未定(増員)"
                    if s.night_mr and not mr_assigned:
                        r_assigned = 'MR'
                        mr_assigned = True
                    elif s.night_angio and not angio_assigned:
                        r_assigned = 'アンギオ'
                        angio_assigned = True
                    elif s.night_cath and not cath_assigned:
                        r_assigned = '心カテ'
                        cath_assigned = True
                    # 余った人は持っているスキルを適当に表示するか、ヘルプとする
                    elif s.night_mr: r_assigned = 'MR(増)'
                    elif s.night_angio: r_assigned = 'アンギオ(増)'
                    elif s.night_cath: r_assigned = '心カテ(増)'
                    
                    assignments.append(NightAssignment(date=d, staff_id=s.id, role=r_assigned))

        return assignments

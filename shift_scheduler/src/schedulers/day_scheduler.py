from ortools.sat.python import cp_model
from typing import List, Dict, Tuple, Optional
from datetime import date, timedelta
import jpholiday

from ..models.staff import Staff
from ..models.location import Location
from ..models.request import Request
from ..models.skill import SkillRank
from ..models.rule import SpecialRule
from ..models.power_balance import PowerBalance
from ..models.assignment import DayAssignment, NightAssignment

class DayScheduler:
    def __init__(self, staff_list: List[Staff], locations: List[Location], rules: List[SpecialRule], 
                 skills: Dict[str, Dict[str, SkillRank]], pb_rules: List[PowerBalance], year: int, month: int):
        self.staff_list = staff_list
        self.locations = locations
        self.rules = rules
        self.skills = skills
        self.pb_rules = pb_rules
        self.year = year
        self.month = month
        self.dates = self._generate_dates()
        self.year = year
        self.month = month
        self.dates = self._generate_dates()
        
        # Pre-calc MRI-only staff
        self.mri_only_staff = set()
        mri_locs = {'病院MR', 'クMR', 'M遅'}
        ignore_locs = {'出', '超遅', 'ク遅', '遅番', '勤務表作成'}
        for s in self.staff_list:
            has_mri = False
            has_other = False
            for l, r in self.skills.get(s.id, {}).items():
                if r.value > SkillRank.NONE.value:
                    if l in mri_locs:
                        has_mri = True
                    elif l not in ignore_locs:
                        has_other = True
            if has_mri and not has_other:
                self.mri_only_staff.add(s.id)
        
    def _generate_dates(self) -> List[date]:
        import calendar
        num_days = calendar.monthrange(self.year, self.month)[1]
        return [date(self.year, self.month, d) for d in range(1, num_days + 1)]

    def schedule(self, 
                 requests: List[Request], 
                 night_assignments: List[NightAssignment]) -> List[DayAssignment]:
        
        all_assignments = []
        assignment_history = [] # List of {staff_id: location_code} per day
        
        # Track cumulative counts for Fairness (Ultra-Late, Portable, MG, ク遅, M遅)
        # {staff_id: {'超遅': 0, 'ポ': 0, 'MG': 0, 'ク遅': 0, 'M遅': 0}}
        assignment_counts = {s.id: {} for s in self.staff_list}
        
        # Track consecutive working days for 6-day limit (legacy fallback)
        consecutive_work_days = {s.id: 0 for s in self.staff_list}
        
        # Pre-process requests and night shifts for fast lookup
        req_map = {(r.staff_id, r.date): r.symbol for r in requests}
        
        night_map = {} # (staff_id, date) -> True
        for na in night_assignments:
            night_map[(na.staff_id, na.date)] = True
            
        # Day-by-Day Scheduling Loop
        for d in self.dates:
            print(f"Scheduling Day: {d}")
            prev_assignments = assignment_history[-1] if assignment_history else {}
            
            day_assignments = self._schedule_one_day(d, req_map, night_map, prev_assignments, assignment_counts, consecutive_work_days)
            all_assignments.extend(day_assignments)
            
            # Record history
            current_day_map = {a.staff_id: a.location_code for a in day_assignments}
            assignment_history.append(current_day_map)
            
            # Update cumulative counts
            for a in day_assignments:
                c = assignment_counts[a.staff_id]
                c[a.location_code] = c.get(a.location_code, 0) + 1
            
            # Update consecutive work days
            for s in self.staff_list:
                loc = current_day_map.get(s.id)
                # Check target day for night shift
                is_night_today = night_map.get((s.id, d))
                # Check previous day for ake (post-night)
                is_ake_today = night_map.get((s.id, d - timedelta(days=1)))
                
                is_working_day = False
                
                req_symbol = req_map.get((s.id, d))
                is_working_req = False
                if req_symbol and req_symbol not in ['休', '○', '★', '★連', '☆', '☆小', '☆デ', '◆', '退職']:
                    is_working_req = True
                
                if is_night_today or is_ake_today or is_working_req:
                    is_working_day = True # Night, Ake, and Working Requests definitely count as working instances
                elif loc and loc not in ['休', '○']:
                    is_working_day = True # Normal day assignment
                    
                if is_working_day:
                    consecutive_work_days[s.id] += 1
                else:
                    consecutive_work_days[s.id] = 0
            
        return all_assignments

    def _schedule_one_day(self, 
                          current_date: date, 
                          req_map: Dict[Tuple[str, date], str], 
                          night_map: Dict[Tuple[str, date], bool],
                          prev_assignments: Dict[str, str],
                          assignment_counts: Dict[str, Dict[str, int]],
                          consecutive_work_days: Dict[str, int]) -> List[DayAssignment]:
        
        model = cp_model.CpModel()
        weekday = current_date.weekday() # 0=Mon, 6=Sun

        # 1. Identify Active Locations and Required Headcount
        
        # Holiday Logic: Jan 1-3 or standard holidays
        is_jan_holiday = (current_date.month == 1 and current_date.day in [1, 2, 3])
        is_holiday = is_jan_holiday or jpholiday.is_holiday(current_date) or weekday == 6
        
        target_locations = []
        location_needs = {}
        
        if is_holiday:
            # Holiday Mode: Only '出' (Day Shift) required.
            shu_loc = next((l for l in self.locations if l.code == '出'), None)
            if shu_loc:
                target_locations.append(shu_loc)
                location_needs['出'] = 2 # Reference script specifies 2 people
        else:
            for loc in self.locations:
                if not loc.is_active: 
                    
                    continue
                req = loc.get_required_count(weekday)
                if req > 0:
                    target_locations.append(loc)
                    location_needs[loc.code] = req
                
        # Apply Special Rule Overrides to Required Counts & Active Locations
        # Optimization: We loop rules early to adjust 'location_needs'
        
        current_week_num = (current_date.day - 1) // 7 + 1
        
        # We need to map rule to location
        # Filter rules applicable today
        active_rules = []
        for rule in self.rules:
             # Check Weekday
            if rule.target_weekday is not None and rule.target_weekday != weekday:
                continue
            # Check Week Num
            if rule.target_week is not None and rule.target_week != current_week_num:
                continue
            active_rules.append(rule)

        # Only apply rules on non-holidays to strict enforcement of "Only '出'"
        if not is_holiday:
            for rule in active_rules:
                # If rule has required_count, it overrides master
                if rule.required_count > 0:
                    # Update location_needs
                    if rule.location_code not in location_needs:
                        # If strictly new location, we might need to add to target_locations
                        # Find location obj
                        loc_obj = next((l for l in self.locations if l.code == rule.location_code), None)
                        if loc_obj:
                            target_locations.append(loc_obj)
                            location_needs[rule.location_code] = rule.required_count
                    else:
                        # Prevent SR-08 and SR-09 from overwriting the Saturday master requirement (3) with (6/4)
                        if weekday == 5 and rule.location_code in ['病CT', 'CT']:
                            pass # Keep the location master data (3)
                        else:
                            location_needs[rule.location_code] = rule.required_count

            # Clinic Holiday: 3rd Saturday -> All Clinic locations closed
            # Clinic Codes: 'クMR', 'ク', 'DR' (Confirmed via Master)
            # Weekday 5 = Sat. Week 3 = 3rd occurrence.
            if weekday == 5 and current_week_num == 3:
                 clinic_codes = ['クMR', 'ク', 'DR', 'CT', 'MG', 'ク遅', 'M遅']
                 # Remove from needs
                 for c in clinic_codes:
                     if c in location_needs:
                         del location_needs[c]
                 # Remove from target_locations
                 target_locations = [l for l in target_locations if l.code not in clinic_codes]

        # 2. Identify Available Staff
        # - Status == '在籍'
        # - Not 'retired' (退職) request
        # - Not 'holiday' request (★, ☆, ...)
        # - Not Previous Day Night Shift (DH-05)
        
        HOLIDAY_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '○', '出/☆', '研(聴)', '退職',
                           '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)',
                           '研(座)', '研(役)', '出/(役)'}
        # '○' is Night Shift End (明け) -> Treated as Holiday usually? 
        # Spec says "○ | 夜勤明け | × | × | ×" (Day: ×) -> So Yes, treated as Holiday/Off.
        
        # Special symbols that enforce specific assignment (DH-07)
        # Map Request Symbol -> Location Code
        FORCED_LOC_MAP = {
            '講': '講',
            '会議': '会議',
            '全会': '全会',
            '業配': '業配',
            '業出': '業出',
            '勤': '勤務表作成', 
            '出': '出',
            '出/講': '出/講'
        }
        
        female_gyohai_wed = 0
        gyohai_has_veteran = False
        
        # Pre-process Forced Requests to adjust Location Needs
        for s in self.staff_list:
            if s.status != '在籍': continue
            p_req = req_map.get((s.id, current_date))
            
            if weekday == 2 and p_req == '業配' and s.gender.value == '女':
                female_gyohai_wed += 1
                if int(s.experience_years) >= 6:
                    gyohai_has_veteran = True
            
            if p_req in FORCED_LOC_MAP:
                target_loc_code = FORCED_LOC_MAP[p_req]
                
                # Check if this location exists in self.locations
                loc_obj = next((l for l in self.locations if l.code == target_loc_code), None)
                if loc_obj:
                    # Increment need
                    if target_loc_code not in location_needs:
                         location_needs[target_loc_code] = 0
                         # Should we add to target_locations if not present?
                         # distinct from active_locations check?
                         # Yes, if we need to assign someone here, it must be a target.
                         if loc_obj not in target_locations:
                             target_locations.append(loc_obj)
                             
                    location_needs[target_loc_code] += 1
                    
        # Deduct Wednesday female Gyohai from 'ク' needs
        if female_gyohai_wed > 0 and 'ク' in location_needs:
            location_needs['ク'] = max(0, location_needs['ク'] - female_gyohai_wed)

        # 17 constraints (DH-08, 09, 10)
        # '17業', '17休', 'SameDayNight' -> No Late Shifts
        LATE_LOCATIONS = {'遅番', '超遅'} 
        
        available_staff = []
        staff_req_symbol = {}
        
        prev_date = current_date - timedelta(days=1)
        two_days_ago = current_date - timedelta(days=2) # Req 4 Logic
        
        forced_holidays = []

        for s in self.staff_list:
            if s.status != '在籍':
                continue
            
            # Calculate unavoidable future consecutive work days due to Night/Ake/Requests
            forced_future = 0
            for offset in range(1, 10):
                check_d = current_date + timedelta(days=offset)
                is_n = night_map.get((s.id, check_d))
                is_a = night_map.get((s.id, check_d - timedelta(days=1)))
                
                is_working_req = False
                req_symbol = req_map.get((s.id, check_d))
                if req_symbol and req_symbol not in ['休', '○', '★', '★連', '☆', '☆小', '☆デ', '◆', '退職']:
                    # If there's a request and it's not a holiday, it's a forced working day
                    is_working_req = True
                
                if is_n or is_a or is_working_req:
                    forced_future += 1
                else:
                    break # Reached a day where they *could* theoretically rest
            
            # 6日連続勤務後は強制休暇（連勤最大6日）
            # もし「今の連勤数」＋「今日働くとしたら(1)」＋「避けられない未来の連勤数(forced_future)」が6を超えるなら、
            # 今日を「休」にして連勤をリセットしなければならない。
            c_days = consecutive_work_days.get(s.id, 0)
            
            if c_days >= 6 or (c_days + 1 + forced_future > 6):
                p_req_check = req_map.get((s.id, current_date))
                if p_req_check is None:
                    # 予定申請がない場合のみ強制休暇
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='休', rank=SkillRank.NONE))
                    continue
                # 予定申請がある場合は連勤制限を適用せず、予定申請を優先する
                
            # Check Previous Night (DH-05)
            if night_map.get((s.id, prev_date)):
                continue
                
            p_req = req_map.get((s.id, current_date))
            
            # Req 4: Enforce Holiday after Post-Night
            if night_map.get((s.id, two_days_ago)):
                # If no request (p_req is None), FORCE Holiday
                if p_req is None:
                    # Create explicit assignment '休'
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='休', rank=SkillRank.NONE))
                    continue
            
            if p_req in HOLIDAY_SYMBOLS:
                continue
                
            # NEW LOGIC: Ishikawa 4th Tuesday PET Assignment
            if s.id == 'T002' and current_date.weekday() == 1 and 22 <= current_date.day <= 28:
                if not night_map.get((s.id, current_date)):
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='PET', rank=SkillRank.NONE))
                    continue
                
            staff_req_symbol[s.id] = p_req
            available_staff.append(s)

        # 3. Create Variables x[staff_id, loc_code]
        x = {}
        fairness_penalties = []
        maximization_objective = [] # Req 2
        next_date = current_date + timedelta(days=1) # Req 3
        
        for s in available_staff:
            s_skills = self.skills.get(s.id, {})
            p_req = staff_req_symbol.get(s.id)
            
            # Constraints for Late/MG bans
            is_night_today = night_map.get((s.id, current_date))
            is_night_tomorrow = night_map.get((s.id, next_date)) # Req 3
            
            ban_late = False
            ban_mg_po = False
            
            if p_req == '17業': # DH-08
                ban_late = True
                ban_mg_po = True
            elif p_req == '17休': # DH-09
                ban_late = True
            elif is_night_today: # DH-10 + User Request (Night Day -> No MG/Po)
                ban_late = True
                ban_mg_po = True # User: "夜勤の日はポ、MGは日勤ではだめ"
            
            # Gender Constraint DH-06
            is_male = (s.gender.value == '男') 
            
            for loc in target_locations:
                l_code = loc.code
                
                # DH-07: Forced Location Check
                if p_req in FORCED_LOC_MAP:
                    target_loc = FORCED_LOC_MAP[p_req]
                    # If this is the target location, Must Assign (1 if possible)
                    # If this is NOT the target location, Must NOT Assign (0)
                    
                    if l_code == target_loc:
                        # Force assignment
                        x[s.id, l_code] = model.NewBoolVar(f'x_{s.id}_{l_code}')
                        model.Add(x[s.id, l_code] == 1)
                    else:
                        # Cannot work elsewhere
                        pass # Do not create variable = effectively 0
                    continue
                
                # If p_req is None or normal
                # DH-02: Skill Check & Rank Rules (Refined)
                rank = s_skills.get(l_code, SkillRank.NONE)
                if rank == SkillRank.NONE:
                    continue
                
                # Specialized Rank Rules
                # DH-02: Skill
                if l_code not in s_skills:
                    continue
                if s_skills[l_code] in [SkillRank.NONE, '-', '']:
                    continue
                # HB: Aランク必須
                if l_code == 'HB' and rank < SkillRank.A:
                    continue
                # アンギオ: Bランク以上
                if l_code == 'ア' and rank < SkillRank.B:
                    continue
                
                # Seisa (精): Wed/Fri -> Rank A. Others -> Rank B (Exclude Rank A).
                if l_code == '精':
                    # Weekday 2=Wed, 4=Fri.
                    if weekday in [2, 4]:
                        if rank < SkillRank.A: continue
                    else:
                        # User Request: "Others -> Rank B or lower"
                        # This means we Allow B, C, D. We only Exclude A.
                        # Also must exclude NONE.
                        if rank == SkillRank.A: continue
                        if rank == SkillRank.NONE: continue
                
                # Cath stays at B+ unless specified (IVR standard)
                if l_code == '心' and rank < SkillRank.B:
                    continue

                # Ultra Late ('超遅') / Clinic Late ('ク遅') / MRI Late ('M遅'): 翌日夜勤なら配置不可
                if l_code in ['超遅', 'ク遅', 'M遅']:
                     # Req 3: Ban if next day is Night
                     if is_night_tomorrow:
                         continue

                # DH-06: Gender
                if loc.gender_constraint == '女性のみ' and s.gender.value == '男':
                    if s.id == 'T014' and l_code == 'ク' and current_date.day == 21: print("Skipped T014 due to gender")
                    continue
                    
                # DH-08,09,10: Late/MG Ban
                if ban_late and l_code in ['遅番', '超遅', 'ク遅', 'M遅']:
                    if s.id == 'T014' and l_code == 'ク' and current_date.day == 21: print("Skipped T014 due to late ban")
                    continue
                if ban_mg_po and l_code in ['MG', 'ポ']:
                    if s.id == 'T014' and l_code == 'ク' and current_date.day == 21: print("Skipped T014 due to MG ban")
                    continue
                
                if s.id == 'T014' and l_code == 'ク' and current_date.day == 21: print("T014 'ク' is ADDED TO x!")
                x[s.id, l_code] = model.NewBoolVar(f'x_{s.id}_{l_code}')
                
                # Maximization term (Req 2)
                base_score = 10000
                if s.id in self.mri_only_staff and l_code in ['病院MR', 'クMR', 'M遅']:
                    base_score = 500000  # Massive bonus to prioritize MRI-only staff
                maximization_objective.append(x[s.id, l_code] * base_score)

                # Soft Constraint for Fairness (Equalize Counts)
                # Equalize ALL locations across staff to prevent bias
                count = assignment_counts[s.id].get(l_code, 0)
                if count > 0:
                    # M遅の均等化を特に強める（ペナルティの重みを大幅に増やす）
                    weight = 10000 if l_code == 'M遅' else 20
                    fairness_penalties.append(x[s.id, l_code] * (count * weight))

                # Special Monthly Bonus Rule for Ono (T014) and Kawana (T026) -> strictly 6 'ク' assignments
                if s.id in ['T014', 'T026'] and l_code == 'ク':
                    if count < 6:
                        # Massive bonus to forcefully pick them for 'ク' until quota hits 6
                        if (s.id, l_code) in x:
                            maximization_objective.append(x[s.id, l_code] * 500000)
                            if s.id == 'T014': print(f"DEBUG: Adding 500k to T014 on Day {current_date.day}. Current count={count}")
                    else:
                        # Hard ban once they hit 6
                        if (s.id, l_code) in x:
                            model.Add(x[s.id, l_code] == 0)


        # 4. Hard Constraints
        
        # DH-01: One person <= 1 location (for those not already forced)
        
        # Ono / Kawana Special Ban: Cannot both work 'ク' on the same day
        if ('T014', 'ク') in x and ('T026', 'ク') in x:
            model.Add(x['T014', 'ク'] + x['T026', 'ク'] <= 1)
            
        ultra_late_next_day_penalties = []
        for s in available_staff:
            vars_s = [x[s.id, l.code] for l in target_locations if (s.id, l.code) in x]
            if vars_s:
                model.Add(sum(vars_s) <= 1)
                
            # Check Previous Assignment for Ultra-Late ('超遅') Logic
            # User: "Next Day ideally Off. If Work, next is '入' or 'MG' (Female)"
            if s.id in prev_assignments and prev_assignments[s.id] == '超遅':
                
                # Exemption: If staff has a Forced Request (e.g. Meeting), strict '入' placement is overruled.
                if staff_req_symbol.get(s.id) in FORCED_LOC_MAP:
                    pass
                else:
                    # Soft Constraint: Prefer Off (Sum vars == 0)
                    # We implement as Penalty for Working
                    if vars_s:
                        ultra_late_next_day_penalties.append(sum(vars_s) * 500) # High penalty to prefer Off
                        
                        # Implementation of Restriction if working
                        # 超遅の翌日は「ク遅」「入」「休」のいずれか
                        allowed_next = ['ク遅', '入', '休']
                        
                        # Constraint: If sum(vars_s) == 1, then one of allowed must be 1.
                        # Meaning others must be 0.
                        for l in target_locations:
                            if l.code not in allowed_next and (s.id, l.code) in x:
                                 model.Add(x[s.id, l.code] == 0)

        # DH-03: Required Headcount
        for loc in target_locations:
            req = location_needs[loc.code]
            vars_l = [x[s.id, loc.code] for s in available_staff if (s.id, loc.code) in x]
            model.Add(sum(vars_l) <= req) # Req 2: Allow understaffing if impossible
            
        # 5. Power Balance (PB-xx)
        self._add_power_balance_constraints(model, x, target_locations, location_needs, available_staff, current_date, weekday, female_gyohai_wed, gyohai_has_veteran)

        # 5.5 クMR Special Rule (SR-クMR)
        l_code = 'クMR'
        if l_code in [loc.code for loc in target_locations]:
            v_s = [(s, x[s.id, l_code]) for s in available_staff if (s.id, l_code) in x]
            if v_s:
                a_vars = [v for s, v in v_s if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) >= SkillRank.A]
                ab_vars = [v for s, v in v_s if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) >= SkillRank.B]
                d_vars = [v for s, v in v_s if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) == SkillRank.D]
                
                if weekday == 2:  # 水曜
                    if a_vars: model.Add(sum(a_vars) >= 3)
                    if ab_vars: model.Add(sum(ab_vars) >= 4) # A3, B1
                    if d_vars: model.Add(sum(d_vars) == 0) # D禁止
                elif weekday == 4:  # 金曜
                    if a_vars: model.Add(sum(a_vars) >= 2)
                    if ab_vars: model.Add(sum(ab_vars) >= 4) # A2, B2
                    if d_vars: model.Add(sum(d_vars) <= 1)
                else:  # 月火木土
                    if a_vars: model.Add(sum(a_vars) >= 2)
                    if ab_vars: model.Add(sum(ab_vars) >= 3) # A2, B1
                    if d_vars: model.Add(sum(d_vars) <= 1)
                
                # Soft Constraint for D
                if weekday != 2 and d_vars:
                    d_count = sum(d_vars)
                    d_assigned = model.NewBoolVar(f'd_assigned_in_clinic_mr_{current_date.day}')
                    model.Add(d_count == 1).OnlyEnforceIf(d_assigned)
                    model.Add(d_count != 1).OnlyEnforceIf(d_assigned.Not())
                    maximization_objective.append(d_assigned * 500) # Give bonus to assign exactly 1 D


        # 6. Special Rules (SR-xx)
        # Helper for week number (Nth occurrence of weekday in month)
        # current_date.day: 1..31
        # week_num = (day - 1) // 7 + 1
        current_week_num = (current_date.day - 1) // 7 + 1
        
        self._add_special_rules(model, x, current_date, self.rules, location_needs)

        # 7. Soft Constraints: Minimize Consecutive Same Assignments
        consecutive_penalties = []
        WEIGHT_CONSECUTIVE = 100
        
        for s in available_staff:
             if s.id in prev_assignments:
                 prev_loc = prev_assignments[s.id]
                 if (s.id, prev_loc) in x:
                     consecutive_penalties.append(x[s.id, prev_loc] * WEIGHT_CONSECUTIVE)
        
        # Aggregate Penalties
        # Fairness + Consecutive + UltraLateOff Preference
        # Note: UltraLateOff Minimize call was done per staff above. CP-SAT allows multiple Minimize calls? 
        # No! "Minimize(obj)". Calling it overrides previous.
        # I must collect all terms into one expression.
        
        total_penalties = []
        total_penalties.extend(fairness_penalties)
        total_penalties.extend(consecutive_penalties)
        total_penalties.extend(ultra_late_next_day_penalties)
        
        # Req 2: Maximize Assignments - Penalties
        model.Maximize(sum(maximization_objective) - sum(total_penalties))

        # Solve
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            result = self._extract_day_solution(solver, x, current_date, self.skills)
            return result + forced_holidays # Merged result
        else:
            print(f"FAILED to schedule day: {current_date}")
            # Debug: Print active constraints or resource shortage
            print(f"  Weekday: {weekday}")
            print(f"  Active Locations: {[l.code for l in target_locations]}")
            print(f"  Available Staff Count: {len(available_staff)}")
            return forced_holidays # Return at least forced ones

    def _extract_day_solution(self, solver, x, date, skills) -> List[DayAssignment]:
        res = []
        for (sid, lcode), var in x.items():
            if solver.Value(var) == 1:
                rank = skills.get(sid, {}).get(lcode, SkillRank.NONE)
                res.append(DayAssignment(date=date, staff_id=sid, location_code=lcode, rank=rank))
        return res

    def _add_power_balance_constraints(self, model, x, target_locations, location_needs, available_staff, current_date, day_of_week, female_gyohai_wed, gyohai_has_veteran):
        """Phase 4: Power Balance Constraints"""
        
        # Helper map
        pb_map = {}
        for r in self.pb_rules:
            pb_map.setdefault(r.location_code, []).append(r)
        
        for loc in target_locations:
            l_code = loc.code
            
            # Identify staff variables for this location
            vars_s_loc = [] # (staff, var)
            vars_loc_only = [] # var
            for s in available_staff:
                if (s.id, l_code) in x:
                    v = x[s.id, l_code]
                    vars_s_loc.append((s, v))
                    vars_loc_only.append(v)
            
            if not vars_loc_only: continue

            # --- Generic Rules (PB-01, PB-02, PB-03) ---
            if l_code in pb_map and l_code != 'クMR':
                for pb in pb_map[l_code]:
                    # PB-01: Min Rank
                    if pb.min_rank and pb.min_count:
                        # User Request Override: Seimitsu (精) on Mon/Tue/Thu/Sat allows Rank D (ignore Min B).
                        skip_min_rank = False
                        if l_code == '精':
                             weekday = current_date.weekday()
                             if weekday in [0, 1, 3, 5]: # Mon, Tue, Thu, Sat
                                 skip_min_rank = True
                        
                        if not skip_min_rank:
                            qualified = [v for s, v in vars_s_loc 
                                         if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) >= pb.min_rank]
                            if qualified:
                                actual_req = location_needs.get(l_code, 0)
                                adjusted_min_count = min(pb.min_count, actual_req)
                                model.Add(sum(qualified) >= adjusted_min_count)
                            
                    # PB-02: CD Cap
                    if pb.cd_cap is not None:
                        cd_vars = [v for s, v in vars_s_loc 
                                   if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) in [SkillRank.C, SkillRank.D]]
                        if cd_vars:
                             model.Add(sum(cd_vars) <= pb.cd_cap)
                             
                    # PB-03: D Solo Ban
                    if pb.d_solo_ban:
                        req_num = location_needs.get(l_code, 0)
                        if req_num >= 2:
                            non_d_vars = [v for s, v in vars_s_loc 
                                          if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) > SkillRank.D]
                            if non_d_vars:
                                model.Add(sum(non_d_vars) >= 1)

            # --- Specific Rules (PB-04, PB-05) ---
            
            # PB-04: Portable (ポ) D Pair Ban
            # If location is 'ポ' and required >= 2, D count <= 1
            if l_code == 'ポ':
                req_num = location_needs.get(l_code, 0)
                if req_num >= 2:
                    d_vars = [v for s, v in vars_s_loc 
                              if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) == SkillRank.D]
                    if len(d_vars) >= 2:
                        model.Add(sum(d_vars) <= 1)
                        
            # PB-05: CT (CT) CD Pair Ban -> effectively "At least 1 A or B" (Rank > C? No, > C is A/B)
            # Or "CD Count < Required"? The snippet says "sum(cd) < required".
            # Which implies "At least one person is NOT CD".
            if l_code == 'CT':
                req_num = location_needs.get(l_code, 0)
                if req_num >= 2:
                    cd_vars = [v for s, v in vars_s_loc 
                               if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) in [SkillRank.C, SkillRank.D]]
                    if cd_vars:
                         model.Add(sum(cd_vars) < req_num)

            # PB-05 end

            # PB-07: クリニック（ク）の経験年数制約（若い人ばかりにならない）
            if l_code == 'ク':
                # The ORIGINAL req_num before deducting gyohai was location_needs['ク'] + female_gyohai_wed
                original_req_num = location_needs.get(l_code, 0) + (female_gyohai_wed if day_of_week == 2 else 0)
                
                if original_req_num >= 2:
                    # If Gyohai already supplied a veteran, we are good.
                    if day_of_week == 2 and gyohai_has_veteran:
                        pass # Requirement already met by fixed assignment
                    else:
                        # 経験年数6年以上のベテランが最低1人は入るようにする
                        experienced_vars = [v for s, v in vars_s_loc 
                                            if int(s.experience_years) >= 6]
                        if experienced_vars:
                            model.Add(sum(experienced_vars) >= 1)
                        else:
                            print(f"DEBUG: No veterans available for 'ク' on {current_date}")

        # PB-06: クリニック系（ク + ク遅 + MG）の女性配置
        # 常時: 女性3人以上、金曜日: 女性4人以上
        clinic_female_codes = ['ク', 'ク遅', 'MG']
            
        female_clinic_vars = []
        for s in available_staff:
            if s.gender.value == '女':
                for lc in clinic_female_codes:
                    if (s.id, lc) in x:
                        female_clinic_vars.append(x[s.id, lc])
        
        if female_clinic_vars:
            weekday = current_date.weekday()
            min_female = 4 if weekday == 4 else 3  # 金曜4人、その他3人
            if day_of_week == 2:
                # Deduct women already stationed via Gyohai
                min_female = max(0, min_female - female_gyohai_wed)
            model.Add(sum(female_clinic_vars) >= min_female)

    def _extract_day_solution(self, solver, x, date, skills) -> List[DayAssignment]:
        res = []
        for (sid, lcode), var in x.items():
            if solver.Value(var) == 1:
                rank = skills.get(sid, {}).get(lcode, SkillRank.NONE)
                res.append(DayAssignment(date=date, staff_id=sid, location_code=lcode, rank=rank))
        return res

    def _add_special_rules(self, model, x, current_date, special_rules, location_needs):
        """Phase 5: Special Placement Rules"""
        weekday = current_date.weekday()
        week_num = self._get_week_number(current_date.day)
        weekday_names = ['月', '火', '水', '木', '金', '土', '日']
        weekday_name = weekday_names[weekday]
        
        for rule in special_rules:
            # Check applicability
            if not self._rule_applies(rule, weekday_name, week_num):
                continue
            
            loc_code = rule.location_code
            
            # Identify staff variables for this location
            # Need to find keys in x that match this location
            # x is {(sid, lcode): var}
            vars_s_loc = [] # (sid, var)
            vars_loc_only = []
            
            for (sid, l), var in x.items():
                if l == loc_code:
                    vars_s_loc.append((sid, var))
                    vars_loc_only.append(var)
            
            if not vars_loc_only: continue

            # Get the actual required count for today from our pre-processed location_needs
            actual_req = location_needs.get(loc_code, 0)
            if actual_req == 0:
                continue # Skip applying rule if location is closed today

            # Rank Condition (e.g. "A Rank >= 2" or "D Ban")
            if rule.rank_condition:
                if isinstance(rule.rank_condition, SkillRank): # Standard Rank (A/B/C)
                    # Count staff >= Rank
                    qualified = []
                    for sid, var in vars_s_loc:
                        val = self.skills.get(sid, {}).get(loc_code, SkillRank.NONE)
                        if val >= rule.rank_condition:
                            qualified.append(var)
                    
                    if rule.rank_count > 0:
                        # Scale down the constraint if the actual daily requirement is lower than the rule's assumption.
                        # For example, if rule says 6 total and 2 A-ranks, but today is Saturday with only 3 total.
                        # Target rank count should be min(rule.rank_count, actual_req)
                        # More specifically for SR-08/08b (2xA, 1xB total 6), 
                        # We just apply min(rule.rank_count, max(1, actual_req // 2)) depending on ratio, but for safety:
                        target_rank_count = min(rule.rank_count, actual_req)
                        # We also shouldn't enforce the full rank distribution strictly if it exceeds actual_req.
                        # But for CT/病CT (Saturday = 3), A:2 and B:1 is exactly 3 which is tight but possible.
                        model.Add(sum(qualified) >= target_rank_count)
                        
                elif rule.rank_condition == 'D同士禁止': # String condition?
                    pass

            # If rule has required_count, ensure we sum to the actual needed count for today,
            # NOT necessarily the one in the rule if it was overridden (e.g., Saturday CT).
            if rule.required_count > 0:
                model.Add(sum(vars_loc_only) == actual_req)

            # Source Logic (OP from HB A)
            if rule.source_location and rule.source_rank:
                # "At least 1 person from Source Rank"
                eligible_vars = []
                for sid, var in vars_s_loc:
                     src_val = self.skills.get(sid, {}).get(rule.source_location, SkillRank.NONE)
                     if src_val >= rule.source_rank:
                         eligible_vars.append(var)
                
                if eligible_vars:
                    model.Add(sum(eligible_vars) >= 1)

    def _rule_applies(self, rule, weekday_name, week_num) -> bool:
        # Weekday Check
        w_map = {'月':0, '火':1, '水':2, '木':3, '金':4, '土':5, '日':6}
        current_w_int = w_map.get(weekday_name)
        
        if rule.target_weekday is not None:
             # If target_weekday covers multiple (e.g. via separate rows), this logic holds.
             # If the rule object has int weekday:
            if rule.target_weekday != current_w_int:
                return False
                
        # Week Num
        if rule.target_week is not None and rule.target_week > 0:
            if rule.target_week != week_num:
                return False
                
        return True

    def _get_week_number(self, day: int) -> int:
        return (day - 1) // 7 + 1

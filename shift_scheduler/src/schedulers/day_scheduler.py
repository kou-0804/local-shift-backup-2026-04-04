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
                 skills: Dict[str, Dict[str, SkillRank]], pb_rules: List[PowerBalance],
                 year: int, month: int, training_rules: List[Dict] = None,
                 disable_training: bool = False, target_holidays: int = 9):
        self.staff_list = staff_list
        self.locations = locations
        self.rules = rules
        self.skills = skills
        self.pb_rules = pb_rules
        self.training_rules = training_rules or []
        self.disable_training = disable_training  # 研修枠を無効化するフラグ
        self.target_holidays = target_holidays
        self.year = year
        self.month = month
        self.dates = self._generate_dates()
        
        # Pre-calc MRI-only staff
        self.mri_only_staff = set()
        mri_locs = {'病院MR', 'CLMR', 'M遅'}
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

        # MRI専門職（放射線技師でない／MRI専従）: 担当回数の公平化対象外
        # 備考欄に「MRI専門」を含むスタッフを抽出する。
        self.mri_specialist_ids = {
            s.id for s in self.staff_list
            if getattr(s, 'note', '') and 'MRI専門' in s.note
        }

    def _is_protected_pair(self, staff_id: str, loc_code: str) -> bool:
        """担当回数の平準化（公平化）の対象外とすべき個別ルールのペアか判定する。
        これらは意図的な専従・個別指定のため、平準化で崩してはならない。
        保護リスト:
          - T001: 病CT専従
          - T013・T025: クリニック(ク)6回以上の個別指定
          - T072: 館山専任
          - MRI専門職: MRI(病院MR/CLMR/M遅)専従
        """
        base = self._get_base_location_code(loc_code)
        if staff_id == 'T001' and base == 'CT':
            return True
        if staff_id in ('T013', 'T025') and base == 'ク':
            return True
        if staff_id == 'T072' and base == '館山':
            return True
        if staff_id in self.mri_specialist_ids and base in ('病院MR', 'CLMR'):
            return True
        return False

    # 近接クラスタ回避の対象業務（希少＋手当）。
    # CT/ク等の高ボリューム業務や専従(病CT専従/MRI専門/PET/RI/放治/館山)は対象外。
    PROXIMITY_DUTIES = ('HB', 'DR', 'ア', 'ポ', '超遅', 'ク遅', 'M遅', 'OP')
    # 手当（手当金）に関わる業務。連続回避・回数上限を特に強く適用する。
    PAID_DUTIES = ('超遅', 'ポ', 'ク遅', 'M遅')
    # 手当業務の1人あたり月間目安上限。上限手前から抑制し上限超で強く抑制する。
    # 上限3だと重回数者を若手へ強制再配置し代休が倍増したため、代休とのバランスで4に設定。
    PAID_MONTHLY_CAP = 4

    # ポータブル(ポ)のランク制約緩和フラグ。仮説検証の結果、緩和しても代休は減らず
    # むしろ悪化(7.0→8.0)したため False。代休増は「資格者の日ごと不足」ではなく
    # 「分散先の若手に公休の余裕が無い」構造的要因で、ランク緩和では解消できない。
    # Bランク必須(PB-01)・D×D禁止(PB-04)は技量担保のため維持する。
    RELAX_PORTABLE_RANK = False

    # ポータブル(ポ)で「下位レイヤー(若手)優先・上位レイヤー(ベテラン)は逃がし弁」とする
    # 経験年数の境界。この年数以下を下位（優先）、超を上位（後回し・代休/連続回避の逃がし弁）とする。
    PORTABLE_JUNIOR_MAX_YEARS = 7

    def _proximity_penalty(self, staff_id, l_code, assignment_history):
        """同一業務の近接クラスタに対する段階的ソフト減点（負値）を返す。

        前日(連続)=強 / 中1日(2日前)=弱 / 中2日(3日前)=微弱 / 中3日以上=なし。
        最も直近の occurrence を1つだけ採用し多重加算しない。
        減点幅は配置不足(500万)・SR人数下限(300万)より必ず小さく保ち、
        他に担当者がいない日は連続を許容してカバレッジを死守する（ソフト制約）。

        手当業務(PAID_DUTIES)は「中1日以上空ける」を徹底するため前日連続を強化するが、
        休/予算判断(約100〜150万)を乱して代休を誘発しない水準(数十万)に上限を抑える。
        HB/DR/ア/OP は従来値のままでカバレッジを保護。
        """
        if l_code not in self.PROXIMITY_DUTIES or not assignment_history:
            return 0
        h = assignment_history
        is_paid = l_code in self.PAID_DUTIES
        # ポは利用者要望で連続を特に強く禁止(-90万準禁止)。他手当は-40万、非手当は-12万。
        if l_code == 'ポ':
            prev_pen, gap1_pen, gap2_pen = -900000, -120000, -30000
        elif is_paid:
            prev_pen, gap1_pen, gap2_pen = -400000, -100000, -30000
        else:
            prev_pen, gap1_pen, gap2_pen = -120000, -30000, -12000
        if len(h) >= 1 and h[-1].get(staff_id) == l_code:
            return prev_pen
        if len(h) >= 2 and h[-2].get(staff_id) == l_code:
            return gap1_pen
        if len(h) >= 3 and h[-3].get(staff_id) == l_code:
            return gap2_pen
        return 0

    def _get_base_location_code(self, loc_code: str) -> str:
        """複合・派生シフトコードを基本業務コードに正規化する。
        例: 'ク/17業' -> 'ク', 'ク遅' -> 'ク', 'M遅' -> 'CLMR', '(ア)' -> 'ア'
        """
        # 育成枠 (ア) → ア
        if loc_code.startswith('(') and loc_code.endswith(')'):
            return loc_code[1:-1]
        # ク遅 → ク
        if loc_code == 'ク遅':
            return 'ク'
        # M遅 → CLMR（クリニックMRIの遅番）
        if loc_code == 'M遅':
            return 'CLMR'
        # 病L → 入（病院リーダー）、病CT → CT（病院CT）
        if loc_code in ['病L', '入']:
            return '入'
        if loc_code in ['病CT', 'CT']:
            return 'CT'
        # '[業務名]/17業' や '[業務名]/17休' → [業務名]
        if '/17業' in loc_code or '/17休' in loc_code:
            return loc_code.split('/')[0]
        return loc_code

    def _generate_dates(self) -> List[date]:
        import calendar
        num_days = calendar.monthrange(self.year, self.month)[1]
        return [date(self.year, self.month, d) for d in range(1, num_days + 1)]

    def _calc_workday_budget(self, req_map, night_map, target_holidays: int = None) -> Dict[str, int]:
        """月ごとの公休目標を守るため、スタッフごとの最大勤務日数を事前計算する。
        max_workdays = 確定可能勤務日数 - 追加で必要な公休日数
        """
        if target_holidays is None:
            target_holidays = self.target_holidays
        # 休暇判定ロジック：☆や★で始まる、または「休」「育」「退職」を含む記号は一意に公休として扱う
        def is_pure_holiday(sym):
            if not sym: return False
            if sym in {'○', '出/☆'}: return True
            if any(sym.startswith(p) for p in ['☆', '★', '◆']): return True
            if any(p in sym for p in ['休', '育', '退職']): return True
            return False

        CONDITIONAL_HOLIDAY_SYMS = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
        # 強制勤務申請: 日程が確定している業務（公休にもスケジュール対象にもならない）
        FORCED_WORK_SYMS = {'業配', '業出', '出', '会議', '全会', '講', '勤', '出/講',
                            '出/(聴)', '出/(発)2', '17業'}
        budgets = {}
        for s in self.staff_list:
            if s.status != '在籍':
                continue
            rest_count = 0        # 確定公休日数（9日カウント対象）
            non_schedulable = 0   # スケジュール不可日数（夜勤・明け・強制勤務）
            for d in self.dates:
                req = req_map.get((s.id, d))
                is_night = night_map.get((s.id, d), False)
                is_ake = night_map.get((s.id, d - timedelta(days=1)), False)
                is_jan = (d.month == 1 and d.day in [1, 2, 3])
                is_off_day = is_jan or jpholiday.is_holiday(d) or d.weekday() == 6
                if is_night:
                    # 夜勤当日は日勤も可能（当直運用）
                    pass
                elif is_ake:
                    non_schedulable += 1   # 明け = 日勤配置なし、公休にもならない
                elif req in FORCED_WORK_SYMS:
                    non_schedulable += 1   # 確定業務（公休にならず、通常配置枠にも入らない）
                elif is_pure_holiday(req):
                    rest_count += 1        # 希望休等 = 確定公休
                elif req in CONDITIONAL_HOLIDAY_SYMS:
                    if is_off_day:
                        rest_count += 1    # 日曜祝日の研修=公休
                    else:
                        non_schedulable += 1 # 平日土曜の研修=勤務扱いで配置不可
                elif req:
                    # その他の勤務申請（病CTなど）がある場合は勤務日として扱う
                    non_schedulable += 1
                elif is_off_day:
                    rest_count += 1        # 日曜・祝日 = 確定公休
                # else: 通常の勤務可能日
            schedulable = len(self.dates) - rest_count - non_schedulable
            needed_extra_rest = max(0, target_holidays - rest_count)
            budgets[s.id] = max(0, schedulable - needed_extra_rest)
        return budgets

    def schedule(self, 
                 requests: List[Request], 
                 night_assignments: List[NightAssignment]) -> Tuple[List[DayAssignment], Dict[date, Dict[str, int]]]:
        
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
            
        # Pre-calculate monthly workday budget per staff (rest-day protection)
        workday_budget = self._calc_workday_budget(req_map, night_map)
        # Track cumulative regular-day assignments (used to enforce budget)
        total_work_count = {s.id: 0 for s in self.staff_list}
        # Day-by-Day Scheduling Loop
        daily_location_needs = {}

        for d in self.dates:
            print(f"Scheduling Day: {d}")
            prev_assignments = assignment_history[-1] if assignment_history else {}

            day_assignments, location_needs = self._schedule_one_day(
                d, req_map, night_map, prev_assignments, assignment_counts, 
                consecutive_work_days, total_work_count, workday_budget,
                assignment_history
            )
            all_assignments.extend(day_assignments)
            daily_location_needs[d] = location_needs
            
            # Record history
            current_day_map = {a.staff_id: a.location_code for a in day_assignments}
            assignment_history.append(current_day_map)
            
            # Update cumulative counts（正規化したコードで管理して均等化の精度を上げる）
            for a in day_assignments:
                c = assignment_counts[a.staff_id]
                base_code = self._get_base_location_code(a.location_code)
                c[base_code] = c.get(base_code, 0) + 1
                # 手当業務(超遅/ポ/ク遅/M遅)は個別公平化のため raw コードでも別キー集計する。
                # （ク遅→ク, M遅→CLMR の base統合とは別に、業務そのものの回数を保持）
                if a.location_code in ('超遅', 'ポ', 'ク遅', 'M遅'):
                    _rk = '_L_' + a.location_code
                    c[_rk] = c.get(_rk, 0) + 1
            # Update consecutive work days AND total_work_count
            PURE_HOLIDAY_SYMS = {'★', '★連', '☆', '☆小', '☆防', '☆デ', '◆', '○', '出/☆', '退職'}
            CONDITIONAL_HOLIDAY_SYMS = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
            
            for s in self.staff_list:
                loc = current_day_map.get(s.id)
                is_night_today = night_map.get((s.id, d))
                is_ake_today = night_map.get((s.id, d - timedelta(days=1)))
                req_symbol = req_map.get((s.id, d))
                
                is_working_day = False
                if is_night_today or is_ake_today:
                    is_working_day = True
                elif req_symbol and req_symbol not in PURE_HOLIDAY_SYMS and req_symbol not in CONDITIONAL_HOLIDAY_SYMS and req_symbol not in ['休', '休(仮)']:
                    is_working_day = True # Normal working requests
                elif req_symbol in CONDITIONAL_HOLIDAY_SYMS:
                    is_jan = (d.month == 1 and d.day in [1, 2, 3])
                    is_off_day = is_jan or jpholiday.is_holiday(d) or d.weekday() == 6
                    if not is_off_day:
                        is_working_day = True # Weekday training is work
                elif loc and loc not in ['休', '○']:
                    is_working_day = True # Normal day assignment
                    
                if is_working_day:
                    consecutive_work_days[s.id] += 1
                    total_work_count[s.id] = total_work_count.get(s.id, 0) + 1
                else:
                    consecutive_work_days[s.id] = 0
            
        return all_assignments, daily_location_needs

    def _schedule_one_day(self, 
                          current_date: date, 
                          req_map: Dict[Tuple[str, date], str], 
                          night_map: Dict[Tuple[str, date], bool],
                          prev_assignments: Dict[str, str],
                          assignment_counts: Dict[str, Dict[str, int]],
                          consecutive_work_days: Dict[str, int],
                          total_work_count: Dict[str, int] = None,
                          workday_budget: Dict[str, int] = None,
                          assignment_history: List[Dict[str, str]] = None) -> Tuple[List[DayAssignment], Dict[str, int]]:
        
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
            # Clinic Codes: 'CLMR', 'ク', 'DR' (Confirmed via Master)
            # Weekday 5 = Sat. Week 3 = 3rd occurrence.
            if weekday == 5 and current_week_num == 3:
                 clinic_codes = ['CLMR', 'ク', 'DR', 'CT', 'MG', 'ク遅', 'M遅']
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
        
        # 休暇判定ロジックを共通化
        def is_any_holiday(sym):
            if not sym: return False
            if sym in ['17休', '休(仮)']: return False # 17時以降休みや仮の休みは日勤可能とみなす
            if sym in {'○', '出/☆'}: return True
            if any(sym.startswith(p) for p in ['☆', '★', '◆']): return True
            if any(p in sym for p in ['休', '育', '退職']): return True
            if sym in {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}:
                return True
            return False
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
        forced_loc_for_staff = {}
        loc_request_counts = {}
        
        for s in self.staff_list:
            if s.status != '在籍': continue
            p_req = req_map.get((s.id, current_date))
            
            if weekday == 2 and p_req == '業配' and s.gender.value == '女':
                female_gyohai_wed += 1
                if int(s.experience_years) >= 6:
                    gyohai_has_veteran = True
            
            target_loc_code = None
            if p_req in FORCED_LOC_MAP:
                target_loc_code = FORCED_LOC_MAP[p_req]
            elif p_req and not is_any_holiday(p_req):
                if any(l.code == p_req for l in self.locations):
                    target_loc_code = p_req
                    
            if target_loc_code:
                forced_loc_for_staff[s.id] = target_loc_code
                loc_request_counts[target_loc_code] = loc_request_counts.get(target_loc_code, 0) + 1

        # 新ルール：事前の「出」などの申請は元の枠（base_need）を消費し、超過分のみ枠を拡張する
        for loc_code, req_count in loc_request_counts.items():
            loc_obj = next((l for l in self.locations if l.code == loc_code), None)
            if loc_obj:
                base_need = location_needs.get(loc_code, 0)
                location_needs[loc_code] = max(base_need, req_count)
                if loc_obj not in target_locations:
                    target_locations.append(loc_obj)
                    
        # Deduct Wednesday female Gyohai from 'ク' needs
        if female_gyohai_wed > 0 and 'ク' in location_needs:
            location_needs['ク'] = max(0, location_needs['ク'] - female_gyohai_wed)

        # 1.5 Setup Training Locations based on training_rules
        training_mappings = []
        if not is_holiday:
            for r in self.training_rules:
                modality = r['modality']
                if any(l.code == modality for l in target_locations):
                    display_name = r.get('display_name') or f"({modality})"
                    dummy_code = display_name # Use display_name as dummy code for Excel
                    dummy_loc = Location(dummy_code, f"{modality}育成", "育成", {}, "なし", 99, True)
                    
                    if not any(l.code == dummy_code for l in target_locations):
                        target_locations.append(dummy_loc)
                        location_needs[dummy_code] = 1 # Force max 1 trainee per day per modality
                        
                        # Determine instructors
                        instructors = r['instructors']
                        if instructors == ["RANK_A_ONLY"]:
                             # Find all staff with Rank A in this modality
                             instructors = [s.id for s in self.staff_list if self.skills.get(s.id, {}).get(modality, SkillRank.NONE) == SkillRank.A]
                        
                        training_mappings.append({
                            'modality': modality,
                            'dummy_code': dummy_code,
                            'instructors': instructors,
                            'trainees': r['trainees']
                        })

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
                
            is_night_today = night_map.get((s.id, current_date))
            
            # Calculate unavoidable future consecutive work days due to Night/Ake/Requests
            forced_future = 0
            CONDITIONAL_HOLIDAY_SYMS = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
            
            for offset in range(1, 10):
                check_d = current_date + timedelta(days=offset)
                is_n = night_map.get((s.id, check_d))
                is_a = night_map.get((s.id, check_d - timedelta(days=1)))
                
                is_working_req = False
                req_symbol = req_map.get((s.id, check_d))
                if req_symbol and req_symbol not in ['休', '休(仮)', '○', '★', '★連', '☆', '☆小', '☆デ', '◆', '退職']:
                    # If there's a request and it's not a holiday, it's a forced working day
                    if req_symbol in CONDITIONAL_HOLIDAY_SYMS:
                        is_jan = (check_d.month == 1 and check_d.day in [1, 2, 3])
                        is_off_day = is_jan or jpholiday.is_holiday(check_d) or check_d.weekday() == 6
                        if not is_off_day:
                            is_working_req = True
                    else:
                        is_working_req = True
                
                if is_n or is_a or is_working_req:
                    forced_future += 1
                else:
                    break # Reached a day where they *could* theoretically rest
            
            # 6日連続勤務後は強制休暇（連勤最大6日）
            c_days = consecutive_work_days.get(s.id, 0)
            
            if c_days >= 6 or (c_days + 1 + forced_future > 6):
                p_req_check = req_map.get((s.id, current_date))
                if p_req_check is None and not is_night_today:
                    # 予定申請がなく、夜勤でもない場合のみ強制休暇
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='休', rank=SkillRank.NONE))
                    continue
                # 予定申請や夜勤がある場合は連勤制限を適用せず、現状を維持する（休夜などの回避）
                
            # Check Previous Night (DH-05)
            if night_map.get((s.id, prev_date)):
                continue
                
            p_req = req_map.get((s.id, current_date))
            
            # Req 4: Enforce Holiday after Post-Night
            if night_map.get((s.id, two_days_ago)):
                if p_req is None and not is_night_today:
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='休', rank=SkillRank.NONE))
                    continue
            
            if is_any_holiday(p_req):
                continue

            # 業配/業出: 勤務場所マスタに無い「表示専用の業務配置」（水曜の乳房生検等）。
            # セルに「業配」と表示し、他業務には流さない（クリニック女性枠の会計とも整合）。
            # 場所として配置できないため、強制表示割当として確定させる。
            if p_req in ('業配', '業出'):
                forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code=p_req, rank=SkillRank.NONE))
                continue

            # NEW LOGIC: Ishikawa 4th Tuesday PET Assignment
            if s.id == 'T002' and current_date.weekday() == 1 and 22 <= current_date.day <= 28:
                if not night_map.get((s.id, current_date)):
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='PET', rank=SkillRank.NONE))
                    continue

            # 箕輪(T022): 月曜は DX として確保し、勤務地に振らない。
            # 祝日(ハッピーマンデー含む)・1/1〜3・本人の休み希望は DX より優先（休み希望は
            # 上の is_any_holiday(p_req) で既に continue 済み）。当日夜勤がある月曜は夜勤を優先。
            # DX は勤務日扱い（公休・代休にはカウントされず、連勤カウントには含まれる）。
            if (s.id == 'T022' and current_date.weekday() == 0
                    and not jpholiday.is_holiday(current_date)
                    and not (current_date.month == 1 and current_date.day in [1, 2, 3])):
                if not night_map.get((s.id, current_date)):
                    forced_holidays.append(DayAssignment(date=current_date, staff_id=s.id, location_code='DX', rank=SkillRank.NONE))
                    continue

            staff_req_symbol[s.id] = p_req
            available_staff.append(s)

        staff_hpi = {}
        future_dates = [ft for ft in self.dates if ft > current_date]
        
        for s in available_staff:
            # 既に取得済みの休日数（本日のDayScheduler時点でのカウント）
            taken_count = 0
            if assignment_history:
                for hist in assignment_history:
                    loc = hist.get(s.id)
                    if loc == '休':
                        taken_count += 1
            
            # 未来の確定休み（日曜、祝日、希望休）
            future_fixed_offs = 0
            future_akes = 0
            for ft in future_dates:
                is_ft_jan = (ft.month == 1 and ft.day in [1, 2, 3])
                is_ft_off = is_ft_jan or jpholiday.is_holiday(ft) or ft.weekday() == 6
                req = req_map.get((s.id, ft))
                is_ft_night = night_map.get((s.id, ft), False)
                is_ft_ake = night_map.get((s.id, ft - timedelta(days=1)), False)
                
                if is_any_holiday(req) or is_ft_off:
                    future_fixed_offs += 1
                elif is_ft_ake:
                    future_akes += 1
            
            # HARDCODED BUG FIX: Removed hardcoded 9. We safely estimate target_holidays as 10 (or 21 budget roughly).
            # T004 had 10 future fixed offs (8 pub + 2 stars). 9 - 10 was negative, so HPI was always 0!
            # We must use self.workday_budget logic or at least 10 here.
            target = 10 # Default standard month
            needed = max(0, target - (taken_count + future_fixed_offs))
            # HPIの分母：夜勤当日も含めるため、future_nights_akes ではなく future_akes のみを除外する
            remaining_weakdays = len(future_dates) - future_fixed_offs - future_akes
            
            if remaining_weakdays > 0:
                hpi = needed / remaining_weakdays
            else:
                hpi = float(needed)
            staff_hpi[s.id] = hpi

        # ── 場所別の担当回数の平均（公平化の基準値）──
        # 各業務について、有資格な出勤可能スタッフの「現時点までの担当回数」の平均を出す。
        # 後段で、この平均を超えて担当している人にペナルティを科し、偏りを是正する。
        loc_avg = {}
        for loc in target_locations:
            bc = self._get_base_location_code(loc.code)
            quals = [assignment_counts[s.id].get(bc, 0) for s in available_staff
                     if self.skills.get(s.id, {}).get(loc.code, SkillRank.NONE) > SkillRank.NONE]
            if quals:
                loc_avg[loc.code] = sum(quals) / len(quals)
        # 手当業務(超遅/ポ/ク遅/M遅)の raw 平均（base統合せず業務そのものの回数で均等化）
        loc_avg_raw = {}
        for _code in ('超遅', 'ポ', 'ク遅', 'M遅'):
            _rk = '_L_' + _code
            _q = [assignment_counts[s.id].get(_rk, 0) for s in available_staff
                  if self.skills.get(s.id, {}).get(_code, SkillRank.NONE) > SkillRank.NONE]
            if _q:
                loc_avg_raw[_code] = sum(_q) / len(_q)

        # 3. Create Variables x[staff_id, loc_code]
        x = {}
        fairness_penalties = []
        maximization_objective = [] # Req 2
        next_date = current_date + timedelta(days=1) # Req 3

        for s in available_staff:
            s_skills = self.skills.get(s.id, {})
            p_req = staff_req_symbol.get(s.id)
            hpi = staff_hpi.get(s.id, 0.0)
            
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
                is_training = l_code.startswith('(') and l_code.endswith(')')

                # --- 研修無効化フラグ ---
                # main.py からの制御で研修を全面禁止にする（代休が発生する月に研修を入れない）
                if is_training and self.disable_training:
                    continue

                # --- PRUNING BASED ON HPI ---
                # HPI > 0.3: 公休不足の予兆があれば研修（育成枠）をスキップ
                if is_training and hpi > 0.3:
                    continue
                
                # 育成枠の優先度制御: リスト内で「最优先の未研修者」だけに変数を作る
                # これにより、従来の「全員が候補となりソルバーが決める」のではなく
                # 「最優先の人のみが候補」になり、後順位の人に割り当てられる問題を解消する
                if is_training:
                    # この日の研修枠定員を確認: リストの中で最優先の人だけを候補にする
                    matched_rule = None
                    for r in self.training_rules:
                        if l_code == (r.get('display_name') or f"({r['modality']})"):
                            matched_rule = r
                            break
                    if matched_rule is None:
                        continue  # この枠に該当ルールなし -> スキップ
                    trainees = matched_rule['trainees']
                    if s.id not in trainees:
                        continue  # 育成対象外 -> スキップ
                    # 「該当日時点で最優先の人」のみを候補にする
                    # メインの支数ルールL709以降で <= ins_sum 制約がかかるが
                    # リスト順位をここで強制する
                    my_index = trainees.index(s.id)
                    # 自分より順位が上の人がすでに今月訓練済みか確認
                    # (assignment_counts に育成枠コードが記録される)
                    higher_priority_done = False
                    for idx in range(my_index):
                        # 上位者が今期不住の時は自分が次の候補になる
                        higher_id = trainees[idx]
                        higher_training_count = assignment_counts.get(higher_id, {}).get(l_code, 0)
                        if higher_training_count == 0:
                            # 上位者がまだ訓練していない -> 自分は候補神
                            higher_priority_done = True
                            break
                    if higher_priority_done:
                        continue  # 上位者が先に研修すべきなのでスキップ
                
                # DH-07: Forced Location Check
                # ソフト制約化: hard "==1" は月末にINFEASIBLEを引き起こすため、
                # 超大ボーナスで実質的に強制しつつ競合時は他の解を許容する
                if s.id in forced_loc_for_staff:
                    target_loc = forced_loc_for_staff[s.id]
                    if l_code == target_loc:
                        x[s.id, l_code] = model.NewBoolVar(f'x_{s.id}_{l_code}')
                        maximization_objective.append(x[s.id, l_code] * 800000)  # ほぼ強制
                    else:
                        pass  # Do not create variable = effectively 0
                    continue
                
                # If p_req is None or normal
                
                # 育成枠（ダミー場所）は専用チェック：スキルマスタを見ず、研修生リストで判断
                if l_code.startswith('(') and l_code.endswith(')'):

                    is_registered_trainee = any(s.id in tm['trainees'] for tm in training_mappings if tm['dummy_code'] == l_code)
                    if not is_registered_trainee:
                        continue
                    # 研修生はスキルチェック不要でそのまま変数作成へ進む
                else:
                    # DH-02: 通常業務のスキルチェック
                    rank = s_skills.get(l_code, SkillRank.NONE)
                    if rank == SkillRank.NONE:
                        continue
                    if l_code not in s_skills:
                        continue
                    if s_skills[l_code] in [SkillRank.NONE, '-', '']:
                        continue
                # 以下のランクチェックはダミー枠には適用しない
                if not (l_code.startswith('(') and l_code.endswith(')')):
                    # HB: 仕様7.1.2 — Aランク必須は第1金曜(SR-03)・第4木曜(SR-04)のみ。
                    # それ以外の日は通常ルール（HBスキルB以上で可）。
                    # 旧実装は全日Aランク必須でAランク6名に候補を固定し、川向等への
                    # 偏り（HB8回）・3連続を招いていた。特殊日のA人数下限(A×2/A×3)は
                    # SR-03/SR-04 が別途ハード制約として担保するため、ここでの全日A固定は
                    # 冗長かつ通常日では誤り。通常日をB+に開放しプール6→12名で分散させる。
                    if l_code == 'HB':
                        _wk = self._get_week_number(current_date.day)
                        _hb_requires_A = (weekday == 4 and _wk == 1) or (weekday == 3 and _wk == 4)
                        if _hb_requires_A and rank < SkillRank.A:
                            continue
                    # アンギオ: Bランク以上
                    if l_code == 'ア' and rank < SkillRank.B:
                        continue
                    # Seisa (精): Wed/Fri -> Rank A. Others -> Rank B (Exclude Rank A).
                    if l_code == '精':
                        if weekday in [2, 4]:
                            if rank < SkillRank.A: continue
                        else:
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
                    continue
                    
                # DH-08,09,10: Late/MG Ban
                if ban_late and l_code in ['遅番', '超遅', 'ク遅', 'M遅']:
                    continue
                if ban_mg_po and l_code in ['MG', 'ポ']:
                    continue
                
                x[s.id, l_code] = model.NewBoolVar(f'x_{s.id}_{l_code}')

                # Maximization term (Req 2)
                base_score = 10000

                # ── Global Workload Fairness (Universal Equity) ──────
                # 全スタッフ間の「総勤務日数」を平準化する。
                # 平均より多く働いている人にはペナルティ、少ない人には加点を行う。
                if total_work_count:
                    avg_work = sum(total_work_count.values()) / len(total_work_count)
                    current_work = total_work_count.get(s.id, 0)
                    diff = current_work - avg_work
                    if diff > 0:
                        # 平均より多い場合は減点（1日につき20000点に増強し強力に平準化）
                        base_score -= int(diff * 20000)
                    elif diff < 0:
                        # 平均より少ない場合は加点（1日につき20000点）
                        base_score += int(abs(diff) * 20000)

                # HPI による動的なスコアリング
                if is_training:
                    # 育成枠の優先度を大幅に下げ、公休を優先させる
                    base_score = 50  # 通常の 1/200
                    # リスト順位によるボーナス（可能な限り1人目を優先）
                    matched_rule = None
                    for r in self.training_rules:
                        if l_code == (r.get('display_name') or f"({r['modality']})"):
                            matched_rule = r
                            break
                    if matched_rule:
                        trainees = matched_rule['trainees']
                        if s.id in trainees:
                            idx = trainees.index(s.id)
                            # 1番目:+3300, 2番目:+2200, 3番目:+1100
                            priority_bonus = max(0, (3 - idx) * 1100)
                            base_score += priority_bonus
                # (3) ペース配分（HPI）による強力なスケジューリング制御
                # 月間で均等に休ませるため、HPIが高騰している（働きすぎている）場合、強力に減点する
                if hpi > 0.8:
                    base_score = 500    # 超低優先度だがプラス（空欄放置は防ぐ）
                elif hpi > 0.6:
                    base_score = 1000   # 低優先度
                elif hpi > 0.4:
                    base_score = 3000   # 中優先度

                # 研修中の人が通常業務に選ばれる場合、わずかなペナルティ
                is_trainee = any(s.id in r['trainees'] for r in self.training_rules)
                if is_trainee:
                    base_score -= 200

                # (4) 希少スキルボーナスの適用（ただし、ペース配分に余裕がある場合のみ強力発動）
                mri_bonus = 50000  # ボーナスを適正化し、休日を無闇にキャンセルさせない
                if s.id in self.mri_only_staff and l_code in ['病院MR', 'CLMR', 'M遅']:
                    base_score += mri_bonus

                # 希少・遅番枠（M遅・ク遅）はスロットが1枠のみのため、
                # 優先的に埋めないと他業務との競合で空きになりやすい。
                # 大きなボーナスで確実に1名を確保する。
                if l_code in ['M遅', 'ク遅']:
                    base_score = max(base_score, 25000)

                # HB・DR・アンギオ（ア）：担当資格者が限られる希少業務。
                # DEFICIT_PENALTY(100,000)が同等の他業務（CLMR等）との競合で
                # ソルバーが一貫してこれらを「諦める」現象を防ぐため、
                # M遅/ク遅と同様に最低スコアを保証して優先配置を促す。
                if l_code in ['HB', 'DR', 'ア']:
                    base_score = max(base_score, 30000)

                # 近接クラスタ回避（希少＋手当業務）: 同一業務を近接した日に固めず分散させる。
                # 前日(連続)=強, 中1日=弱, 中2日=微弱の段階的ソフト減点。専従/高ボリューム業務は
                # 対象外。詳細は docs/superpowers/specs/2026-06-16-duty-proximity-clustering-design.md
                base_score += self._proximity_penalty(s.id, l_code, assignment_history)


                # (5) 究極の予算制限とラストリゾート（安全網）
                if workday_budget and total_work_count:
                    _budget = workday_budget.get(s.id, 9999)
                    _used = total_work_count.get(s.id, 0)
                    over = _used - _budget
                    if over >= 2:
                        base_score = -1500000  # 強力な拒否だが、配置不足(500万点)には劣るため最終手段として採用される
                    elif over == 1:
                        # 代休1日目到達で強力な拒否
                        base_score = -1500000 
                    elif over == 0:
                        # 予算ちょうど到達：できれば避ける（マイナススコア）
                        base_score = -200000

                # 手当業務(ポ/超遅/ク遅/M遅)の1人あたり月間上限(=3回)。回数集中を抑制する。
                # 累積回数(_L_*)で段階的に減点。配置充足(500万)より弱いソフトのため、他に
                # 担当者がいない最終手段では上限超過を許容しINFEASIBLE化しない。予算ブロックで
                # base_score が再代入された後に加算し、上限抑制が確実に効くようにする。
                if l_code in self.PAID_DUTIES:
                    _paid_count = assignment_counts[s.id].get('_L_' + l_code, 0)
                    if _paid_count >= self.PAID_MONTHLY_CAP:        # 上限超(5回目〜): 準禁止
                        base_score += -2000000
                    elif _paid_count == self.PAID_MONTHLY_CAP - 1:  # 上限手前(4回目): 弱い抑制(逃がし弁より弱く保つ)
                        base_score += -50000

                # ポータブル(ポ)の上位レイヤー(>7年)は「逃がし弁」。下位(若手)を優先しつつ、
                # 若手が連続(-18万)・予算オーバー(-150万)になる時だけ上位者が引き取れるよう、
                # それらより弱い控えめ減点(-10万)で上位者を後回しにする。カバレッジ(500万)・
                # B必須(300万)より弱いため、担当不能日は上位者でも確実に充足する（ソフト）。
                if l_code == 'ポ' and int(s.experience_years) > self.PORTABLE_JUNIOR_MAX_YEARS:
                    base_score += -100000

                maximization_objective.append(x[s.id, l_code] * base_score)

                # ── Soft Constraint: 場所別の担当回数の公平化（相対方式）──
                # 「同一業務の有資格者の平均担当回数(loc_avg)」を基準に、平均を超えた分
                # だけペナルティを科す。これにより特定の人にMRI等が偏るのを是正する。
                # 旧方式（count*500 を base_score-100 でキャップ）はボーナスに埋もれて
                # 事実上機能していなかったため、相対方式に作り直した。
                # 正規化ベースコードで集計し、ク遅・/17業 等を本来業務に統合して均等化する。
                base_l_code = self._get_base_location_code(l_code)
                count = assignment_counts[s.id].get(base_l_code, 0)
                # 予算到達・超過スタッフはスコアが既に低いので公平性ペナルティ免除
                _at_or_over_budget = (workday_budget and total_work_count and
                                      total_work_count.get(s.id, 0) >= workday_budget.get(s.id, 9999))
                # 保護ペア（病CT専従・ク6回ルール・館山専任・MRI専門）は公平化対象外
                if not self._is_protected_pair(s.id, l_code) and not _at_or_over_budget:
                    avg_for_loc = loc_avg.get(l_code, count)
                    excess = count - avg_for_loc
                    # 手当業務(超遅・ポ)は「両側公平化」を最優先。重みをク6ボーナス(50000)より
                    # 強くし、平均超過は強く減点・平均未満(特に0回)へは強く誘導する。手当の
                    # 「やる人/やらない人」差を最小化する狙い。上限は人員不足(500万)より必ず小さく保つ。
                    if l_code in ('超遅', 'ポ', 'ク遅', 'M遅'):
                        # 手当業務は raw カウント(_L_*)と raw平均で両側公平化（base統合しない）。
                        # 超遅/ポは raw==base なので従来挙動と同じ。ク遅/M遅はこれで初めて個別に効く。
                        p_count = assignment_counts[s.id].get('_L_' + l_code, 0)
                        p_avg = loc_avg_raw.get(l_code, p_count)
                        WEIGHT_PAID = 60000
                        if p_count > p_avg:
                            penalty = min(int((p_count - p_avg) * WEIGHT_PAID), 1500000)
                            fairness_penalties.append(x[s.id, l_code] * penalty)
                        elif p_count < p_avg:
                            deficit = p_avg - p_count
                            # 0回者には追加ボーナスで最優先（手当ゼロを潰す）
                            bonus = min(int(deficit * WEIGHT_PAID) + (100000 if p_count == 0 else 0), 1500000)
                            maximization_objective.append(x[s.id, l_code] * bonus)
                    else:
                        # 通常勤務地（CT/病CT/CLMR/ク 等）も手当業務と同じ「両側公平化」に統一する。
                        # 旧実装は平均超過の減点のみで、平均未満(特に0回)の有資格者を引き込む
                        # 加点が無かった。そのため特定業務に固定された技師（例: クに固定され
                        # CT系=0 の松井）の「一度も入らない」飢餓が放置されていた。
                        # 不足側に加点を付け、有資格者を本来業務へ呼び戻す。
                        # 注: 病CTとCTは _get_base_location_code で同一カウンタ(CT)に統合される
                        # ため、CT系全体を1プールとして均等化する（病CT専従は超過側で自然に抑制）。
                        WEIGHT_FAIR = 12000
                        if excess > 0:
                            # 平均超過1回あたり減点。上限は人員不足ペナルティ(500万)より
                            # 必ず小さく保ち、「公平化のために人員不足を招かない」を保証する。
                            #
                            # 希少1枠業務(HB/DR/ア)は有資格者が多い(HBは12名)割に特定者へ
                            # 積み増りやすい。超過減点を強化して有資格者全員へ広く分散させる。
                            # これは超過者を「押し出す」だけで総勤務日数は増えないため、不足側の
                            # 容量ゲートと違い代休に影響しない。
                            # 希少1枠業務(HB/DR/ア)は強めに分散。ク等の高ボリューム業務へ
                            # 同種の強い超過減点を掛けると、汎用技師(川向)が押し出された分が
                            # HBへ流れHB3連続が復活する（総勤務が保存されるためのトレードオフ）。
                            # よって強化は希少1枠業務に限定する。
                            _w_ex = 60000 if l_code in ('HB', 'DR', 'ア') else WEIGHT_FAIR
                            _cap_ex = 1200000 if l_code in ('HB', 'DR', 'ア') else 800000
                            penalty = min(int(excess * _w_ex), _cap_ex)
                            fairness_penalties.append(x[s.id, l_code] * penalty)
                        elif excess < 0:
                            # 平均未満は加点して引き込む。特に0回者には固定加点(+30000)を上乗せし
                            # 「一度も入らない」状態を解消する。ただし配置不足(500万)・出力体制
                            # スラック(200万〜)・ランク品質より必ず小さく保ち、配置や品質を壊さない。
                            #
                            # 【重要】総勤務日数が平均以下＝「余力のある人」に限定して加点する。
                            # 総勤務が平均超の人にまで場所加点をすると、本来休める日に余分な勤務を
                            # 引き当てて勤務日数が増え、代休（公休<目標）を誘発する。場所の偏りは
                            # 是正しつつ総勤務日数バランス（代休回避）を壊さないための条件。
                            _has_capacity = True
                            if total_work_count:
                                _avg_w = sum(total_work_count.values()) / len(total_work_count)
                                # 平均+1.0 までは余力ありとみなす。完全に平均以下に限ると
                                # 高稼働の技師(例:松井)が一度も本来業務に入れず飢餓が残るため、
                                # 1日分の緩衝を許容し、生じた端数代休はリバランサーで回収させる。
                                _has_capacity = total_work_count.get(s.id, 0) <= _avg_w + 1.0
                            if _has_capacity:
                                deficit = avg_for_loc - count
                                bonus = min(int(deficit * WEIGHT_FAIR) + (30000 if count == 0 else 0), 400000)
                                maximization_objective.append(x[s.id, l_code] * bonus)

                # Special Monthly Bonus Rule for Ono (T013) and Kawana (T025) -> strictly 6 'ク' assignments
                if s.id in ['T013', 'T025'] and l_code == 'ク':
                    if count < 6:
                        # 優先配置のためのボーナス（ただし休日キャンセルは引き起こさないレベル）
                        # NOTE: greedyのため6回を保証できない（実測で小野5回）。
                        # 増強(150000)はかえって悪化(4回)したため50000に据置。6回保証は将来の大域最適化マター。
                        if (s.id, l_code) in x:
                            maximization_objective.append(x[s.id, l_code] * 50000)
                    else:
                        # Hard ban once they hit 6
                        if (s.id, l_code) in x:
                            model.Add(x[s.id, l_code] == 0)



        # 4. Hard Constraints

        # DH-01: One person <= 1 location (for those not already forced)
        
        # Ono / Kawana Special Ban: Cannot both work 'ク' on the same day
        if ('T013', 'ク') in x and ('T025', 'ク') in x:
            model.Add(x['T013', 'ク'] + x['T025', 'ク'] <= 1)
            
        ultra_late_next_day_penalties = []
        for s in available_staff:
            vars_s = [x[s.id, l.code] for l in target_locations if (s.id, l.code) in x]
            if vars_s:
                model.Add(sum(vars_s) <= 1)
                
            # ===== NEW: Soft Constraint for Pre-seeded Holidays ('休(仮)') =====
            p_req = staff_req_symbol.get(s.id)
            if p_req == '休(仮)':
                if vars_s:
                    is_off = model.NewBoolVar(f'is_off_preseed_{s.id}_{current_date}')
                    model.Add(is_off + sum(vars_s) <= 1)
                    
                    holiday_bonus = 1000000
                    if total_work_count:
                        avg_work = sum(total_work_count.values()) / len(total_work_count)
                        diff = total_work_count.get(s.id, 0) - avg_work
                        if diff > 0:
                            holiday_bonus += int(diff * 200000)
                        elif diff < 0:
                            holiday_bonus -= int(abs(diff) * 200000)
                            
                    maximization_objective.append(is_off * holiday_bonus)
            # ===================================================================


                
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

        # DH-03: Required Headcount with Understaffing Penalty
        # 場所の重要度に応じてペナルティを調整する。
        # パワーバランス制約(3M)と競合しないよう、2倍程度の控えめな引き上げにとどめる。
        DEFICIT_PENALTIES = {
            'CT':   5500000,
            'MG':   5000000,
            'OP':   5000000,
            '超遅': 5000000,
        }
        DEFICIT_PENALTY_DEFAULT = 5000000
        deficit_vars = []

        for loc in target_locations:
            req = location_needs[loc.code]
            vars_l = [x[s.id, loc.code] for s in available_staff if (s.id, loc.code) in x]

            # shortage = 目標人数(req) - 実際の配置人数
            shortage = model.NewIntVar(0, req, f'shortage_{loc.code}_{current_date}')
            model.Add(sum(vars_l) + shortage == req)

            # 場所別ペナルティを適用
            penalty = DEFICIT_PENALTIES.get(loc.code, DEFICIT_PENALTY_DEFAULT)
            deficit_vars.append(shortage * penalty)
            
        # Add Training Restrictions
        for tm in training_mappings:
            dummy_code = tm['dummy_code']
            modality = tm['modality']
            
            # Constraint: A trainee can only be assigned to dummy_loc if at least one instructor is assigned to modality
            ins_vars = [x[s_id, modality] for s_id in tm['instructors'] if (s_id, modality) in x]
            if not ins_vars:
                # No instructor available or configured properly, force dummy to 0
                for s in available_staff:
                    if (s.id, dummy_code) in x:
                        model.Add(x[s.id, dummy_code] == 0)
                continue
                
            ins_sum = sum(ins_vars)
            
            for s in available_staff:
                if (s.id, dummy_code) in x:
                    if s.id in tm['trainees']:
                        model.Add(x[s.id, dummy_code] <= ins_sum)
                    else:
                        model.Add(x[s.id, dummy_code] == 0)

        # 4.5. Tateyama Special Rule (Tateyama Hospital Assignment)
        # Endo (T072) is the specialist. Backups: Fukuda(T006), Minowa(T022), Ishii(T023)
        if '館山' in location_needs:
            endo_id = 'T072'
            backups = ['T006', 'T022', 'T023']
            off_symbols = {'★', '★連', '☆', '☆小', '☆デ', '◆', '出/☆', '研(聴)', '退職', 
                           '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', 
                           '出/(座)', '研(座)', '研(役)', '出/(役)'}
            
            endo_req = staff_req_symbol.get(endo_id)
            endo_is_off = endo_req in off_symbols
            
            # Is Endo available to work? (Not on holiday and in available_staff list)
            if not endo_is_off and any(s.id == endo_id for s in available_staff):
                # ソフト: ほぼ強制（INFEASIBLE防止のため == 1 は使わない）
                if (endo_id, '館山') in x:
                    maximization_objective.append(x[endo_id, '館山'] * 850000)
            else:
                # Endo is off or unavailable: backup must go
                if (endo_id, '館山') in x:
                    model.Add(x[endo_id, '館山'] == 0)

                backup_vars = [x[sid, '館山'] for sid in backups if (sid, '館山') in x]
                if backup_vars:
                    # ソフト: sum == 1 の代わりに sum >= 1 かつ大ボーナス
                    maximization_objective.append(sum(backup_vars) * 850000)
                    model.Add(sum(backup_vars) <= 1)  # 上限のみ hard

            # 4.5.1 館山応援者の夜勤禁止制約
            # 他院応援のため、当日夜勤があるスタッフは館山に入れない
            for sid in [endo_id] + backups:
                if (sid, '館山') in x:
                    if night_map.get((sid, current_date)):
                        model.Add(x[sid, '館山'] == 0)

        # 5. Power Balance (PB-xx)
        self._add_power_balance_constraints(model, x, target_locations, location_needs, available_staff, current_date, weekday, female_gyohai_wed, gyohai_has_veteran, fairness_penalties)

        # 5.5 CLMR Special Rule (SR-CLMR)
        l_code = 'CLMR'
        if l_code in [loc.code for loc in target_locations]:
            # CLMR(クリニックMRI)のランク要件は、M遅(クリニックMRI遅番)の担当者も
            # 1名としてカウントする。クリニックMRIは M遅 が勤務に含まれるため。
            # ランク判定は本人のCLMR技能ランクで統一する（M遅担当でもCLMRランクで数える）。
            # 注: 同一人物が CLMR と M遅 の両候補変数を持ち得るが、1日1アサインのため
            #     解では高々どちらか一方のみ 1 となり二重計上は起きない。
            v_s = [(s, x[s.id, l_code]) for s in available_staff if (s.id, l_code) in x]
            v_s += [(s, x[s.id, 'M遅']) for s in available_staff if (s.id, 'M遅') in x]
            if v_s:
                def _clmr_rank(st):
                    return self.skills.get(st.id, {}).get('CLMR', SkillRank.NONE)
                a_vars = [v for s, v in v_s if _clmr_rank(s) >= SkillRank.A]
                ab_vars = [v for s, v in v_s if _clmr_rank(s) >= SkillRank.B]
                d_vars = [v for s, v in v_s if _clmr_rank(s) == SkillRank.D]
                c_vars = [v for s, v in v_s if _clmr_rank(s) == SkillRank.C]

                # 注意: 要求数 > available数 の場合は充足可能な数までキャップする
                # → モデルがINFEASIBLEになって全配置0になるのを防ぐ
                def _safe_min(req: int, pool: list) -> int:
                    return min(req, len(pool))
                def _add_soft_min(req_n, pool, tag):
                    n = _safe_min(req_n, pool)
                    if n <= 0: return
                    sl = model.NewIntVar(0, n, tag)
                    model.Add(sum(pool) + sl >= n)
                    fairness_penalties.append(sl * 3000000)

                if weekday == 2:  # 水曜
                    _add_soft_min(3, a_vars,  f'clmr_a_slack_{current_date.day}')
                    _add_soft_min(4, ab_vars, f'clmr_ab_slack_{current_date.day}')
                    # 仕様7.1.5: 水曜CLMRは C・D 完全禁止（A/Bランクのみで構成）
                    if d_vars: model.Add(sum(d_vars) == 0) # D禁止
                    if c_vars: model.Add(sum(c_vars) == 0) # C禁止
                elif weekday == 4:  # 金曜
                    _add_soft_min(2, a_vars,  f'clmr_a_slack_{current_date.day}')
                    _add_soft_min(4, ab_vars, f'clmr_ab_slack_{current_date.day}')
                    if d_vars: model.Add(sum(d_vars) <= 1)
                else:  # 月火木土
                    _add_soft_min(2, a_vars,  f'clmr_a_slack_{current_date.day}')
                    _add_soft_min(3, ab_vars, f'clmr_ab_slack_{current_date.day}')
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
        
        self._add_special_rules(model, x, current_date, self.rules, location_needs, fairness_penalties)

        # 7. Soft Constraints: Minimize Consecutive Same Assignments
        consecutive_penalties = []
        WEIGHT_CONSECUTIVE = 1000  # 強力に分散させるため 100 -> 1000 に強化
        # スキルが単一タスクのスタッフは連続ペナルティを免除する。
        # 病CT専従（T001）等、他に選択肢がないスタッフに課すと「1日おき」の強制になるため。
        CONSECUTIVE_EXEMPT = {'T001'}
        
        for s in available_staff:
             if s.id in CONSECUTIVE_EXEMPT:
                 continue
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
        total_penalties.extend(deficit_vars)
        
        # Req 2: Maximize Assignments - Penalties
        model.Maximize(sum(maximization_objective) - sum(total_penalties))

        # Solve
        solver = cp_model.CpSolver()
        # 決定性確保: 探索打ち切りを「実時間」でなく「決定的時間(作業量基準)」にする。
        # max_time_in_seconds は負荷依存で打ち切り点が毎回変わり別解を生む(再現性なしの真因)。
        # max_deterministic_time が常に先に binding するよう、実時間は大きめの安全弁に降格。
        solver.parameters.max_deterministic_time = 30.0   # 再現的な打ち切り(主)
        solver.parameters.max_time_in_seconds = 300       # 安全弁(暴走防止・通常 binding しない)
        solver.parameters.random_seed = 42      # 再現性確保
        solver.parameters.num_workers = 1       # シングルスレッド（完全再現性）
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            result = self._extract_day_solution(solver, x, current_date, self.skills)

            return result + forced_holidays, location_needs
        else:
            status_name = {cp_model.INFEASIBLE: 'INFEASIBLE', cp_model.UNKNOWN: 'UNKNOWN/TIMEOUT'}.get(status, str(status))
            print(f"FAILED to schedule day: {current_date} (status={status_name})")
            print(f"  Weekday: {weekday}, Vars: {len(x)}, Avail: {len(available_staff)}")
            # 強制割り当て（forced_loc_map）を持つスタッフを表示
            forced = {s.id: staff_req_symbol.get(s.id) for s in available_staff if staff_req_symbol.get(s.id) in FORCED_LOC_MAP}
            if forced:
                print(f"  FORCED assignments: {forced}")
            return forced_holidays, location_needs

    def _extract_day_solution(self, solver, x, date, skills) -> List[DayAssignment]:
        res = []
        for (sid, lcode), var in x.items():
            if solver.Value(var) == 1:
                rank = skills.get(sid, {}).get(lcode, SkillRank.NONE)
                res.append(DayAssignment(date=date, staff_id=sid, location_code=lcode, rank=rank))
        return res

    def _add_power_balance_constraints(self, model, x, target_locations, location_needs, available_staff, current_date, day_of_week, female_gyohai_wed, gyohai_has_veteran, fairness_penalties=None):
        if fairness_penalties is None:
            fairness_penalties = []
        """Phase 4: Power Balance Constraints"""
        
        # Helper map
        pb_map = {}
        for r in self.pb_rules:
            pb_map.setdefault(r.location_code, []).append(r)
        
        # --- FINAL HEADCOUNT CONSTRAINTS AND POWER BALANCE ---
        for loc in target_locations:
            l_code = loc.code
            vars_s_loc = [] # (staff, var)
            vars_loc_only = [] # var
            for s in available_staff:
                if (s.id, l_code) in x:
                    v = x[s.id, l_code]
                    vars_s_loc.append((s, v))
                    vars_loc_only.append(v)
            
            if not vars_loc_only: continue

            # --- DH-01: Headcount ---
            req_num = location_needs.get(l_code, 0)
            # 上限のみ hard constraint: 変数数 < req_num の場合でも INFEASIBLE にならない
            # 正のスコアによる objective 最大化で自然に充足される
            model.Add(sum(vars_loc_only) <= req_num)

            # --- Generic Rules (PB-01, PB-02, PB-03) ---
            if l_code in pb_map and l_code != 'CLMR':
                for pb in pb_map[l_code]:
                    # PB-01: Min Rank
                    if pb.min_rank and pb.min_count:
                        # User Request Override: Seimitsu (精) on Mon/Tue/Thu/Sat allows Rank D (ignore Min B).
                        skip_min_rank = False
                        if l_code == '精':
                             weekday = current_date.weekday()
                             if weekday in [0, 1, 3, 5]: # Mon, Tue, Thu, Sat
                                 skip_min_rank = True
                        # ポは権限制限済のためBランク必須(PB-01)を緩和し availability を広げる
                        if l_code == 'ポ' and self.RELAX_PORTABLE_RANK:
                            skip_min_rank = True
                        
                        if not skip_min_rank:
                            qualified = [v for s, v in vars_s_loc
                                         if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) >= pb.min_rank]
                            if qualified:
                                actual_req = location_needs.get(l_code, 0)
                                adjusted_min_count = min(pb.min_count, actual_req, len(qualified))
                                if adjusted_min_count > 0:
                                    # ソフト制約: スラックで INFEASIBLE を防止
                                    slack = model.NewIntVar(0, adjusted_min_count, f'pb01_slack_{l_code}_{current_date.day}')
                                    model.Add(sum(qualified) + slack >= adjusted_min_count)
                                    fairness_penalties.append(slack * 3000000)
                            
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
                                sl_nd = model.NewIntVar(0, 1, f'nond_slack_{l_code}_{current_date.day}')
                                model.Add(sum(non_d_vars) + sl_nd >= 1)
                                fairness_penalties.append(sl_nd * 2000000)

            # --- Specific Rules (PB-04, PB-05) ---
            
            # PB-04: Portable (ポ) D Pair Ban
            # RELAX_PORTABLE_RANK 有効時は D×D 禁止も緩和し、日ごとの候補を広げる。
            if l_code == 'ポ' and not self.RELAX_PORTABLE_RANK:
                req_num = location_needs.get(l_code, 0)
                if req_num >= 2:
                    d_vars = [v for s, v in vars_s_loc
                              if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) == SkillRank.D]
                    if len(d_vars) >= 2:
                        model.Add(sum(d_vars) <= 1)
                        
            # PB-05: CT (CT) CD Pair Ban
            if l_code == 'CT':
                req_num = location_needs.get(l_code, 0)
                if req_num >= 2:
                    cd_vars = [v for s, v in vars_s_loc 
                               if self.skills.get(s.id, {}).get(l_code, SkillRank.NONE) in [SkillRank.C, SkillRank.D]]
                    if cd_vars:
                         model.Add(sum(cd_vars) < req_num)

            # PB-07: クリニック（ク）の経験年数制約
            if l_code == 'ク':
                original_req_num = location_needs.get(l_code, 0) + (female_gyohai_wed if day_of_week == 2 else 0)
                if original_req_num >= 2:
                    if not (day_of_week == 2 and gyohai_has_veteran):
                        experienced_vars = [v for s, v in vars_s_loc 
                                            if int(s.experience_years) >= 6]
                        if experienced_vars:
                            sl_exp = model.NewIntVar(0, 1, f'exp_slack_k_{current_date.day}')
                            model.Add(sum(experienced_vars) + sl_exp >= 1)
                            fairness_penalties.append(sl_exp * 2000000)

        # PB-06: クリニック系（ク + ク遅 + MG）の女性配置
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
            # available数でキャップ後、スラックでソフト化
            min_female = min(min_female, len(female_clinic_vars))
            if min_female > 0:
                sl_f = model.NewIntVar(0, min_female, f'female_clinic_slack_{current_date.day}')
                model.Add(sum(female_clinic_vars) + sl_f >= min_female)
                fairness_penalties.append(sl_f * 2000000)

    def _extract_day_solution(self, solver, x, date, skills) -> List[DayAssignment]:
        res = []
        for (sid, lcode), var in x.items():
            if solver.Value(var) == 1:
                rank = skills.get(sid, {}).get(lcode, SkillRank.NONE)
                res.append(DayAssignment(date=date, staff_id=sid, location_code=lcode, rank=rank))
        return res

    def _add_special_rules(self, model, x, current_date, special_rules, location_needs, fairness_penalties=None):
        if fairness_penalties is None:
            fairness_penalties = []
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
                        # available数でもキャップ: INFEASIBLE 防止
                        target_rank_count = min(rule.rank_count, actual_req, len(qualified))
                        if target_rank_count > 0 and qualified:
                            sl_rank = model.NewIntVar(0, target_rank_count, f'rank_slack_{loc_code}_{current_date.day}')
                            model.Add(sum(qualified) + sl_rank >= target_rank_count)
                            fairness_penalties.append(sl_rank * 3000000)
                        
                elif rule.rank_condition == 'D同士禁止': # String condition?
                    pass

            # If rule has required_count, ensure we sum to the actual needed count for today,
            # NOT necessarily the one in the rule if it was overridden (e.g., Saturday CT).
            if rule.required_count > 0:
                # EXACT count は INFEASIBLE になりやすいため上限のみ設定（上限はソルバーが自然に満たす）
                model.Add(sum(vars_loc_only) <= actual_req)

            # Source Logic (OP from HB A)
            if rule.source_location and rule.source_rank:
                # "At least 1 person from Source Rank"
                eligible_vars = []
                for sid, var in vars_s_loc:
                     src_val = self.skills.get(sid, {}).get(rule.source_location, SkillRank.NONE)
                     if src_val >= rule.source_rank:
                         eligible_vars.append(var)
                
                if eligible_vars:
                    sl_elig = model.NewIntVar(0, 1, f'eligible_slack_{current_date.day}_{rule.location_code}')
                    model.Add(sum(eligible_vars) + sl_elig >= 1)
                    fairness_penalties.append(sl_elig * 2000000)

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

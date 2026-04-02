import calendar
from datetime import date, timedelta
from typing import Dict, List, Tuple

try:
    import jpholiday
except ImportError:
    jpholiday = None

class OnCallScheduler:
    def __init__(self, staff_list, year: int, month: int):
        self.staff_list = staff_list
        self.year = year
        self.month = month
        self.days_in_month = calendar.monthrange(year, month)[1]
        
    def _is_holiday(self, d: date) -> bool:
        if jpholiday and jpholiday.is_holiday(d):
            return True
        return d.weekday() == 6 or (d.month == 1 and d.day in [1, 2, 3])

    def schedule(self, day_result_list, night_assignments, requests) -> Tuple[Dict[int, Dict[str, str]], Dict[str, int]]:
        night_map = {}
        for na in night_assignments:
            # Note: na.date could be from previous month for history, we only care about exact hits
            night_map[(na.staff_id, na.date)] = True
                
        day_map = {}
        for da in day_result_list:
            day_map[(da.staff_id, da.date)] = da.location_code
                
        active_staff = [s for s in self.staff_list if s.status == '在籍' and getattr(s, 'can_oncall', True)]
        oncall_counts = {s.id: 0 for s in active_staff}
        staff_exp = {s.id: s.experience_years for s in active_staff}
        staff_night_hb = {s.id: getattr(s, 'night_hb', False) for s in active_staff}
        
        night_hb_covered = {}
        for day in range(1, self.days_in_month + 1):
            day_d = date(self.year, self.month, day)
            assigned_night = [s for s in active_staff if night_map.get((s.id, day_d))]
            night_hb_covered[day] = any(getattr(s, 'night_hb', False) for s in assigned_night)
        
        oncall_results = {}
        LATE_LOCATIONS = {'遅番', '超遅', 'ク遅', 'M遅'}
        
        request_map = {}
        for r in requests:
            if r.date.year == self.year and r.date.month == self.month:
                request_map[(r.staff_id, r.date.day)] = r.symbol
                
        def is_blocked(sid, day_num):
            sym = request_map.get((sid, day_num))
            return sym in ['17業', '17休']
        
        for day in range(1, self.days_in_month + 1):
            daily_active_staff = [s for s in active_staff if not is_blocked(s.id, day)]
            
            d = date(self.year, self.month, day)
            d_next = d + timedelta(days=1)
            d_prev = d - timedelta(days=1)
            
            is_today_hol = self._is_holiday(d)
            is_tmrw_hol = self._is_holiday(d_next)
            
            night_lacks_hb = not night_hb_covered.get(day, True)
            
            result = {}
            
            if is_today_hol:
                post_night_staff = [s.id for s in daily_active_staff if night_map.get((s.id, d_prev))]
                today_day_staff = [s.id for s in daily_active_staff if day_map.get((s.id, d)) not in [None, '休', '○'] and not night_map.get((s.id, d))]
                
                if post_night_staff:
                    post_night_staff.sort(key=lambda sid: oncall_counts[sid])
                    result['第1拘束'] = post_night_staff[0]
                    oncall_counts[post_night_staff[0]] += 1
                
                if today_day_staff:
                    res_1 = result.get('第1拘束')
                    # If 1st person is inexperienced (<3 yrs), heavily penalize other inexperienced staff
                    penalty_threshold = 3
                    def score_fn(sid):
                        score = oncall_counts[sid]
                        if res_1 and staff_exp.get(res_1, 10) < penalty_threshold and staff_exp.get(sid, 10) < penalty_threshold:
                            score += 100
                        if night_lacks_hb and staff_night_hb.get(sid, False):
                            score -= 1000
                        return score
                        
                    today_day_staff.sort(key=score_fn)
                    for sid in today_day_staff:
                        if sid != res_1:
                            result['第2拘束'] = sid
                            oncall_counts[sid] += 1
                            break
                            
            elif is_tmrw_hol:
                tmrw_night_staff = [s.id for s in daily_active_staff if night_map.get((s.id, d_next))]
                tmrw_day_staff = [s.id for s in daily_active_staff if day_map.get((s.id, d_next)) not in [None, '休', '○'] and not night_map.get((s.id, d_next))]
                
                if tmrw_night_staff:
                    tmrw_night_staff.sort(key=lambda sid: oncall_counts[sid])
                    result['第1拘束'] = tmrw_night_staff[0]
                    oncall_counts[tmrw_night_staff[0]] += 1
                    
                if tmrw_day_staff:
                    res_1 = result.get('第1拘束')
                    penalty_threshold = 3
                    def score_fn(sid):
                        score = oncall_counts[sid]
                        if res_1 and staff_exp.get(res_1, 10) < penalty_threshold and staff_exp.get(sid, 10) < penalty_threshold:
                            score += 100
                        if night_lacks_hb and staff_night_hb.get(sid, False):
                            score -= 1000
                        return score
                        
                    tmrw_day_staff.sort(key=score_fn)
                    for sid in tmrw_day_staff:
                        if sid != res_1:
                            result['第2拘束'] = sid
                            oncall_counts[sid] += 1
                            break
                            
            else:
                candidates = []
                for s in daily_active_staff:
                    loc_today = day_map.get((s.id, d))
                    is_night_today = night_map.get((s.id, d))
                    if not loc_today or loc_today in ['休', '○'] or loc_today in LATE_LOCATIONS or is_night_today:
                        continue
                        
                    loc_tmrw = day_map.get((s.id, d_next))
                    is_night_tmrw = night_map.get((s.id, d_next))
                    # For end of month where next day is not assigned, we assume it's OK if it's missing (defaults to free).
                    # Actually, if missing, it means next month. Handled permissively.
                    if loc_tmrw in ['休', '○'] or loc_tmrw in LATE_LOCATIONS or is_night_tmrw:
                        continue
                        
                    candidates.append(s.id)
                    
                if len(candidates) >= 1:
                    def first_score_fn(sid):
                        score = oncall_counts[sid]
                        if night_lacks_hb and staff_night_hb.get(sid, False):
                            score -= 1000
                        return score
                        
                    candidates.sort(key=first_score_fn)
                    res_1 = candidates[0]
                    result['第1拘束'] = res_1
                    oncall_counts[res_1] += 1
                    
                    # Sort remaining for 2nd slot with penalty for low experience pair
                    remaining = candidates[1:]
                    if remaining:
                        penalty_threshold = 3
                        def score_fn(sid):
                            score = oncall_counts[sid]
                            if staff_exp.get(res_1, 10) < penalty_threshold and staff_exp.get(sid, 10) < penalty_threshold:
                                score += 100
                            if night_lacks_hb and staff_night_hb.get(sid, False):
                                score -= 1000
                            return score
                        remaining.sort(key=score_fn)
                        result['第2拘束'] = remaining[0]
                        oncall_counts[remaining[0]] += 1
                    
            oncall_results[day] = result
            
        print(f"  拘束割り当て完了", flush=True)
        return oncall_results, oncall_counts


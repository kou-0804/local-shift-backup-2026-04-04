"""Single source for the holiday/work symbol vocabularies and a pure,
solver-free recomputation of off (公休) / daikyu (代休) counts from the
assignment dicts. Mirrors main.py assign_monthly_off_days exactly so stats
can be refreshed after a manual edit without re-running the solver."""
import calendar
from datetime import date
import jpholiday

# Copied EXACTLY from main.py assign_monthly_off_days (single source now).
PURE_HOLIDAY_SYMS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '出/☆', '退職', '☆育'}
CONDITIONAL_HOLIDAY_SYMS = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
FORCED_WORK_SYMS = {'業配', '業出', '出', '会議', '全会', '講', '勤', '出/講', '出/(聴)', '出/(発)2', '17業'}


def _is_public_off(d: date) -> bool:
    is_jan_holiday = (d.month == 1 and d.day in (1, 2, 3))
    return d.weekday() == 6 or jpholiday.is_holiday(d) or is_jan_holiday


def _classify(sid, d, dnum, day_assignments, night_assignments, requests):
    """その日のステータスを分類（main.py assign_monthly_off_days:97-132 と同一）。
    返り値: 'work' | 'off' | 'half' | 'blank'。最初に一致した分岐が優先（順序依存）。"""
    req = requests.get(dnum, {}).get(sid)
    is_night = sid in night_assignments.get(dnum, [])
    is_ake = sid in night_assignments.get(dnum - 1, [])

    # existing_loc: dict から復元。複数エントリーがある場合は '休' を優先
    # （main.py day_assign_map の '休' 優先ロジックを再現）。
    locs = [loc for loc, ids in day_assignments.get(dnum, {}).items() if sid in ids]
    if '休' in locs:
        existing_loc = '休'
    elif locs:
        existing_loc = locs[0]
    else:
        existing_loc = None

    is_public_off = _is_public_off(d)

    if is_night:
        return 'work'        # 夜勤当日 = 勤務
    elif is_ake:
        return 'work'        # 明け = 勤務扱い（公休カウント外）
    elif req in FORCED_WORK_SYMS:
        return 'work'        # 強制勤務（17業含む）
    elif req == '出/☆':
        return 'half'        # 半休（午前勤務・午後休）= 公休0.5カウント
    elif req in PURE_HOLIDAY_SYMS or req == '休' or existing_loc == '休':
        return 'off'         # 明示的な公休マーカーあり
    elif req in CONDITIONAL_HOLIDAY_SYMS:
        if is_public_off:
            return 'off'     # 日曜祝日の研修等は公休
        else:
            return 'work'    # 平日の研修等は勤務
    elif is_public_off and not (existing_loc and existing_loc not in ['休', '○']):
        return 'off'         # 日曜・祝日（特別割当なし）
    elif existing_loc and existing_loc not in ['休', '○']:
        return 'work'        # 日勤配置あり
    elif req == '17休':
        return 'off'         # 17休単独（日勤配置なし）= 公休
    elif req and req != '休(仮)':
        return 'work'        # 勤務申請あり
    else:
        return 'blank'       # 未割当平日（実質公休）


def recompute_off_daikyu(day_assignments, night_assignments, requests,
                         staff_ids, year, month, target_holidays):
    """Return (off_counts: dict[sid,float], daikyu_counts: dict[sid,float]).
    off = #off + #blank + 0.5*#half ; daikyu = max(0, target - off)."""
    num_days = calendar.monthrange(year, month)[1]
    off_counts, daikyu_counts = {}, {}
    for sid in staff_ids:
        explicit_off = 0.0   # 明示公休(★☆/日祝) or 付与済み '休' マーカー
        half = 0
        blank = 0
        for dnum in range(1, num_days + 1):
            d = date(year, month, dnum)
            status = _classify(sid, d, dnum, day_assignments, night_assignments, requests)
            if status == 'off':
                explicit_off += 1.0
            elif status == 'half':
                half += 1
            elif status == 'blank':
                blank += 1
            # 'work' contributes 0
        # 余剰の空欄は公休に数えない: 規定 target へ到達する分の blank のみカウントする
        # （main.py assign_monthly_off_days の blanks_quota と同一ロジックで整合）。
        # ユーザー方針(2026-07): 規定人数充足で不要な日は '休' を付けず空欄＝公休外。
        blanks_counted = min(blank, max(0, target_holidays - explicit_off))
        off = explicit_off + blanks_counted + 0.5 * half
        off_counts[sid] = off
        dk = max(0.0, target_holidays - off)
        daikyu_counts[sid] = dk
    return off_counts, daikyu_counts


from collections import defaultdict


def _day_of(iso_or_day):
    """Accept 'YYYY-MM-DD', date, or int day -> int day."""
    if isinstance(iso_or_day, int):
        return iso_or_day
    if isinstance(iso_or_day, date):
        return iso_or_day.day
    return int(str(iso_or_day).split('-')[2])


def recompute_stats(day_assignments, night_assignments, requests, technicians,
                    year, month, target_holidays, *,
                    daily_location_needs=None, staff_scope=None):
    """Solver-free recompute of off/daikyu/coverage/holiday_deficit/consecutive/
    night-HB. Mirrors main.py:19-185 (via recompute_off_daikyu) + main.py:1210-1225.
    Returns a plain JSON-able dict. `skill`/PB warnings are P3 (not here)."""
    num_days = calendar.monthrange(year, month)[1]
    active = [t for t in technicians if getattr(t, 'status', '在籍') == '在籍']
    if staff_scope is not None:
        active = [t for t in active if t.id in staff_scope]
    staff_ids = [t.id for t in active]

    off_counts, daikyu_counts = recompute_off_daikyu(
        day_assignments, night_assignments, requests,
        staff_ids, year, month, target_holidays)

    # holiday_deficit mirrors daikyu (off < target).
    holiday_deficit = [
        {"staff_id": sid, "off": off_counts[sid], "target": target_holidays,
         "short": round(target_holidays - off_counts[sid], 1)}
        for sid in staff_ids if off_counts[sid] < target_holidays
    ]

    # consecutive: any run of work-status days >= 7. Reuse the P2a-1 classifier so
    # status semantics are identical; 出/☆ half counts as work (main.py:946-949).
    consecutive = []
    for sid in staff_ids:
        run = 0
        start_day = None
        for dn in range(1, num_days + 1):
            d = date(year, month, dn)
            st = _classify(sid, d, dn, day_assignments, night_assignments, requests)
            working = st in ('work', 'half')
            if working:
                if run == 0:
                    start_day = dn
                run += 1
                if run >= 7:
                    consecutive.append({
                        "staff_id": sid,
                        "start": date(year, month, start_day).isoformat(),
                        "len": run})
            else:
                run = 0

    # coverage vs daily_location_needs (fold クL->ク; skip parenthesized).
    coverage = []
    if daily_location_needs:
        assigned_by_day = defaultdict(lambda: defaultdict(list))
        for dn, locs in day_assignments.items():
            for loc, ids in locs.items():
                assigned_by_day[int(dn)][loc].extend(ids)
        for key, loc_needs in daily_location_needs.items():
            dn = _day_of(key)
            for loc_code, required in loc_needs.items():
                if loc_code.startswith('(') and loc_code.endswith(')'):  # main.py:1213
                    continue
                if not required or required <= 0:
                    continue
                assigned = len(assigned_by_day[dn].get(loc_code, []))
                if loc_code == 'ク':
                    assigned += len(assigned_by_day[dn].get('クL', []))  # fold
                if assigned < required:
                    coverage.append({
                        "date": date(year, month, dn).isoformat(),
                        "location": loc_code, "required": required,
                        "assigned": assigned, "short": required - assigned})

    # night-HB gaps (main.py:1218-1225).
    by_id = {t.id: t for t in technicians}
    night_hb_gaps = [
        int(dn) for dn, ids in night_assignments.items()
        if not any(getattr(by_id.get(i), 'night_hb', False) for i in ids)
    ]

    return {
        "off_counts": off_counts,
        "daikyu_counts": daikyu_counts,
        "holiday_deficit": holiday_deficit,
        "coverage": coverage,
        "consecutive": consecutive,
        "night_hb_gaps": sorted(night_hb_gaps),
    }

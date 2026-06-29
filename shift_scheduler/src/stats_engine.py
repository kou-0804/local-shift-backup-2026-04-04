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
        off = 0.0
        for dnum in range(1, num_days + 1):
            d = date(year, month, dnum)
            status = _classify(sid, d, dnum, day_assignments, night_assignments, requests)
            if status == 'off':
                off += 1.0
            elif status == 'half':
                off += 0.5
            elif status == 'blank':
                off += 1.0   # unassigned weekday = effective rest (off_contrib=1.0)
            # 'work' contributes 0
        off_counts[sid] = off
        dk = max(0.0, target_holidays - off)
        daikyu_counts[sid] = dk
    return off_counts, daikyu_counts

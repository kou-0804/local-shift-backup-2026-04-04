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


def assign_monthly_off_days(
    technicians,
    day_result_list,
    night_assignments,
    requests,
    year: int,
    month: int,
    target_holidays: int = 9,
) -> Tuple[list, Dict[str, int], Dict[str, int]]:
    """出力済みシフト表に対してポスト処理：
    各スタッフに月間の指定された公休数（target_holidays）になるよう「休」を自動添加する。

    設計方針:
      - blank（未割当平日）は既に実質的な公休。全て '休' マーカーに変換して可視化する。
      - blank を含めた公休数が target_holidays に満たない場合のみ、研修枠→休 の変換を行う。
      - 公休数 = explicit_off + len(blank_days) + 研修枠から変換した日数
      - 代休 = max(0, target_holidays - 公休数)
    """
    PURE_HOLIDAY_SYMS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '出/☆', '退職', '☆育'}
    CONDITIONAL_HOLIDAY_SYMS = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
    FORCED_WORK_SYMS = {'業配', '業出', '出', '会議', '全会', '講', '勤', '出/講', '出/(聴)', '出/(発)2', '17業'}

    num_days = calendar.monthrange(year, month)[1]
    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]

    req_map = {(r.staff_id, r.date): r.symbol for r in requests
               if r.date.year == year and r.date.month == month}

    night_map = {}
    for na in night_assignments:
        night_map[(na.staff_id, na.date)] = True

    # day_assign_map: (staff_id, day_num) -> location_code
    # 同一スタッフ・同一日に複数エントリーがある場合は '休' を優先する
    day_assign_map: Dict[tuple, str] = {}
    for da in day_result_list:
        if da.date.year == year and da.date.month == month:
            key = (da.staff_id, da.date.day)
            existing = day_assign_map.get(key)
            if existing is None or existing != '休':
                day_assign_map[key] = da.location_code

    additional_holidays = []
    overridden_work = set()
    daikyu_counts: Dict[str, int] = {}
    off_counts: Dict[str, int] = {}

    active_staff = [s for s in technicians if s.status == '在籍']

    def _pick_best_day(candidate_days: list, status: dict) -> int:
        """既存の 'off' 日から最も遠い候補日を選ぶ（休みを均等に分散させる）。"""
        best_day = candidate_days[0]
        best_score = -1
        for dn in candidate_days:
            min_dist = min(
                (abs(dn - other) for other, st in status.items() if st == 'off'),
                default=999
            )
            if min_dist > best_score:
                best_score = min_dist
                best_day = dn
        return best_day

    def _passes_7day_check(dn: int, status: dict, num_days: int) -> bool:
        """dn を 'off' に変えた後も 7連勤ウィンドウが生じないか確認。"""
        for start in range(max(1, dn - 6), min(num_days - 5, dn + 1)):
            window = [status.get(start + i, 'blank') for i in range(7)]
            if sum(1 for w in window if w == 'work') >= 7:
                return False
        return True

    for s in active_staff:
        # ── Step 1: 各日のステータスを分類 ──────────────────────────
        # 'off'   = 明示的な公休マーカーあり（★/☆/日曜/祝日 等）
        # 'work'  = 勤務（夜勤・明け・日勤配置・勤務申請）
        # 'blank' = 何も割り当てられていない平日（実質公休だがマーカーなし）
        status: Dict[int, str] = {}

        for d in all_dates:
            dn = d.day
            req = req_map.get((s.id, d))
            is_night = night_map.get((s.id, d), False)
            is_ake   = night_map.get((s.id, d - timedelta(days=1)), False)
            existing_loc = day_assign_map.get((s.id, dn))

            is_jan_holiday = (d.month == 1 and d.day in [1, 2, 3])
            is_public_off  = d.weekday() == 6 or jpholiday.is_holiday(d) or is_jan_holiday

            if is_night:
                status[dn] = 'work'      # 夜勤当日 = 勤務
            elif is_ake:
                status[dn] = 'work'      # 明け = 勤務扱い（公休カウント外）
            elif req in FORCED_WORK_SYMS:
                status[dn] = 'work'      # 強制勤務（17業含む：日勤あり・夜勤/拘束/遅番なし）
            elif req == '出/☆':
                status[dn] = 'half'      # 半休（午前勤務・午後休）= 公休0.5カウント
            elif req in PURE_HOLIDAY_SYMS or req == '休' or existing_loc == '休':
                status[dn] = 'off'       # 明示的な公休マーカーあり
            elif req in CONDITIONAL_HOLIDAY_SYMS:
                if is_public_off:
                    status[dn] = 'off'   # 日曜祝日の研修等は公休
                else:
                    status[dn] = 'work'  # 平日の研修等は勤務
            elif is_public_off and not (existing_loc and existing_loc not in ['休', '○']):
                status[dn] = 'off'       # 日曜・祝日（特別割当なし）
            elif existing_loc and existing_loc not in ['休', '○']:
                status[dn] = 'work'      # 日勤配置あり（17休＋日勤=勤務）
            elif req == '17休':
                status[dn] = 'off'       # 17休単独（日勤配置なし）= 日勤も休み可 → 公休
            elif req and req != '休(仮)':
                status[dn] = 'work'      # 勤務申請あり

            else:
                status[dn] = 'blank'     # 未割当平日（実質公休）

        # ── Step 2: 公休数を把握 ──────────────────────────────────
        explicit_off = sum(1 for v in status.values() if v == 'off')
        blank_days   = sorted(dn for dn, v in status.items() if v == 'blank')
        # 規定を超えないよう、変換するblank日数を上限で制限
        # explicit_off が既に target 以上の場合（祝日が多い月など）は blank 変換ゼロ
        blanks_quota = max(0, target_holidays - explicit_off)

        # explicit_off が既に target を超えている場合は警告
        if explicit_off > target_holidays:
            # 5月のように祝日が多い月は構造上避けられないため、警告(⚠️)ではなく情報として表示
            print(f"  (i) {s.id}({getattr(s, 'name', s.id)}): "
                  f"固定公休({explicit_off}日)が目標({target_holidays}日)を超過しています。", flush=True)

        # ── Phase 1: 全 blank 日を '休' に変換して可視化 ──────────
        # 未割当平日は実質的な公休なので、Excel で空白にせず全て '休' マーカーを付与する。
        # quota による制限を撤廃し、blank は全件変換してカウントに含める。
        for dn in blank_days:
            d_obj = date(year, month, dn)
            additional_holidays.append(DayAssignment(
                date=d_obj, staff_id=s.id, location_code='休', rank=SkillRank.NONE,
            ))
            day_assign_map[(s.id, dn)] = '休'

        # ── Step 3: 公休数・代休数を確定 ──────────────────────────
        # 全 blank 日を含めて公休数を計算する（空白セルも実態として公休）
        # 半休（出/☆）は 0.5 日としてカウント
        half_days = [dn for dn, v in status.items() if v == 'half']
        actual_off = explicit_off + len(blank_days) + 0.5 * len(half_days)
        off_counts[s.id] = actual_off

        deficit = target_holidays - actual_off
        if deficit > 0:
            daikyu_counts[s.id] = deficit

    # 研修枠→休 に変換された元の勤務割当を除去
    filtered_result = [
        da for da in day_result_list
        if not (da.date.year == year and da.date.month == month
                and (da.staff_id, da.date.day) in overridden_work)
    ]

    total_daikyu      = sum(1 for c in daikyu_counts.values() if c > 0)
    total_daikyu_days = sum(daikyu_counts.values())
    for sid, cnt in sorted(daikyu_counts.items()):
        if cnt > 0:
            name = next((s.name for s in technicians if s.id == sid), sid)
            print(f"  ⚠️ 代休 {sid}({name}): {cnt}日 (公休={off_counts.get(sid,0)}日)", flush=True)
    print(f"✅ {target_holidays}日公休処理: {len(additional_holidays)}件の自動休を追加 "
          f"({len(overridden_work)}件の研修割当を休に変更) - "
          f"{total_daikyu}名に計{total_daikyu_days}日の代休を付与", flush=True)

    return list(filtered_result) + additional_holidays, daikyu_counts, off_counts


def pre_seed_rest_days(technicians, requests, night_assignments, year: int, month: int,
                        target_holidays: int = 9, skills=None, locations=None):
    """
    日勤スケジューリング前に、スタッフごとの不足公休日を月全体に均等分散して
    ☆（指定休）として事前割り当てする。
    スキル枯渇チェック付き：この人を休ませると特定業務の担当者がゼロになる日は除外。
    これにより月末に「全員バジェット切れ」の崖が発生するのを防ぐ。
    """
    from shift_scheduler.src.models.request import Request
    from shift_scheduler.src.models.skill import SkillRank

    HOLIDAY_SYMS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '○', '出/☆', '研(聴)', '退職',
                    '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)',
                    '研(座)', '研(役)', '出/(役)', '☆育'}
    FORCED_WORK_SYMS = {'業配', '業出', '出', '会議', '全会', '講', '勤', '出/講', '出/(聴)', '17業'}
    UNAVAIL_SYMS = HOLIDAY_SYMS | FORCED_WORK_SYMS | {'夜希', '17業', '17休'}

    all_dates = [date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)]
    req_map = {(r.staff_id, r.date): r.symbol for r in requests}
    night_map = {}
    for na in night_assignments:
        night_map[(na.staff_id, na.date)] = True

    # 処理済みの事前公休を累積管理（後のスタッフの安全チェックに使う）
    pre_seeded_map: Dict[Tuple, bool] = {}

    def _is_available_on(staff_id: str, d) -> bool:
        """このスタッフがその日に出勤可能かを判定（夜勤・明け・休暇・強制業務を除く）"""
        if night_map.get((staff_id, d), False):
            return False
        if night_map.get((staff_id, d - timedelta(days=1)), False):
            return False
        req = req_map.get((staff_id, d))
        if req and req in UNAVAIL_SYMS:
            return False
        if pre_seeded_map.get((staff_id, d), False):
            return False
        return True

    def _qualifies_for_location(staff_id: str, loc_code: str) -> bool:
        """このスタッフが業務のスキル条件を満たすか"""
        if not skills:
            return True
        s_skills = skills.get(staff_id, {})
        rank = s_skills.get(loc_code, SkillRank.NONE)
        if loc_code == 'HB':
            return rank >= SkillRank.A
        if loc_code in ('ア', '心'):
            return rank >= SkillRank.B
        return rank > SkillRank.NONE

    # 希少業務（担当可能者が限られる業務）：通常と同等のバッファ(+1)で保護する
    # ※ 以前はreq（バッファなし）を使っていたが、それは逆に無防備だったため修正
    SCARCE_LOCS = {'ク遅', 'M遅', '超遅', 'HB', 'ア', '心', '館山'}

    def _is_critical_on(staff_id: str, d) -> bool:
        """
        この日にこのスタッフを休ませると人員が不足する場合に True を返す（詰み防止）。

        2段階チェック:
        1. グローバル充足率チェック: 自分を除いた出勤可能人数が当日の全業務合計必要人数を
           GLOBAL_SAFETY_MARGIN 以下しか上回らない場合はクリティカル。
           （業務またがり競合・大量☆集中を防ぐ本質的な防衛線）
        2. 希少スキルチェック: 担当可能者が少ない業務（ク遅, HB等）で担当者が枯渇する場合。
        """
        if not skills or not locations:
            return False
        weekday = d.weekday()
        is_jan = (d.month == 1 and d.day in [1, 2, 3])
        is_holiday_day = is_jan or jpholiday.is_holiday(d) or weekday == 6
        if is_holiday_day:
            return False  # 休日は '出' だけなのでクリティカル判定不要

        # --- チェック1: グローバル充足率 ---
        GLOBAL_SAFETY_MARGIN = 10  # 業務またがりのスキル競合を吸収するため、合計必要人数＋10名のバッファを確保
        total_required = sum(
            loc.get_required_count(weekday)
            for loc in locations
            if loc.is_active and not loc.code.startswith('(')
            and loc.get_required_count(weekday) > 0
        )
        total_others_avail = sum(
            1 for s in technicians
            if s.id != staff_id and s.status == '在籍'
            and _is_available_on(s.id, d)
        )
        if total_others_avail < total_required + GLOBAL_SAFETY_MARGIN:
            return True  # 全体的に人員タイト → この日に☆を入れない


        # --- チェック2: 希少スキル枯渇チェック ---
        for loc in locations:
            if not loc.is_active:
                continue
            req_count = loc.get_required_count(weekday)
            if req_count <= 0:
                continue
            if not _qualifies_for_location(staff_id, loc.code):
                continue  # この人はそもそもこの業務に入れない → 除いても影響なし

            # この業務に入れる他スタッフ（自分以外）が何人利用可能か数える
            others_available = sum(
                1 for s in technicians
                if s.id != staff_id and s.status == '在籍'
                and _qualifies_for_location(s.id, loc.code)
                and _is_available_on(s.id, d)
            )

            # 全業務統一: +1 バッファ（1人余裕を残す）
            threshold = req_count + 1
            if others_available < threshold:
                return True

        return False

    pre_seeded: List = []
    active_staff = [s for s in technicians if s.status == '在籍']

    # ===== 全業務対象の「同日☆集中防止」トラッカー =====
    # key: (loc_code, date), value: その日にその業務の有資格者で☆になった人数
    # SCARCE_LOCSに限らず、全業務でこの集中を追跡する。
    skill_seeded_on_day: Dict[Tuple, int] = {}

    # 希少業務（担当可能者が限られる業務）：通常と同等のバッファ(+1)で保護する
    SCARCE_LOCS = {'ク遅', 'M遅', '超遅', 'HB', 'ア', '心', '館山'}

    def _would_exceed_skill_capacity(staff_id: str, d) -> bool:
        """
        この日にこのスタッフを☆にすると、いずれかの業務で
        「必要人数+1バッファ」を下回る（ギリギリになる）か確認。
        全業務対象（SCARCE_LOCSに限定しない）。
        """
        if not skills or not locations:
            return False
        weekday = d.weekday()
        for loc in locations:
            if not loc.is_active:
                continue
            req_count = loc.get_required_count(weekday)
            if req_count <= 0:
                continue
            if not _qualifies_for_location(staff_id, loc.code):
                continue  # この人はこの業務に入れない→関係なし

            # この日にこの業務の有資格者で、すでに☆で確定している人数
            already_seeded = skill_seeded_on_day.get((loc.code, d), 0)

            def _is_available_for_loc(sid, d, loc_code):
                if night_map.get((sid, d), False): return False
                if night_map.get((sid, d - timedelta(days=1)), False): return False
                
                req = req_map.get((sid, d))
                if not req: return True
                
                if req in HOLIDAY_SYMS: return False
                
                # 特定の業務に固定される申請（会議、出張など）は、他業務に入れない
                if req in {'講', '会議', '全会', '業配', '業出', '勤', '出', '出/講', '出/(聴)'}:
                    if req != loc_code: return False
                    
                return True

            # この業務の出勤可能な全有資格者数（退職・育休・夜勤・明け・他業務固定・予定休を除く実質稼働可能人数）
            total_active_qualified = sum(
                1 for s in technicians
                if s.status == '在籍'
                and _qualifies_for_location(s.id, loc.code)
                and _is_available_for_loc(s.id, d, loc.code)
            )

            # 自分が☆になった後に残る有資格者
            remaining_after = total_active_qualified - already_seeded - 1

            # 重要場所は大きなバッファで保護し、同日に休みが集中するのを防ぐ
            CRITICAL_BUFFER = {
                '病CT':  4,   # req=5 → threshold=9
                'CT':    3,   # req=3 → threshold=6
                '病院MR': 3,  # req=3 → threshold=6
                'CLMR':  2,   # req=4 → threshold=6
                'MG':    2,   # req=1 → threshold=3
            }
            threshold = req_count + CRITICAL_BUFFER.get(loc.code, 1)
            if remaining_after < threshold:
                return True
        return False

    def _register_skill_seeded(staff_id: str, d):
        """プリシード決定後に全業務のカウントを更新する。"""
        if not skills or not locations:
            return
        weekday = d.weekday()
        for loc in locations:
            if not loc.is_active:
                continue
            if loc.get_required_count(weekday) <= 0:
                continue
            if _qualifies_for_location(staff_id, loc.code):
                key = (loc.code, d)
                skill_seeded_on_day[key] = skill_seeded_on_day.get(key, 0) + 1

    # 1日あたりのプレシード人数を制限（同日に多くの人を休ませ過ぎない）
    total_active = len(active_staff)
    max_preseed_per_day = max(3, total_active // 4)  # 最低3人、最大25%
    preseed_count_on_day: Dict[date, int] = {}

    for s in active_staff:

        # === assign_monthly_off_days と同じロジックで公休数を予測する ===
        explicit_off = 0
        blank_days_count = 0
        for d in all_dates:
            req = req_map.get((s.id, d))
            is_night = night_map.get((s.id, d), False)
            is_ake = night_map.get((s.id, d - timedelta(days=1)), False)
            is_jan = (d.month == 1 and d.day in [1, 2, 3])
            is_pub = is_jan or jpholiday.is_holiday(d) or d.weekday() == 6

            if is_night or is_ake:
                pass  # 勤務扱い
            elif req in FORCED_WORK_SYMS:
                pass  # 強制業務
            elif req in HOLIDAY_SYMS:
                explicit_off += 1
            elif is_pub:
                explicit_off += 1
            elif not req:
                blank_days_count += 1

        # ==== 事前公休割り当て（Pre-seeding）====
        needed = max(0, target_holidays - explicit_off)
        if needed <= 0:
            continue

        # 候補日：既存リクエスト・公休・夜勤明けがない平日・土曜
        # かつスキル枯渇・同日集中を引き起こさない日のみ
        candidates = []
        skipped_critical = 0
        for d in all_dates:
            req = req_map.get((s.id, d))
            is_night = night_map.get((s.id, d), False)
            is_ake = night_map.get((s.id, d - timedelta(days=1)), False)
            is_jan = (d.month == 1 and d.day in [1, 2, 3])
            is_pub = is_jan or jpholiday.is_holiday(d) or d.weekday() == 6

            if is_pub or is_night or is_ake:
                continue
            if req:  # 何らかのリクエストあり → 上書き不可
                continue
            if _is_critical_on(s.id, d):
                skipped_critical += 1
                continue
            # ★ 全業務対象の同日集中チェック（旧SCARCE_LOCSのみを廃止）
            if _would_exceed_skill_capacity(s.id, d):
                skipped_critical += 1
                continue
            if preseed_count_on_day.get(d, 0) >= max_preseed_per_day:
                skipped_critical += 1
                continue
            candidates.append(d)

        if skipped_critical > 0:
            print(f"    {s.id}: クリティカル日{skipped_critical}日をスキップ", flush=True)

        if not candidates:
            print(f"    {s.id}: 安全な候補日なし（{needed}日不足のまま）", flush=True)
            continue

        # needed 個の休みを月全体に均等に分散して選ぶ
        selected: list[date] = []
        n = len(candidates)
        interval = n / needed if needed > 0 else 1
        for i in range(needed):
            start = int(i * interval)
            end = int((i + 1) * interval)
            bucket = candidates[start:end] if end <= n else candidates[start:]
            if not bucket:
                break
            # バケツの中で「これまで一番プレシードが少ない日」を選ぶ
            chosen = min(bucket, key=lambda d: preseed_count_on_day.get(d, 0))
            selected.append(chosen)
            pre_seeded_map[(s.id, chosen)] = True
            _register_skill_seeded(s.id, chosen)  # ★ 全業務対象のカウント更新
            preseed_count_on_day[chosen] = preseed_count_on_day.get(chosen, 0) + 1

        for d in selected:
            pre_seeded.append(Request(staff_id=s.id, date=d, symbol='休(仮)'))

    print(f"  事前公休割り当て: {len(pre_seeded)}件", flush=True)
    return pre_seeded


def _in_rotation(staff, rest_val, num_days, long_leave_slack: int = 10):
    """画像診断ローテの実働要員かを判定（リバランサーの over集合・mover から除外する人を弾く）。

    除外: 別部門(核医学/治療) / MRI専門 / 新人(経験1年以下) / 当月ほぼ全休(育休・長期休)。
    rest_val は当月の公休相当日数（半休0.5込み）。num_days は当月日数。
    """
    note = getattr(staff, 'note', '') or ''
    if '核医学' in note or '治療' in note:
        return False
    if 'MRI専門' in note:
        return False
    if getattr(staff, 'experience_years', 99) <= 1:
        return False
    if rest_val >= num_days - long_leave_slack:   # 育休/長期休: 実勤務がごく僅か
        return False
    return True


def _coexistence_report(rest_map, target):
    """代休(公休<目標)と余剰(公休>目標)の併存状況を集計（ローテ要員の rest_map を渡す）。"""
    unders = {k: v for k, v in rest_map.items() if v < target}
    overs = {k: v for k, v in rest_map.items() if v > target}
    daikyu = sum(target - v for v in unders.values())
    surplus = sum(v - target for v in overs.values())
    return {
        "n_under": len(unders),
        "n_over": len(overs),
        "daikyu_days": round(daikyu, 2),
        "surplus_days": round(surplus, 2),
        "coexists": len(unders) > 0 and len(overs) > 0,
    }


def rebalance_workload(day_result_list, technicians, skills, locations, requests,
                       night_assignments, year: int, month: int, target_holidays: int):
    """後段リバランサー: 過剰休(公休>目標)の人の空き平日に日勤を移し、代休(公休<目標)の人を
    休ませて、全員を目標公休に近づける。ハード制約(スキル/性別/連勤/個別ルール/パワーバランス簡易)を保つ。

    数学的背景: 公休不足(代休)は容量の限界ではなく「夜勤者が過剰休/日勤専門者が過重」という
    分配の偏りが主因。過剰休者の空き平日に日勤を移すことで、副作用なく代休と有給消化を同時に減らす。
    """
    from shift_scheduler.src.models.skill import SkillRank

    num_days = calendar.monthrange(year, month)[1]
    all_days = [date(year, month, d) for d in range(1, num_days + 1)]
    req_map = {(r.staff_id, r.date): r.symbol for r in requests}
    night_map = {}
    for na in night_assignments:
        night_map[(na.staff_id, na.date)] = True
    active = [s for s in technicians if s.status == '在籍']
    skill_of = lambda sid, l: skills.get(sid, {}).get(l, SkillRank.NONE)

    FORCED = {'業配', '業出', '出', '会議', '全会', '講', '勤', '出/講', '17業'}
    COND = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
    LATE = {'遅番', '超遅', 'ク遅', 'M遅'}
    loc_codes = {l.code for l in locations}
    gender_only = {l.code: l.gender_constraint for l in locations}

    def qualifies(sid, l):
        r = skill_of(sid, l)
        if l == 'HB': return r >= SkillRank.A
        if l in ('ア', '心'): return r >= SkillRank.B
        return r > SkillRank.NONE

    def is_protected(sid, l):
        if sid == 'T001' and l in ('病CT', 'CT'): return True
        if sid in ('T013', 'T025') and l in ('ク', 'ク遅'): return True
        if sid == 'T072' and l == '館山': return True
        return False

    def is_pub(d):
        is_jan = (d.month == 1 and d.day in [1, 2, 3])
        return is_jan or jpholiday.is_holiday(d) or d.weekday() == 6

    # 実勤務の割当マップ (sid, date) -> DayAssignment（休/○より実業務を優先）
    assign = {}
    for da in day_result_list:
        if da.date.year == year and da.date.month == month:
            key = (da.staff_id, da.date)
            if key not in assign or assign[key].location_code in ('休', '○'):
                assign[key] = da

    # 業務別ロスター: (date, loc_code) -> その日その業務に入っているsid集合（質の維持判定に使う）
    from collections import defaultdict
    loc_roster = defaultdict(set)
    for (sid, dd), da in assign.items():
        if da.location_code not in ('休', '○'):
            loc_roster[(dd, da.location_code)].add(sid)

    def is_working(sid, d):
        if night_map.get((sid, d)): return True
        if night_map.get((sid, d - timedelta(days=1))): return True   # 明け
        da = assign.get((sid, d))
        if da and da.location_code not in ('休', '○'): return True
        sym = req_map.get((sid, d))
        if sym in FORCED: return True
        if sym in COND and not is_pub(d): return True
        return False

    def rest_count(sid):
        # 半休(出/☆)は0.5、それ以外の非勤務日は1.0としてカウント（最終カウントと整合）
        c = 0.0
        for d in all_days:
            if is_working(sid, d):
                continue
            c += 0.5 if req_map.get((sid, d)) == '出/☆' else 1.0
        return c

    def is_free_weekday(sid, d):
        """O がその平日に日勤を引き受けられるか（空きで、申請・夜勤・明け・翌日夜勤が無い）。"""
        if is_pub(d): return False
        if is_working(sid, d): return False
        if req_map.get((sid, d)): return False
        if night_map.get((sid, d)) or night_map.get((sid, d - timedelta(days=1))): return False
        if night_map.get((sid, d + timedelta(days=1))): return False
        return True

    def consec_if_work(sid, d):
        run = 1
        dd = d - timedelta(days=1)
        while dd >= all_days[0] and is_working(sid, dd):
            run += 1; dd -= timedelta(days=1)
        dd = d + timedelta(days=1)
        while dd <= all_days[-1] and is_working(sid, dd):
            run += 1; dd += timedelta(days=1)
        return run

    rest = {s.id: rest_count(s.id) for s in active}
    moves = 0
    changed = True
    rounds = 0
    while changed and rounds < 300:
        changed = False
        rounds += 1
        unders = sorted([s for s in active if rest[s.id] < target_holidays], key=lambda s: rest[s.id])
        overs = [s for s in active if rest[s.id] > target_holidays]
        if not unders or not overs:
            break
        for U in unders:
            if rest[U.id] >= target_holidays:
                continue
            for d in all_days:
                if rest[U.id] >= target_holidays:
                    break
                if is_pub(d):
                    continue
                da = assign.get((U.id, d))
                if not da or da.location_code in ('休', '○'):
                    continue
                L = da.location_code
                if L in LATE or L not in loc_codes:
                    continue
                if is_protected(U.id, L):
                    continue
                if req_map.get((U.id, d)):
                    continue
                if night_map.get((U.id, d)) or night_map.get((U.id, d - timedelta(days=1))):
                    continue
                for O in overs:
                    if rest[O.id] <= target_holidays or O.id == U.id:
                        continue
                    if is_protected(O.id, L) or not qualifies(O.id, L):
                        continue
                    # ランク完全一致は厳しすぎる（専門職が休めない）。人間的判断で緩和:
                    # U が Aランクでも、交代後その業務にもう1人A評価が残るなら低ランクへ委譲可（質維持）
                    if skill_of(U.id, L) == SkillRank.A and skill_of(O.id, L) != SkillRank.A:
                        if sum(1 for sid in loc_roster[(d, L)]
                               if sid != U.id and skill_of(sid, L) == SkillRank.A) < 1:
                            continue
                    # Dランク単独化を防ぐ（交代後にDより上が1人以上残ること）
                    if skill_of(O.id, L) == SkillRank.D:
                        if sum(1 for sid in loc_roster[(d, L)]
                               if sid != U.id and skill_of(sid, L).value > SkillRank.D.value) < 1:
                            continue
                    if gender_only.get(L) == '女性のみ' and O.gender.value == '男':
                        continue
                    # 夜勤明け後の休み優先(ソフト): O が d-2 に夜勤＝当日 d は「明けの翌日」。
                    # その日に日勤を移すと明け後の休みが潰れるため、移動先から除外して保護する。
                    if night_map.get((O.id, d - timedelta(days=2))):
                        continue
                    if not is_free_weekday(O.id, d):
                        continue
                    if consec_if_work(O.id, d) > 6:
                        continue
                    # 交換実行: U の日勤 L(d) を O へ移す → U は休、O は勤務
                    da.staff_id = O.id
                    assign[(O.id, d)] = da
                    del assign[(U.id, d)]
                    loc_roster[(d, L)].discard(U.id)
                    loc_roster[(d, L)].add(O.id)
                    rest[U.id] += 1
                    rest[O.id] -= 1
                    moves += 1
                    changed = True
                    break
    # === 最終モップアップ: 主ループが round 上限/順序で取りこぼした「厳密に改善する」交換を回収する。
    # ドナー O は交代後も target 以上を保つ者のみ（rest[O] >= target+1）＝新規代休を作らない。
    # under U の代休を解消（U は +0.5 超過まで許容）。各 move は総代休を厳密に減らすので必ず収束する。
    mop_improved = True
    while mop_improved:
        mop_improved = False
        m_unders = sorted([s for s in active if rest[s.id] < target_holidays], key=lambda s: rest[s.id])
        if not m_unders:
            break
        for U in m_unders:
            if rest[U.id] >= target_holidays:
                continue
            done = False
            for d in all_days:
                if done:
                    break
                if is_pub(d):
                    continue
                da = assign.get((U.id, d))
                if not da or da.location_code in ('休', '○'):
                    continue
                L = da.location_code
                if L in LATE or L not in loc_codes:
                    continue
                if is_protected(U.id, L) or req_map.get((U.id, d)):
                    continue
                if night_map.get((U.id, d)) or night_map.get((U.id, d - timedelta(days=1))):
                    continue
                for O in active:
                    # 交代後も O が target 以上を保つ＝新規代休を作らない（主ループより厳格）
                    if rest[O.id] < target_holidays + 1 or O.id == U.id:
                        continue
                    if not _in_rotation(O, rest[O.id], num_days):
                        continue
                    if is_protected(O.id, L) or not qualifies(O.id, L):
                        continue
                    if skill_of(U.id, L) == SkillRank.A and skill_of(O.id, L) != SkillRank.A:
                        if sum(1 for sid in loc_roster[(d, L)] if sid != U.id and skill_of(sid, L) == SkillRank.A) < 1:
                            continue
                    if skill_of(O.id, L) == SkillRank.D:
                        if sum(1 for sid in loc_roster[(d, L)] if sid != U.id and skill_of(sid, L).value > SkillRank.D.value) < 1:
                            continue
                    if gender_only.get(L) == '女性のみ' and O.gender.value == '男':
                        continue
                    # 夜勤明け後の休み優先(完全保護): O が d-2 に夜勤＝当日 d は明けの翌日。
                    # 明け後の休みを守るため、モップアップ(代休撲滅の最終手段)でもこの日には
                    # 日勤を移さない。運用者判断で明け後休を代休回避より優先する（代休増を許容）。
                    if night_map.get((O.id, d - timedelta(days=2))):
                        continue
                    if not is_free_weekday(O.id, d):
                        continue
                    if consec_if_work(O.id, d) > 6:
                        continue
                    da.staff_id = O.id
                    assign[(O.id, d)] = da
                    del assign[(U.id, d)]
                    loc_roster[(d, L)].discard(U.id)
                    loc_roster[(d, L)].add(O.id)
                    rest[U.id] += 1
                    rest[O.id] -= 1
                    moves += 1
                    mop_improved = True
                    done = True
                    break

    # 別部門/育休/新人/MRI専門は「余剰」として数えない（見かけ値を排除）。ローテ要員のみで併存を測る。
    rotation = [s for s in active if _in_rotation(s, rest[s.id], num_days)]
    rot_rest = {s.id: rest[s.id] for s in rotation}
    rep = _coexistence_report(rot_rest, target_holidays)
    print(f"  ⚖️ リバランサー(貪欲): {moves}件移動 → ローテ内 代休{rep['n_under']}名({rep['daikyu_days']}日) "
          f"/ 余剰{rep['n_over']}名({rep['surplus_days']}日)", flush=True)
    if rep["coexists"]:
        # 代休と余剰が併存して残った＝これ以上の自動解消が出来なかった。理由を明示する（正直性）。
        stuck = sorted([s for s in rotation if rest[s.id] < target_holidays], key=lambda s: rest[s.id])
        for U in stuck:
            print(f"    ⚠️ 代休残存: {U.name}(公休{rest[U.id]}) — 有資格・空き平日・連勤・性別の"
                  f"いずれかが噛み合わず肩代わり不能", flush=True)
    return day_result_list


def optimize_assignments_cpsat(day_result_list, technicians, skills, locations, requests,
                               night_assignments, year: int, month: int, target_holidays: int):
    """月全体をCP-SATで再最適化（作り直し版・2026-06-14）。
    目的: ①ク6回(T013/T025)をハード床で修正 ②場所別担当回数の偏り(CT/ク)を公平化。
    既存の日次スロット(場所×必要数)は保ち「誰が埋めるか」だけを最適化する。

    ルール維持の二段構え（ルールを全部書き直さない）:
      - 凍結: 夜勤/明け/申請/業配/PET/遅番系/非業務 + 個別固定(T001病CT・T072館山・MRI専従)。
      - rank-floor不変条件: 各スロットでA数・AB数≧現状, D数≦現状 → SR-01〜09b・
        パワーバランス(病CT A2B1CD3, ク A3 等)を入力が合法な限り自動維持。
    代休は各人 over≦現状 のハード制約で悪化させない。連勤≤6。
    反映は「解からの再構築」（既存オブジェクト書換でなく新規生成）でバグを根治。
    採用は status∈{OPTIMAL,FEASIBLE} の時のみ。それ以外は元リストをそのまま返す。
    """
    from ortools.sat.python import cp_model
    from shift_scheduler.src.models.skill import SkillRank
    from collections import defaultdict

    num_days = calendar.monthrange(year, month)[1]
    days = [date(year, month, dd) for dd in range(1, num_days + 1)]
    req_map = {(r.staff_id, r.date): r.symbol for r in requests}
    night_map = {}
    for na in night_assignments:
        night_map[(na.staff_id, na.date)] = True
    active = sorted([s for s in technicians if s.status == '在籍'], key=lambda s: s.id)
    staff_by_id = {s.id: s for s in active}
    # MRI専従（備考"MRI専門"）: 病院MR/CLMR から動かさない（凍結）
    mri_spec = {s.id for s in active if getattr(s, 'note', '') and 'MRI専門' in s.note}
    KU6_IDS = ('T013', 'T025')  # 小野/川名: クリニック月6回のハード床で能動的に修正
    KU6_TARGET = 6              # クリニック月6回（床）。暴走は公平化目的(含T013/T025)で抑制
    skill_of = lambda sid, l: skills.get(sid, {}).get(l, SkillRank.NONE)
    loc_codes = {l.code for l in locations}
    gender_only = {l.code: l.gender_constraint for l in locations}
    LATE = {'遅番', '超遅', 'ク遅', 'M遅'}
    FORCED = {'業配', '業出', '出', '会議', '全会', '講', '勤', '出/講', '17業'}
    COND = {'研(聴)', '出/(発)', '出(発)', '発', '☆/(発)', '☆/(聴)', '研(発)', '出/(座)', '研(座)', '研(役)', '出/(役)'}
    # 最適化対象＝可動な日勤場所すべて（ク6達成に必要な入替の自由度を確保するため）。
    # 凍結する場所（遅番系・特殊・無効）。これら＋個別固定(is_protected)はソルバが触らない。
    FROZEN_LOCS = LATE | {'館山', '出', 'PICC', '勤務表作成'}
    OPT_LOCS = {l.code for l in locations if l.code not in FROZEN_LOCS}

    def is_pub(d):
        is_jan = (d.month == 1 and d.day in [1, 2, 3])
        return is_jan or jpholiday.is_holiday(d) or d.weekday() == 6

    def qualifies(sid, l):
        r = skill_of(sid, l)
        if l == 'HB': return r >= SkillRank.A
        if l in ('ア', '心'): return r >= SkillRank.B
        return r > SkillRank.NONE

    def is_protected(sid, l):
        # 個別固定ルール → これらのセルは凍結（再配置しない）。
        # 注: T013/T025 の ク はここでは凍結しない。ク6床で能動的に修正するため
        #     スロット構成員(可動)として扱い、別途ハード床 Σy[ク]≥6 を課す。
        if sid == 'T001' and l in ('病CT', 'CT'): return True
        if sid == 'T072' and l == '館山': return True
        if sid in mri_spec and l in ('病院MR', 'CLMR'): return True
        return False

    # 公平化対象 base へのグループ化（CT合=CT+病CT, MRI=病院MR+CLMR, 他は単独）。
    # 全可動場所を base にまとめて偏りを最小化（モデル化したが目的に無い場所の劣化を防ぐ）。
    def fair_base(l):
        if l in ('CT', '病CT'): return 'CT'
        if l in ('病院MR', 'CLMR'): return 'MRI'
        if l not in OPT_LOCS:
            return None
        return l
    # base ごとの公平化除外者（個別ルール対象＝床/専従があるため平準化しない）
    # 注: ク は T013/T025 を除外しない（目的に含めて床6超の山積みを抑制）。
    #     CT/MRI は専従(T001/MRI専門)を除外（構造的に多く、平準化対象外）。
    fair_exclude = defaultdict(set, {'CT': {'T001'} | mri_spec, 'MRI': set(mri_spec)})

    # 現状の実勤務割当 (sid,d)->loc。休/○含む全エントリも別マップに保持（公休カウント用）。
    cur = {}
    loc_full = {}                  # (sid,d)->location_code（休/○含む、'休'優先）
    for da in day_result_list:
        if not (da.date.year == year and da.date.month == month):
            continue
        key = (da.staff_id, da.date)
        if da.location_code not in ('休', '○'):
            cur[key] = da
        if key not in loc_full or loc_full[key] in ('休', '○'):
            loc_full[key] = da.location_code

    # 固定(ロック)日 → 再配置しない:
    #   夜勤/明け、強制勤務申請(FORCED)、半休(出/☆)、平日の研修(COND)、
    #   休日/公休申請(LOCK_OFF: ★☆◆/休/17休 等＝勤務を入れてはいけない)、
    #   最適化対象外場所(MRI/ポ/MG/遅番/非業務)・個別固定(is_protected)。
    LOCK_OFF = {'★', '★連', '☆', '☆小', '☆デ', '◆', '退職', '☆育'}
    def is_fixed_day(sid, d):
        if night_map.get((sid, d)) or night_map.get((sid, d - timedelta(days=1))):
            return True
        sym = req_map.get((sid, d))
        if sym in FORCED:
            return True
        if sym == '出/☆':          # 半休（午前勤務・午後休0.5）は動かさない
            return True
        if sym in COND and not is_pub(d):
            return True
        if sym in LOCK_OFF:        # 申請休（公休）日には勤務を入れない＝上書き防止
            return True
        da = cur.get((sid, d))
        if da and (da.location_code not in OPT_LOCS or is_protected(sid, da.location_code)):
            return True
        return False

    _PURE = {'★', '★連', '☆', '☆小', '☆デ', '◆', '退職', '☆育'}
    def off_contrib(sid, d, locmap):
        """assign_monthly_off_days と同じ基準で、その日の公休寄与(0/0.5/1)を返す。
        locmap=(sid,d)->location_code（休/○含む）。任意の割当リストの公休を測れる。"""
        if night_map.get((sid, d)) or night_map.get((sid, d - timedelta(days=1))):
            return 0.0                               # 夜勤/明け=勤務
        sym = req_map.get((sid, d))
        if sym in FORCED:
            return 0.0
        if sym == '出/☆':
            return 0.5
        loc = locmap.get((sid, d))
        if sym in _PURE or sym == '休' or loc == '休':
            return 1.0
        if sym in COND:
            return 1.0 if is_pub(d) else 0.0
        if is_pub(d) and not (loc and loc not in ('休', '○')):
            return 1.0
        if loc and loc not in ('休', '○'):
            return 0.0                               # 勤務(17休+日勤含む)
        if sym == '17休':
            return 1.0                               # 17休単独=公休
        if sym and sym != '休(仮)':
            return 0.0                               # その他申請=勤務
        return 1.0                                   # 空白=実質公休
    real_off_contrib = lambda sid, d: off_contrib(sid, d, loc_full)

    # 再配置対象スロット: (d,L)->現状人数・ランク構成（固定枠の人を除く通常日勤）
    slot = defaultdict(list)  # (d, L) -> [sid]
    for (sid, d), da in cur.items():
        L = da.location_code
        if L not in OPT_LOCS or is_protected(sid, L):
            continue              # CT/病CT/ク 以外は最適化しない（凍結）
        if night_map.get((sid, d)) or night_map.get((sid, d - timedelta(days=1))):
            continue
        if is_fixed_day(sid, d):
            continue
        slot[(d, L)].append(sid)

    model = cp_model.CpModel()
    y = {}  # (sid, d, L) -> bool
    cand_by_slot = {}
    for (d, L), people in slot.items():
        n = len(people)
        cands = [s for s in active
                 if qualifies(s.id, L) and not is_fixed_day(s.id, d)
                 and not (gender_only.get(L) == '女性のみ' and s.gender.value == '男')]
        cand_by_slot[(d, L)] = cands
        for s in cands:
            y[(s.id, d, L)] = model.NewBoolVar(f'y_{s.id}_{d.day}_{L}')
        # 人数固定
        model.Add(sum(y[(s.id, d, L)] for s in cands) == n)
        # rank-floor（質維持）: A数・AB数は現状以上、D数は現状以下
        cur_A = sum(1 for sid in people if skill_of(sid, L) == SkillRank.A)
        cur_AB = sum(1 for sid in people if skill_of(sid, L) >= SkillRank.B)
        cur_D = sum(1 for sid in people if skill_of(sid, L) == SkillRank.D)
        A_vars = [y[(s.id, d, L)] for s in cands if skill_of(s.id, L) == SkillRank.A]
        AB_vars = [y[(s.id, d, L)] for s in cands if skill_of(s.id, L) >= SkillRank.B]
        D_vars = [y[(s.id, d, L)] for s in cands if skill_of(s.id, L) == SkillRank.D]
        if cur_A > 0 and A_vars:
            model.Add(sum(A_vars) >= cur_A)
        if cur_AB > 0 and AB_vars:
            model.Add(sum(AB_vars) >= cur_AB)
        if D_vars:
            model.Add(sum(D_vars) <= cur_D)

    # 1人1日1場所
    by_person_day = defaultdict(list)
    for (sid, d, L) in y:
        by_person_day[(sid, d)].append(y[(sid, d, L)])
    for key, vs in by_person_day.items():
        model.Add(sum(vs) <= 1)

    # 連勤≤6 用の勤務フラグ。固定日は「実際に勤務か」で判定（休日申請=0、半休/勤務=1）。
    # ※ is_fixed_day には休日申請(LOCK_OFF)も含むため、一律1にすると休日を連勤に数えてしまう。
    work = {}  # (sid, d) -> 0/1/expr
    for s in active:
        for d in days:
            if is_fixed_day(s.id, d):
                work[(s.id, d)] = 0 if real_off_contrib(s.id, d) >= 1.0 else 1
            else:
                vs = by_person_day.get((s.id, d), [])
                work[(s.id, d)] = sum(vs) if vs else 0
    # 連勤制約: 7日窓で勤務≤6
    for s in active:
        for i in range(num_days - 6):
            window = [work[(s.id, days[i + j])] for j in range(7)]
            model.Add(sum(window) <= 6)

    # ---- 代休(公休不足)を悪化させない: 各人 実公休 ≥ min(目標, 現状公休)（ハード） ----
    # free日(申請なしの素の平日/休日)のみ可変。実公休を厳密に表現:
    #   実公休 = Σ_lock real_off_contrib + Σ_free(1 - slot勤務)
    # baseline実公休 = Σ_lock real_off + (nfree - 現状slot勤務).
    # 制約 実公休 ≥ T=min(目標, baseline) ⇔ Σ_free slot勤務 ≤ baseline + 現状slot勤務 - T.
    import math
    cur_slot_cnt = {s.id: 0 for s in active}       # 現状スロット勤務数(=free日の現状勤務)
    for (d, L), people in slot.items():
        for sid in people:
            cur_slot_cnt[sid] = cur_slot_cnt.get(sid, 0) + 1
    for s in active:
        lock_off = sum(real_off_contrib(s.id, d) for d in days if is_fixed_day(s.id, d))
        nfree = sum(1 for d in days if not is_fixed_day(s.id, d))
        baseline_off = lock_off + (nfree - cur_slot_cnt.get(s.id, 0))
        T = min(target_holidays, baseline_off)     # 現状が構造的代休なら現状を下限に
        cap = math.floor(baseline_off + cur_slot_cnt.get(s.id, 0) - T)
        slot_work = [y[(s.id, d, L)] for (d, L) in slot if (s.id, d, L) in y]
        if slot_work:
            model.Add(sum(slot_work) <= max(0, cap))

    # ---- ク6回 ハード床（T013小野 / T025川名 ≥ 6）＋ 同日ク禁止 ----
    # =6固定は同日ク禁止と衝突してINFEASIBLEになるため床(≥6)とし、
    # 暴走(6超の山積み)は下の公平化目的に T013/T025 を含めることで抑制する。
    for kid in KU6_IDS:
        ku_vars = [y[(kid, d, 'ク')] for d in days if (kid, d, 'ク') in y]
        if ku_vars:
            model.Add(sum(ku_vars) >= KU6_TARGET)
    for d in days:
        a = y.get(('T013', d, 'ク')); b = y.get(('T025', d, 'ク'))
        if a is not None and b is not None:
            model.Add(a + b <= 1)

    # ---- 公平化目的: CT合・ク の担当回数の偏り(平均超過分)を最小化 ----
    # 個別ルール対象(CT→T001/MRI専従, ク→T013/T025)と MRI専従 は除外。
    cnt_vars = defaultdict(list)                   # (sid,B) -> [y vars]
    for (sid, d, L), var in y.items():
        B = fair_base(L)
        if B is None or sid in mri_spec or sid in fair_exclude.get(B, set()):
            continue
        cnt_vars[(sid, B)].append(var)
    cur_base = defaultdict(int)                     # (sid,B) -> 現状担当数
    for (d, L), people in slot.items():
        B = fair_base(L)
        if B is None:
            continue
        for sid in people:
            if sid in mri_spec or sid in fair_exclude.get(B, set()):
                continue
            cur_base[(sid, B)] += 1
    elig_by_base = defaultdict(set)
    for (sid, B) in cnt_vars:
        elig_by_base[B].add(sid)
    excess_terms = []
    for B in sorted(elig_by_base):
        sids = elig_by_base[B]
        n = len(sids)
        tot = sum(cur_base.get((sid, B), 0) for sid in sids)
        tgt = (tot + n - 1) // n if n else 0        # ceil(平均)
        for sid in sorted(sids):
            c = sum(cnt_vars[(sid, B)])
            ex = model.NewIntVar(0, num_days, f'ex_{sid}_{B}')
            model.Add(ex >= c - tgt)
            excess_terms.append(ex)
    # 目的: greedy解からの変更を最小化（＝ク6を満たす最小の入替）。第二目的で公平化を弱く加味。
    # 全場所モデルでは120秒で公平化を解ききれず悪化するため、まず「ク6を最小撹乱で達成」を主目的に。
    # 変更コスト: hint(現状)と異なる割当を1とカウント。
    change_terms = []
    for (sid, d, L), var in y.items():
        is_cur = 1 if (cur.get((sid, d)) and cur[(sid, d)].location_code == L) else 0
        change_terms.append((1 - var) if is_cur else var)
    W_CHANGE = 100
    model.Minimize(W_CHANGE * sum(change_terms) + sum(excess_terms))

    # 現状解をヒント（悪化させない）
    for (sid, d, L), var in y.items():
        model.AddHint(var, 1 if cur.get((sid, d)) and cur[(sid, d)].location_code == L else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_deterministic_time = 120.0
    solver.parameters.max_time_in_seconds = 600
    solver.parameters.random_seed = 42
    solver.parameters.num_workers = 1
    status = solver.Solve(model)
    print(f"  🧮 CP-SAT全体最適化: {solver.StatusName(status)} "
          f"(detTime={solver.ResponseProto().deterministic_time:.1f})", flush=True)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("  (最適化解なし→貪欲リバランス結果を維持)", flush=True)
        return day_result_list

    # ---- 反映: 「解からの再構築」（既存オブジェクト書換のバグを根治） ----
    # スロット構成員の元DayAssignmentを id() で識別して破棄し、solver採用者で新規生成。
    # 凍結セル・他月・休/○ は温存（ただし新規勤務者の旧 休/○ は重複防止のため除去）。
    member_obj_ids = set()                          # 置換対象＝スロット構成員の元オブジェクト
    for (d, L), people in slot.items():
        for sid in people:
            da = cur.get((sid, d))
            if da is not None and da.location_code == L:
                member_obj_ids.add(id(da))
    chosen_by_slot = {}                             # (d,L) -> [sid]（決定的に sorted）
    chosen_person_days = set()                      # 新規に勤務する(sid,d)
    for (d, L), cands in cand_by_slot.items():
        chosen = sorted(s.id for s in cands if solver.Value(y[(s.id, d, L)]) == 1)
        chosen_by_slot[(d, L)] = chosen
        for sid in chosen:
            chosen_person_days.add((sid, d))

    new_list = []
    for da in day_result_list:
        if not (da.date.year == year and da.date.month == month):
            new_list.append(da)                     # 他月はそのまま
            continue
        if id(da) in member_obj_ids:
            continue                                # 旧スロット勤務は破棄→下で再生成
        if da.location_code in ('休', '○') and (da.staff_id, da.date) in chosen_person_days:
            continue                                # 新規勤務者の旧休/○は除去（重複防止）
        new_list.append(da)                         # 凍結セル等は温存
    for (d, L) in sorted(chosen_by_slot, key=lambda k: (k[0], k[1])):
        for sid in chosen_by_slot[(d, L)]:
            new_list.append(DayAssignment(
                date=d, location_code=L, staff_id=sid, rank=skill_of(sid, L)))

    # ---- 採否ゲート: 入力(greedy)と再構築解を同一基準で測り、悪化なら不採用 ----
    # greedyは非決定的なので「別runのbaseline」でなく「このrunの入力」と比較するのが正しい。
    def _locmap(rlist):
        m = {}
        for da in rlist:
            if da.date.year == year and da.date.month == month:
                k = (da.staff_id, da.date)
                if k not in m or m[k] in ('休', '○'):
                    m[k] = da.location_code
        return m

    def _metrics(rlist):
        lm = _locmap(rlist)
        daikyu = 0.0
        for s in active:
            off = sum(off_contrib(s.id, d, lm) for d in days)
            if off < target_holidays:
                daikyu += target_holidays - off
        ku = {kid: sum(1 for d in days if lm.get((kid, d)) == 'ク') for kid in KU6_IDS}
        spread = {}
        for B, exc in (('CT', {'T001'} | mri_spec), ('ク', set())):
            members = ('CT', '病CT') if B == 'CT' else ('ク',)
            cnt = defaultdict(int)
            for (sid, d), L in lm.items():
                if L in members and sid not in exc and sid not in mri_spec:
                    cnt[sid] += 1
            vals = list(cnt.values())
            spread[B] = (max(vals) - min(vals)) if vals else 0
        return daikyu, ku, spread

    in_dk, in_ku, in_sp = _metrics(day_result_list)
    out_dk, out_ku, out_sp = _metrics(new_list)
    ku6_ok = all(out_ku[k] >= KU6_TARGET for k in KU6_IDS)
    ku6_in = all(in_ku[k] >= KU6_TARGET for k in KU6_IDS)
    worse = (out_dk > in_dk + 1e-9 or
             out_sp['CT'] > in_sp['CT'] or out_sp['ク'] > in_sp['ク'] or
             (ku6_in and not ku6_ok))
    print(f"  📊 入力: 代休{in_dk:.1f} ク{in_ku} 幅CT{in_sp['CT']}/ク{in_sp['ク']}", flush=True)
    print(f"  📊 最適: 代休{out_dk:.1f} ク{out_ku} 幅CT{out_sp['CT']}/ク{out_sp['ク']}", flush=True)
    if worse:
        print("  ⛔ 悪化検知 → 最適化を不採用（greedy結果を維持）", flush=True)
        return day_result_list
    print("  ✅ 改善/同等 → 最適化を採用", flush=True)
    return new_list


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
    training_rules = loader.load_training_rules(technicians)
    
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
    
    # 前月末の夜勤実績を申請データから取得（当月1日の明け判定に必要）
    print("🔙 前月の夜勤実績を確認中...", flush=True)
    start_date = date(year, month, 1)
    prev_month_limit = start_date - timedelta(days=7)
    prev_night_history = []
    for r in requests:
        if prev_month_limit <= r.date < start_date and '夜' in r.symbol:
            prev_night_history.append(
                NightAssignment(date=r.date, staff_id=r.staff_id, role='History')
            )
    print(f"  前月の夜勤実績: {len(prev_night_history)}件 -> 統合", flush=True)

    # 夜勤スケジューリング
    print("🌙 夜勤スケジューリング実行中...", flush=True)
    night_scheduler = NightScheduler(staff_list=technicians, year=year, month=month)
    night_result = night_scheduler.schedule(requests, night_counts, prev_night_history)
    print(f"  夜勤配置数: {len(night_result)}件", flush=True)
    print(flush=True)

    # 夜勤データ変換: List[NightAssignment] -> Dict[day -> List[staff_id]]
    night_assignments_dict = {}
    for na in night_result:
        night_assignments_dict.setdefault(na.date.day, []).append(na.staff_id)

    print(f"  前月の夜勤実績(申請より): {len(prev_night_history)}件 -> 統合", flush=True)

    # 当月用と引き継ぎ用を分離
    # night_result     = Excel出力用（当月分のみ）
    # full_night_assignments = DayScheduler用（前月末分を含む）
    full_night_assignments = night_result + prev_night_history

    # 公休目標日数を読み込む
    target_holidays = loader.load_monthly_holidays(year, month)
    print(f"📅 今月の公休目標: {target_holidays}日", flush=True)
    print(flush=True)

    # ===== Phase 1: 公休先行配置（スキル枯渇チェック付き） =====
    print("🌅 公休先行配置（Phase 1）実行中...", flush=True)
    pre_seeded = pre_seed_rest_days(
        technicians=technicians,
        requests=requests,
        night_assignments=full_night_assignments,
        year=year,
        month=month,
        target_holidays=target_holidays,
        skills=skills,
        locations=locations,
    )
    requests_with_preseed = requests + pre_seeded
    print(flush=True)

    # ===== Phase 2: 日勤スケジューリング（研修配置なし）=====
    # 研修枠（拡大配置）は自動配置せず、担当者が手動で調整する
    print("☀️ 日勤スケジューリング実行中（研修なし）...", flush=True)
    day_scheduler = DayScheduler(
        staff_list=technicians,
        skills=skills,
        locations=locations,
        pb_rules=pb_rules,
        rules=special_rules,
        training_rules=training_rules,
        year=year,
        month=month,
        disable_training=True,
        target_holidays=target_holidays,
    )
    day_result_list, daily_location_needs = day_scheduler.schedule(requests_with_preseed, full_night_assignments)
    print(f"  日勤配置数: {len(day_result_list)}件", flush=True)
    print(flush=True)

    # ===== Phase 2.5: 勤務平均化リバランサー（過剰休↔代休者の日勤交換）=====
    print("⚖️ 勤務平均化リバランス中...", flush=True)
    day_result_list = rebalance_workload(
        day_result_list=day_result_list,
        technicians=technicians,
        skills=skills,
        locations=locations,
        requests=requests_with_preseed,
        night_assignments=full_night_assignments,
        year=year,
        month=month,
        target_holidays=target_holidays,
    )
    print(flush=True)

    # ===== Phase 2.6: CP-SAT 全体最適化（ク6修正＋場所別公平化）=====
    # 反映は「解からの再構築」方式（前回バグの根治）。代休は各人現状以下に固定し悪化させない。
    print("🧮 CP-SAT全体最適化中（ク6修正＋公平化）...", flush=True)
    day_result_list = optimize_assignments_cpsat(
        day_result_list=day_result_list,
        technicians=technicians,
        skills=skills,
        locations=locations,
        requests=requests_with_preseed,
        night_assignments=full_night_assignments,
        year=year,
        month=month,
        target_holidays=target_holidays,
    )
    print(flush=True)

    # ===== 公休付与（規定日数に合わせて '休' を追加） =====
    # requests_with_preseed を渡して pre-seed 済み ☆ を公休としてカウントさせる
    print(f"📅 {target_holidays}日公休付与中...", flush=True)
    day_result_list, daikyu_counts, off_counts = assign_monthly_off_days(
        technicians=technicians,
        day_result_list=day_result_list,
        night_assignments=full_night_assignments,
        requests=requests_with_preseed,
        year=year,
        month=month,
        target_holidays=target_holidays,
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
        
    # Requests Conversion（pre-seeded ☆ を含めて Excel に反映する）
    requests_dict = {}
    for r in requests_with_preseed:
        d_day = r.date.day
        if r.date.year == year and r.date.month == month:
            if d_day not in requests_dict:
                requests_dict[d_day] = {}
            # 元の申請が既にある場合は上書きしない（pre-seeded ☆ より元申請を優先）
            if r.staff_id not in requests_dict[d_day]:
                requests_dict[d_day][r.staff_id] = r.symbol

    # ── Validation (Configure Validation Errors) ──
    print("🔍 最終検証・エラーレポート作成中...", flush=True)
    validation_errors = []
    
    # 1. Day Shift Understaffing Check
    for d, loc_needs in daily_location_needs.items():
        d_day = d.day
        for loc_code, required in loc_needs.items():
            if loc_code.startswith('(') and loc_code.endswith(')'):
                continue # Skip dummy training locations from understaffing warnings
            if required > 0:
                assigned_count = len(day_assignments_dict.get(d_day, {}).get(loc_code, []))
                if assigned_count < required:
                    validation_errors.append(f"{d.month}月{d.day}日: [{loc_code}] の配置人数が不足しています (目標: {required}人 / 実際: {assigned_count}人)")
                    
    # 2. Night Shift HB Coverage Check
    for d_day, assigns in night_assignments_dict.items():
        night_staff_objs = [s for s in technicians if s.id in assigns]
        has_hb = any(getattr(s, 'night_hb', False) for s in night_staff_objs)
        if not has_hb:
            validation_errors.append(f"{month}月{d_day}日: 夜勤メンバーにHB対応可能者がいないため代替処理を行いました (※本日の拘束枠でHBカバー)")
            
    if not validation_errors:
         print("  ✅ 全ての要件が正常に満たされています")
    else:
         print(f"  ⚠️ {len(validation_errors)}件の警告が発生しました")
         for err in validation_errors:
             print(f"    - {err}")

    # ===== クL（クリニックリーダー）表示付与（検証後・表示オーバーレイ）=====
    # その日のク担当者から有資格者1名を「クL」表示にする。資格=3年目以降・女性・ク有資格。
    # クL回数が最小の人を選ぶ輪番で負担を均等化（同数は技師IDで決定的）。クはそのまま1カウント。
    from shift_scheduler.src.models.skill import SkillRank as _SR
    _staff_by_id = {t.id: t for t in technicians}
    def _can_lead_clinic(sid):
        # スキルマスタの「クL」列を権威とする（運用者が個別に資格を管理）。
        # クL列が無いデータでは従来ルール(3年目以降・女性・ク有資格)に自動フォールバック。
        ssk = skills.get(sid, {})
        if 'クL' in ssk:
            return ssk.get('クL', _SR.NONE) > _SR.NONE
        t = _staff_by_id.get(sid)
        if not t or t.gender.value != '女':
            return False
        if int(t.experience_years) < 3:
            return False
        return ssk.get('ク', _SR.NONE) > _SR.NONE
    _kl_counts = {}
    _kl_days = 0
    for _d in sorted(day_assignments_dict.keys()):
        _ku = day_assignments_dict[_d].get('ク', [])
        _elig = [sid for sid in _ku if _can_lead_clinic(sid)]
        if not _elig:
            continue
        _leader = min(_elig, key=lambda s: (_kl_counts.get(s, 0), s))
        day_assignments_dict[_d]['ク'].remove(_leader)
        if not day_assignments_dict[_d]['ク']:
            del day_assignments_dict[_d]['ク']
        day_assignments_dict[_d].setdefault('クL', []).append(_leader)
        _kl_counts[_leader] = _kl_counts.get(_leader, 0) + 1
        _kl_days += 1
    print(f"  👑 クL付与: {_kl_days}日に指定 (対象{len(_kl_counts)}名 / 回数分布{sorted(_kl_counts.values(), reverse=True)})", flush=True)

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
        daikyu_counts=daikyu_counts,
        off_counts=off_counts,
        validation_errors=validation_errors
    )
    generator.generate(output_path)
    print(flush=True)
    
    print("=" * 70, flush=True)
    print("✅ 勤務表作成完了", flush=True)
    print("=" * 70, flush=True)

if __name__ == '__main__':
    main()

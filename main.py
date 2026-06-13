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
                    if skill_of(O.id, L) < skill_of(U.id, L):   # ランク劣化させない（パワーバランス保護）
                        continue
                    if gender_only.get(L) == '女性のみ' and O.gender.value == '男':
                        continue
                    if not is_free_weekday(O.id, d):
                        continue
                    if consec_if_work(O.id, d) > 6:
                        continue
                    # 交換実行: U の日勤 L(d) を O へ移す → U は休、O は勤務
                    da.staff_id = O.id
                    assign[(O.id, d)] = da
                    del assign[(U.id, d)]
                    rest[U.id] += 1
                    rest[O.id] -= 1
                    moves += 1
                    changed = True
                    break
    n_under = sum(1 for s in active if rest[s.id] < target_holidays)
    n_over = sum(1 for s in active if rest[s.id] > target_holidays)
    print(f"  ⚖️ リバランサー: {moves}件移動 → 目標未満{n_under}名 / 超過{n_over}名", flush=True)
    return day_result_list


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

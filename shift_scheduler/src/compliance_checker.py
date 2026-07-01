"""Solver-free COMPLIANCE checker (the "P3" skill/power-balance layer that
stats_engine deliberately left out).

Why this exists: the scheduler builds its CP-SAT model so it can never be
INFEASIBLE — most spec "hard" rules (required headcount, rank floors, special
weekday rules, 館山 …) are actually very-large-weight SOFT penalties. The only
post-solve check in run_schedule is headcount, yet the Excel report claims
"すべての配置・スキル要件が正常に満たされています". So "no error" does NOT mean
"rules satisfied". This module re-verifies the FINAL schedule against the real
rules and returns an honest, structured list of violations. It changes nothing
about scheduling and touches no files — it only inspects the produced schedule.

Reuses stats_engine for the parts it already computes (headcount coverage,
6連勤, 公休/代休). Adds: gender (DH-06), 夜勤明け day-work (DH-05), single
placement (DH-01), night modality distinct-coverage (NH-06), power-balance
rank floors / CD cap / D-solo (PB-01..05), and the safety-critical special
weekday rank rules (SR ア火A×2, 精水金A限定, HB第1金A×2 / 第4木A×3).
"""
from __future__ import annotations
import calendar
from datetime import date
from itertools import permutations

from .models.skill import SkillRank
from . import stats_engine


def _rank(skills, sid, loc_code) -> SkillRank:
    return skills.get(sid, {}).get(loc_code, SkillRank.NONE)


def _base_loc(loc_code: str) -> str:
    """Fold display/derived codes to their power-balance base for counting.
    クL/ク遅→ク, M遅→CLMR; strip training parens (ア)→ア."""
    if loc_code in ('クL', 'ク遅'):
        return 'ク'
    if loc_code == 'M遅':
        return 'CLMR'
    if loc_code.startswith('(') and loc_code.endswith(')'):
        return loc_code[1:-1]
    return loc_code


def _assigned_ids(day_assignments, dnum, base_code):
    """All staff whose (possibly derived) placement folds to base_code on dnum."""
    out = []
    for loc, ids in day_assignments.get(dnum, {}).items():
        if _base_loc(loc) == base_code:
            out.extend(ids)
    return out


def _week_of_month(dnum: int) -> int:
    return (dnum - 1) // 7 + 1


def check_compliance(*, year, month, technicians, skills, locations, pb_rules,
                     day_assignments, night_assignments, requests,
                     daily_location_needs=None, target_holidays=9,
                     staff_scope=None):
    """Return a list of violation dicts sorted by severity.
    Each: {severity, code, category, date, location, detail}.

    All inputs are the SAME objects run_schedule already holds:
      skills: {sid: {loc_code: SkillRank}}   locations: [Location]
      pb_rules: [PowerBalance]   day_assignments: {day:{loc:[sid]}}
      night_assignments: {day:[sid]}   requests: {day:{sid:symbol}}
    """
    num_days = calendar.monthrange(year, month)[1]
    by_id = {t.id: t for t in technicians}
    loc_by_code = {l.code: l for l in locations}
    pb_by_code = {r.location_code: r for r in pb_rules}
    active_ids = {t.id for t in technicians
                  if getattr(t, 'status', '在籍') == '在籍'
                  and (staff_scope is None or t.id in staff_scope)}
    V = []

    def nm(sid):
        t = by_id.get(sid)
        return getattr(t, 'name', sid) if t else sid

    def add(sev, code, category, dnum, location, detail):
        V.append({
            'severity': sev, 'code': code, 'category': category,
            'date': date(year, month, dnum).isoformat() if dnum else None,
            'location': location, 'detail': detail,
        })

    # ---- reuse stats_engine for headcount coverage + 6連勤 (already correct) ----
    st = stats_engine.recompute_stats(
        day_assignments, night_assignments, requests, technicians,
        year, month, target_holidays,
        daily_location_needs=daily_location_needs, staff_scope=staff_scope)
    for c in st['coverage']:
        add('high', 'DH-03', '必要人数不足',
            int(c['date'].split('-')[2]), c['location'],
            f"必要{c['required']}人に対し{c['assigned']}人 (不足{c['short']})")
    for c in st['consecutive']:
        add('critical', 'DH-09', '6連勤超過',
            int(c['start'].split('-')[2]), None,
            f"{nm(c['staff_id'])}: {c['start']}から{c['len']}連勤")

    # ---- per-day placement-level checks ----
    for dnum in range(1, num_days + 1):
        d = date(year, month, dnum)
        weekday = d.weekday()          # Mon=0
        wom = _week_of_month(dnum)
        day_map = day_assignments.get(dnum, {})

        # DH-01 single placement: staff in >1 real (non 休/○) location
        placed_count = {}
        for loc, ids in day_map.items():
            if loc in ('休', '○'):
                continue
            for sid in ids:
                placed_count[sid] = placed_count.get(sid, 0) + 1
        for sid, n in placed_count.items():
            if n > 1:
                add('high', 'DH-01', '二重配置', dnum, None,
                    f"{nm(sid)}: 同日{n}箇所に配置")

        # DH-05 夜勤明け: worked a real location the day after a night
        for sid in night_assignments.get(dnum - 1, []):
            locs = [l for l, ids in day_map.items()
                    if sid in ids and l not in ('休', '○')]
            if locs:
                add('critical', 'DH-05', '夜勤明け日勤', dnum, ','.join(locs),
                    f"{nm(sid)}: 前日夜勤なのに日勤配置")

        # DH-06 gender: male in a female-only location
        for loc, ids in day_map.items():
            L = loc_by_code.get(_base_loc(loc)) or loc_by_code.get(loc)
            if not L or getattr(L, 'gender_constraint', None) not in ('female', '女性のみ'):
                continue
            for sid in ids:
                t = by_id.get(sid)
                if t and getattr(t.gender, 'value', t.gender) == '男':
                    add('high', 'DH-06', '性別制約違反', dnum, loc,
                        f"{t.name}(男性)が女性限定枠に配置")

        # PB-01/02/03 power-balance floors on active locations
        for base_code, rule in pb_by_code.items():
            L = loc_by_code.get(base_code)
            if not L or not getattr(L, 'is_active', True):
                continue
            req = L.get_required_count(weekday) if hasattr(L, 'get_required_count') else 0
            ids = _assigned_ids(day_assignments, dnum, base_code)
            if not ids:
                continue
            # PB-01 min rank floor
            if rule.min_rank is not None and rule.min_count:
                have = sum(1 for sid in ids if _rank(skills, sid, base_code) >= rule.min_rank)
                need = min(rule.min_count, req or rule.min_count)
                if have < need:
                    add('medium', 'PB-01', 'ランク下限割れ', dnum, base_code,
                        f"{rule.min_rank.name}以上{need}名必要だが{have}名")
            # PB-02 CD cap
            if getattr(rule, 'cd_cap', None) is not None:
                cd = sum(1 for sid in ids
                         if _rank(skills, sid, base_code) in (SkillRank.C, SkillRank.D))
                if cd > rule.cd_cap:
                    add('medium', 'PB-02', 'CD上限超過', dnum, base_code,
                        f"C/D合計{cd}名 (上限{rule.cd_cap})")
            # PB-03 D solo ban (>=2 assigned, all D)
            if getattr(rule, 'd_solo_ban', False) and len(ids) >= 2:
                non_d = sum(1 for sid in ids
                            if _rank(skills, sid, base_code).value > SkillRank.D.value)
                if non_d == 0:
                    add('medium', 'PB-03', 'D単独配置', dnum, base_code,
                        f"配置{len(ids)}名が全員Dランク")

        # Special weekday rank rules (the safety-critical hard gates)
        def a_count(code):
            return sum(1 for sid in _assigned_ids(day_assignments, dnum, code)
                       if _rank(skills, sid, code) == SkillRank.A)
        # SR-01 ア 火曜 A×2
        if weekday == 1 and _assigned_ids(day_assignments, dnum, 'ア'):
            if a_count('ア') < 2:
                add('medium', 'SR-01', 'ア火曜A×2未達', dnum, 'ア',
                    f"火曜はAランク2名必要だが{a_count('ア')}名")
        # SR-03 HB 第1金曜 A×2 / SR-04 HB 第4木曜 A×3
        if weekday == 4 and wom == 1 and _assigned_ids(day_assignments, dnum, 'HB'):
            if a_count('HB') < 2:
                add('medium', 'SR-03', 'HB第1金A×2未達', dnum, 'HB',
                    f"第1金曜はAランク2名必要だが{a_count('HB')}名")
        if weekday == 3 and wom == 4 and _assigned_ids(day_assignments, dnum, 'HB'):
            if a_count('HB') < 3:
                add('medium', 'SR-04', 'HB第4木A×3未達', dnum, 'HB',
                    f"第4木曜はAランク3名必要だが{a_count('HB')}名")
        # SR-06 精 水金 A限定
        if weekday in (2, 4):
            sei = _assigned_ids(day_assignments, dnum, '精')
            non_a = [sid for sid in sei if _rank(skills, sid, '精') != SkillRank.A]
            if non_a:
                add('medium', 'SR-06', '精水金A限定違反', dnum, '精',
                    f"水金は精はAランクのみ。非A配置: {','.join(nm(s) for s in non_a)}")

    # ---- NH-06 night modality coverage ----
    # THE RULE (spec §4.5 + scheduler hard constraint): each of MR/アンギオ/心カテ has
    # >=1 capable person among the night staff. Spec explicitly allows ONE person to
    # cover multiple roles, so a real violation is only a modality with ZERO coverer.
    roles = ['night_mr', 'night_angio', 'night_cath']
    role_jp = {'night_mr': 'MR', 'night_angio': 'アンギオ', 'night_cath': '心カテ'}
    for dnum, ids in night_assignments.items():
        if dnum < 1 or dnum > num_days:
            continue
        people = [by_id.get(s) for s in ids]
        cover = {r: any(getattr(p, r, False) for p in people if p) for r in roles}
        for r in roles:
            if not cover[r]:
                add('high', 'NH-06', '夜勤モダリティ無資格', dnum, None,
                    f"{role_jp[r]}対応可能者が夜勤{len(ids)}名にゼロ (夜勤: {','.join(nm(s) for s in ids)})")
        # Beyond-spec resilience: can the 3 roles be filled by DISTINCT people (i.e. a
        # simultaneous different-modality emergency)? Spec permits doubling up, so INFO.
        if all(cover.values()) and len(ids) >= 3:
            distinct_ok = any(
                all(getattr(by_id.get(c[i]), roles[i], False) for i in range(3))
                for c in permutations(ids, 3))
            if not distinct_ok:
                add('info', 'NH-06b', '夜勤モダリティ同時対応注意', dnum, None,
                    f"3名でMR/アンギオ/心カテを別々に同時カバー不可(1名が兼務)。仕様上は可 "
                    f"(夜勤: {','.join(nm(s) for s in ids)})")

    # ---- 公休 upper-bound surplus report (informational; user concern ①) ----
    surplus = [(sid, off) for sid, off in st['off_counts'].items()
               if sid in active_ids and off > target_holidays]
    if surplus:
        add('info', 'OFF-SURPLUS', '公休超過(過剰休)', None, None,
            f"目標{target_holidays}日超の職員{len(surplus)}名 "
            f"(最大{max(o for _, o in surplus)}日): "
            + ', '.join(f"{nm(s)}={o}" for s, o in sorted(surplus, key=lambda x: -x[1])[:8]))

    sev_order = {'critical': 0, 'high': 1, 'medium': 2, 'info': 3, 'low': 4}
    V.sort(key=lambda v: (sev_order.get(v['severity'], 9), v['code'], v['date'] or ''))
    return V


def format_report(violations, *, target_holidays=9) -> str:
    """Human-readable console/report text. Honest about what was checked."""
    if not violations:
        return ("✅ 実質コンプライアンス検査: 検査した全ルール(必要人数/性別/夜勤明け/"
                "二重配置/6連勤/パワーバランス/特殊曜日/夜勤モダリティ)に違反なし。")
    real = [v for v in violations if v['severity'] != 'info']
    lines = [f"⚠️ 実質コンプライアンス検査: {len(real)}件の違反 + "
             f"{len(violations) - len(real)}件の情報"]
    for v in violations:
        tag = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'info': 'ℹ️'}.get(v['severity'], '・')
        loc = f"[{v['location']}]" if v['location'] else ''
        dt = f"{v['date']} " if v['date'] else ''
        lines.append(f"  {tag} {v['code']} {dt}{loc} {v['detail']}")
    return '\n'.join(lines)

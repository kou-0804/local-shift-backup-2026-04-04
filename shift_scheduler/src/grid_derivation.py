"""Pure cell-text + fill derivation, lifted verbatim from ExcelGenerator so the
Excel renderer, the web grid, and edit responses all share one source of truth.
No openpyxl, no solver. Keep the precedence EXACTLY as the original."""


def derive_cell_text(tech_id: str, day: int, day_assignments, night_assignments,
                     requests, nuc_tx_ids) -> str:
    """配置テキストを取得"""
    parts = []

    # 日勤配置
    if day in day_assignments:
        for loc_code, tech_ids in day_assignments[day].items():
            if tech_id in tech_ids:
                parts.append(loc_code)

    # 夜勤
    if day in night_assignments:
        if tech_id in night_assignments[day]:
            if parts:
                parts[0] += '夜'
            else:
                parts.append('夜')

    # 明け
    if day > 1 and (day - 1) in night_assignments:
        if tech_id in night_assignments[day - 1]:
            return '○'

    # Visualizing Requests (User Requirement)
    req_symbol = ""
    if day in requests and tech_id in requests[day]:
         req_symbol = requests[day][tech_id]

    # If Night Request matches Assignment, append (希)
    if req_symbol == '夜希':
         # Find the part with '夜' and mark it
         for i, p in enumerate(parts):
              if '夜' in p:
                  parts[i] = p + '(希)'

    # Fix: Ensure 17業/17休 is reflected
    if req_symbol in ['17業', '17休']:
        # append to list effectively
        parts.append(req_symbol)

    # 割り当てがない場合、申請を表示
    if not parts:
        if req_symbol and req_symbol != '休(仮)':
            return req_symbol

    # 核医学・治療のスタッフで、システムが付けた「休」を非表示にする
    # （夜勤・明け・申請休みがある場合はそちらが優先されるため、ここでは純粋な「休」を空欄化する）
    if tech_id in nuc_tx_ids and parts == ['休']:
        # 申請が休み系（◆, ☆, 17休など）でない場合は、空欄にする
        if not req_symbol or req_symbol in ['', '夜希', '休(仮)']:
            return ''

    # 「休」が割り当てられていても、予定申請があればそちらを優先表示
    if parts == ['休'] and req_symbol and req_symbol not in ['', '夜希', '休(仮)']:
        return req_symbol

    return '/'.join(parts) if parts else ''


def cell_fill(cell_value: str):
    """セルの背景色（16進カラー文字列）を取得。該当なしは None。"""
    if '夜' in cell_value:
        return 'FFFF00'
    if cell_value == '○':
        return 'FFC0CB'
    if cell_value in ['★', '☆', '◆']:
        return 'FFCDD2'
    if cell_value == '休':
        # Enforced Holiday (Grey)
        return 'D3D3D3'
    return None


import calendar
from datetime import date

from .stats_engine import _is_public_off  # 祝日/日曜判定の単一ソース（MR表記の祝日除外に使用）

# 21-column stats labels — excel_generator.py:100,144,202 (single source).
STATS_COLUMNS = ['夜勤', '病院MR', 'CLMR', '病CT', 'CT', 'ア', '心', 'ク', 'ポ', '精',
                 'MG', 'DR', 'HB', 'OP', '入', '病L', '超遅', 'ク遅', 'M遅', '公休', '代休']
# Superset gating has_work — excel_generator.py:150-154 (verbatim). Some codes
# (PICC/館山/TV/PET/RI/放治/DX) have no own stats column but still mark work.
WORK_LOCATION_CODES = {
    '病院MR', 'CLMR', 'CT', '病CT', 'ア', '心', 'ク', 'クL', 'ポ', '精',
    'MG', 'DR', 'HB', 'OP', 'PICC', '入', '病L', '超遅', 'ク遅', 'M遅',
    '館山', 'TV', 'PET', 'RI', '放治', 'DX',
}
_WEEKDAY = ['月', '火', '水', '木', '金', '土', '日']
_SPECIAL_OFF = {'★', '☆', '◆'}

# 時短スタッフの「表記のみ」固定配置（どの集計にも入れない）。
# 矢野(T003)は高齢・時短で、MRI手伝いとして毎週 月火木金 に「MR」と“表記だけ”表示する。
# build_grid では集計(_count_row)が終わった後に差し替えるため、夜勤/病院MR等いずれの
# 統計にも入らず、has_work も変えないので統計行は従来どおり非表示のまま。普段「休/空欄」の
# 平日だけを対象にし、◆申請休・夜勤明け(○)・祝日（出勤しない前提）はそのまま残す。
DISPLAY_ONLY_FIXED = {
    'T003': {'weekdays': {'月', '火', '木', '金'}, 'label': 'MR'},
}


def _kind_for(text):
    """Additive web-only cell metadata. Do NOT drive Excel fill off this; the
    Excel renderer keys fill off the final text via cell_fill()."""
    if text == '○':
        return 'akemei'
    if '夜' in text:
        return 'night'
    if text in _SPECIAL_OFF:
        return 'special_off'
    if text == '休':
        return 'off'
    if text == '':
        return 'empty'
    return 'work'


def _count_row(cells):
    """VERBATIM port of the counting loop excel_generator.py:158-192.
    公休/代休 are NOT counted here — they are injected after, from off/daikyu."""
    counts = {label: 0 for label in STATS_COLUMNS}
    has_work = False
    for text in cells.values():
        if '夜' in text:                  # whole-cell substring test, BEFORE split (:170)
            counts['夜勤'] += 1
        for p in text.split('/'):
            p = p.strip()
            if p.endswith('(希)'):        # normalization order: (希) -> （希） -> 夜
                p = p[:-3]
            elif p.endswith('（希）'):
                p = p[:-3]
            if p.endswith('夜'):
                p = p[:-1]
            if p in WORK_LOCATION_CODES:
                has_work = True
            if p == 'クL':                # :189 fold クL into ク
                p = 'ク'
            if p in counts:
                counts[p] += 1
    return counts, has_work


def build_grid(year, month, technicians, day_assignments, night_assignments,
               requests, off_counts=None, daikyu_counts=None,
               on_call_assignments=None, cells=None):
    """Whole grid (cells=None) or affected-staff fast path (cells={(sid,day),...}).
    Reuses derive_cell_text/cell_fill (P2a-1). 公休/代休 injected AFTER counting."""
    off_counts = off_counts or {}
    daikyu_counts = daikyu_counts or {}
    days = calendar.monthrange(year, month)[1]
    nuc_tx_ids = {t.id for t in technicians
                  if getattr(t, 'note', '') and ('核医学' in t.note or '治療' in t.note)}
    weekdays = {d: _WEEKDAY[date(year, month, d).weekday()] for d in range(1, days + 1)}

    scope = None if cells is None else {sid for (sid, _d) in cells}
    rows = []
    for t in technicians:
        if getattr(t, 'status', '在籍') != '在籍':
            continue
        if scope is not None and t.id not in scope:
            continue
        try:
            num = int(t.id.replace('T', ''))
        except ValueError:
            num = t.id
        row_cells, cell_meta = {}, {}
        for d in range(1, days + 1):
            text = derive_cell_text(t.id, d, day_assignments, night_assignments,
                                    requests, nuc_tx_ids)
            row_cells[d] = text
            cell_meta[d] = {"kind": _kind_for(text), "fill": cell_fill(text)}
        counts, has_work = _count_row(row_cells)
        counts['公休'] = off_counts.get(t.id, 0)      # inject AFTER counting (:195-196)
        counts['代休'] = daikyu_counts.get(t.id, 0)

        # 表示のみの固定配置（集計対象外）。集計が済んだ後に差し替えるので、どの統計にも
        # 入らず has_work も変えない。普段「休/空欄」の対象曜日だけを上書きし、◆申請休・
        # 夜勤明け(○)・夜勤・祝日（_is_public_off）はそのまま残す。
        fixed = DISPLAY_ONLY_FIXED.get(t.id)
        if fixed:
            for d in range(1, days + 1):
                if (weekdays[d] in fixed['weekdays']
                        and row_cells[d] in ('', '休')
                        and not _is_public_off(date(year, month, d))):
                    row_cells[d] = fixed['label']
                    cell_meta[d] = {"kind": _kind_for(fixed['label']),
                                    "fill": cell_fill(fixed['label'])}

        rows.append({
            "staff_id": t.id, "staff_num": num, "name": t.name,
            "cells": row_cells, "cell_meta": cell_meta,
            "has_work": has_work,
            "stats": counts if has_work else None,
        })

    oncall_rows = []
    if on_call_assignments:
        names = {t.id: t.name for t in technicians}
        for label in ('第1拘束', '第2拘束'):
            rc = {}
            for d in range(1, days + 1):
                sid = on_call_assignments.get(d, {}).get(label)
                if sid:
                    nm = names.get(sid, sid)
                    nm = nm.replace('(', '').replace(')', '').replace(' ', '').replace('　', '')
                    rc[d] = nm
                else:
                    rc[d] = ''
            oncall_rows.append({"label": label, "cells": rc})

    return {
        "year": year, "month": month, "days_in_month": days,
        "weekdays": weekdays, "stats_columns": STATS_COLUMNS,
        "rows": rows, "oncall_rows": oncall_rows,
    }

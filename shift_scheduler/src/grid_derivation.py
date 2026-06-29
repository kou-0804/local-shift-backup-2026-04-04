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

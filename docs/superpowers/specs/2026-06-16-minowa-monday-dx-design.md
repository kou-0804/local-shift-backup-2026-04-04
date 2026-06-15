# 設計仕様: 箕輪(T022) 月曜DX確保ルール（個別ルール）

**日付**: 2026-06-16
**対象**: `shift_scheduler/src/schedulers/day_scheduler.py`（`_schedule_one_day`）、
`shift_scheduler/src/excel_generator.py`（WORK_LOCATION_CODES）

## 目的
T022 箕輪綱平を、月曜日は DX 業務として確保し、臨床勤務（勤務地）に割り当てない。

## ルール
**対象**: T022、月曜日（weekday==0）のみ。

**適用条件（=箕輪の勤務日のとき）**:
- 国民の祝日でない（`jpholiday.is_holiday` 偽）かつ 1/1〜1/3 でない
- 本人の休み希望・有休・産育休等が無い（既存の `is_any_holiday(p_req)` で除外済み）
- 前日夜勤明けでない／前日夜勤でない（既存ロジックで除外済み）
- 当日夜勤でない（夜勤がある月曜は DX より夜勤を優先）

**挙動**:
- ハード: 箕輪に当日いかなる勤務地も割り当てない（候補から外し固定割当にする）
- セル表示は **「DX」**
- DX は**勤務日扱い**: 連勤カウントに含む／公休・代休にカウントしない／業務回数集計に非計上

**例外（休み優先）**: 月曜が祝日 or 箕輪の休み希望等なら DX を適用せず通常の休日ロジックを優先。

## 実装
既存の個別ルール前例（T002 第4火曜PET、`_schedule_one_day` 530行）に倣う。
`available_staff` 構築ループ内、休日・夜勤明け判定の後に次を追加:

```python
# 箕輪(T022): 月曜は DX として確保（勤務地に振らない）。祝日・休み希望は優先。
if (s.id == 'T022' and current_date.weekday() == 0
        and not jpholiday.is_holiday(current_date)
        and not (current_date.month == 1 and current_date.day in [1, 2, 3])):
    if not night_map.get((s.id, current_date)):
        forced_holidays.append(DayAssignment(
            date=current_date, staff_id=s.id, location_code='DX', rank=SkillRank.NONE))
        continue
```

`is_any_holiday(p_req)` の continue（休み希望）はこの行より前にあるため、休み優先は自動的に成立。

excel_generator の `WORK_LOCATION_CODES` に `'DX'` を追加し、DX を実勤務（勤務地）として
認識させる（全休行判定で勤務扱い）。

## 受け入れ基準（検証）
2026年7月再生成（月曜=6/13/20/27日）:
1. **どの月曜も箕輪は臨床勤務地ゼロ**（核心要求）。働く月曜は 'DX' 表示。
2. 箕輪の月曜が祝日/休み希望/夜勤明け強制休なら DX でなく休日表示（休み優先）。
3. DX 日は公休にカウントされない（勤務日扱い）。連勤≤6 維持。
4. 全ハード制約（欠員ゼロ等）維持。

### 確定時の実測・トレードオフ（2026-06-16）
- 7月結果: 月曜6・13=DX、20=休、27=夜勤明け休 → **全月曜で臨床勤務ゼロを達成**。
- 箕輪の総勤務日数は公休目標(9日)で固定のため、月曜が常に DX 勤務になるとは限らず、
  休日確保が必要な月曜は休になる（働く月曜のみ DX）。
- **代休は 1.0→5.0 日に増加**。これは「箕輪を月曜の臨床枠から外す」要求自体の不可避な
  コスト（彼の病CT/館山/病L枠を他者が肩代わり→他者の勤務増）。DX をハード化しても
  この代休は減らず、むしろ箕輪自身の代休が増えるため、現状方針を採用する。

## 非目標
- 他スタッフ・他曜日への一般化はしない（箕輪・月曜限定の個別ルール）。
- DX の中身（具体的業務内容）の管理はしない（表示のみ）。

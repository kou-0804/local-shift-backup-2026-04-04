# 代休×余剰公休の併存解消 — リバランサー強化 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 後段リバランサー `rebalance_workload()` を強化し、代休（公休<目標）が残る限り
ローテ要員の余剰公休（公休>目標）を代休解消へ回す。別部門/育休/新人/MRI専門を対象外にし、
半休(0.5)を扱い、連勤を厳守し、構造的に不可能なら理由を明示する。

**Architecture:** 既存の決定的グリーディ・リバランサー（`main.py` Phase 2.5）への増分強化。
純粋な判定ロジック（`_in_rotation`、併存計測）はモジュール関数として切り出し pytest で単体検証。
ループ本体の変更はフルパイプライン再生成 + `scratch/` 検証スクリプトで統合検証する。

**Tech Stack:** Python 3.13, pytest 8.3.3, openpyxl, ortools(CP-SAT は本プラン非変更), jpholiday

設計ドキュメント: `docs/superpowers/specs/2026-06-14-rebalancer-daikyu-surplus-coexistence-design.md`

---

## ファイル構成

- 変更: `main.py`
  - 新規モジュール関数 `_in_rotation(...)`（純粋判定）を `rebalance_workload` の直前に追加
  - 新規モジュール関数 `_coexistence_report(...)`（純粋計測）を追加
  - `rebalance_workload()`（現 477-638 行）のループ・集合構築を改修
- 新規: `tests/test_rebalancer_helpers.py`（純粋関数の pytest 単体テスト）

## 実行・検証コマンド（共通）

- 7月再生成: `python main.py --year 2026 --month 7 --output-dir scratch/plan_jul`
- 6月再生成: `python main.py --year 2026 --month 6 --output-dir scratch/plan_jun`
- 併存・代休計測: `python scratch/verify_schedule.py <xlsx> 2026 7`
- 単体テスト: `python -m pytest tests/test_rebalancer_helpers.py -v`

> 注: 本プロジェクトのリバランサーは巨大関数内のクロージャ中心のため、ループ本体は
> 単体テスト困難。純粋関数のみ pytest 化し、ループ改修は「再生成 → 計測 → 非劣化確認」で守る。

---

## Task 1: `_in_rotation` 純粋判定関数の追加（別部門/育休/新人/MRI専門の除外）

**Files:**
- Create: `tests/test_rebalancer_helpers.py`
- Modify: `main.py`（`rebalance_workload` 定義の直前, 現 476 行付近に新規関数を挿入）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_rebalancer_helpers.py`:

```python
from dataclasses import dataclass

from main import _in_rotation


@dataclass
class _S:
    id: str
    note: str = ""
    experience_years: int = 10


def test_separate_department_excluded():
    assert _in_rotation(_S("T058", note="核医学"), rest_val=31, num_days=31) is False
    assert _in_rotation(_S("T067", note="治療"), rest_val=31, num_days=31) is False


def test_mri_specialist_excluded():
    assert _in_rotation(_S("T005", note="MRI専門"), rest_val=9.5, num_days=31) is False


def test_new_staff_excluded():
    assert _in_rotation(_S("T057", note="", experience_years=1), rest_val=31, num_days=31) is False


def test_long_leave_excluded():
    # 大島/原田: 当月ほぼ全休（育休/長期休）
    assert _in_rotation(_S("T026", note="", experience_years=5), rest_val=21, num_days=31) is False
    assert _in_rotation(_S("T021", note="", experience_years=9), rest_val=31, num_days=31) is False


def test_normal_rotation_member_included():
    # 須田(+2)・河西(+1)・森(+0.5) は対象
    assert _in_rotation(_S("T011", note="", experience_years=18), rest_val=11, num_days=31) is True
    assert _in_rotation(_S("T007", note="", experience_years=25), rest_val=10, num_days=31) is True
    assert _in_rotation(_S("T024", note="", experience_years=7), rest_val=9.5, num_days=31) is True


def test_deficit_member_included():
    # 代休者(公休<目標)は当然ローテ内
    assert _in_rotation(_S("T036", note="", experience_years=4), rest_val=8.5, num_days=31) is True
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: FAIL（`ImportError: cannot import name '_in_rotation'`）

- [ ] **Step 3: 最小実装を追加**

`main.py` の `def rebalance_workload(` 行の直前に挿入:

```python
def _in_rotation(staff, rest_val, num_days, long_leave_slack: int = 6):
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS（6 件）

- [ ] **Step 5: コミット**

```bash
git add tests/test_rebalancer_helpers.py main.py
git commit -m "feat(rebalancer): add _in_rotation purity helper for scope hygiene"
```

---

## Task 2: `rebalance_workload` の over集合・mover を `_in_rotation` で絞る

**Files:**
- Modify: `main.py`（`rebalance_workload` 内, 現 571-579 行付近）

- [ ] **Step 1: ベースライン計測（before）を記録**

Run: `python main.py --year 2026 --month 7 --output-dir scratch/plan_base`
その後: `python scratch/verify_schedule.py scratch/plan_base/勤務表_2026年7月.xlsx 2026 7`
Expected: 代休 1.0 日（松井/田﨑 0.5 ずつ）・警告0 を記録（after 比較用）。

- [ ] **Step 2: over集合・under集合を `_in_rotation` で絞る実装**

`main.py` 現 571-579 行:

```python
    rest = {s.id: rest_count(s.id) for s in active}
    moves = 0
    changed = True
    rounds = 0
    while changed and rounds < 300:
        changed = False
        rounds += 1
        unders = sorted([s for s in active if rest[s.id] < target_holidays], key=lambda s: rest[s.id])
        overs = [s for s in active if rest[s.id] > target_holidays]
```

を次に置換:

```python
    rest = {s.id: rest_count(s.id) for s in active}
    # ローテ実働要員のみ（別部門/育休/新人/MRI専門は over も under も対象外＝触らない）
    rotation = [s for s in active if _in_rotation(s, rest[s.id], num_days)]
    moves = 0
    changed = True
    rounds = 0
    while changed and rounds < 300:
        changed = False
        rounds += 1
        unders = sorted([s for s in rotation if rest[s.id] < target_holidays], key=lambda s: rest[s.id])
        overs = [s for s in rotation if rest[s.id] > target_holidays]
```

- [ ] **Step 3: 再生成して非劣化を確認**

Run: `python main.py --year 2026 --month 7 --output-dir scratch/plan_t2`
その後: `python scratch/verify_schedule.py scratch/plan_t2/勤務表_2026年7月.xlsx 2026 7`
Expected: 代休が Step1 比で悪化しない・人員不足警告0。別部門/育休者へ誤って日勤が
振られていないこと（公休=31 の核医学/治療/原田が変わらないこと）を確認。

- [ ] **Step 4: 単体テスト回帰**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add main.py
git commit -m "feat(rebalancer): restrict over/under sets to rotation members"
```

---

## Task 3: 併存計測 `_coexistence_report` と正直なログ出力

**Files:**
- Modify: `main.py`（`_in_rotation` の直後に新規関数; `rebalance_workload` 末尾のログを拡張）
- Modify: `tests/test_rebalancer_helpers.py`（テスト追加）

- [ ] **Step 1: 失敗するテストを追加**

`tests/test_rebalancer_helpers.py` の末尾に追加:

```python
from main import _coexistence_report


def test_coexistence_report_counts():
    # rest_map: id -> 公休相当. target=9
    rest_map = {"A": 8.5, "B": 8.5, "C": 11, "D": 10, "E": 9}
    rep = _coexistence_report(rest_map, target=9)
    assert rep["n_under"] == 2
    assert rep["n_over"] == 2
    assert rep["daikyu_days"] == 1.0          # (9-8.5)*2
    assert rep["surplus_days"] == 3.0         # (11-9)+(10-9)
    assert rep["coexists"] is True


def test_coexistence_report_no_deficit():
    rest_map = {"A": 9, "B": 10, "C": 11}
    rep = _coexistence_report(rest_map, target=9)
    assert rep["n_under"] == 0
    assert rep["coexists"] is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: FAIL（`ImportError: cannot import name '_coexistence_report'`）

- [ ] **Step 3: 実装を追加**

`main.py` の `_in_rotation` の直後に挿入:

```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS

- [ ] **Step 5: `rebalance_workload` 末尾のログを拡張**

`main.py` 現 635-638 行:

```python
    n_under = sum(1 for s in active if rest[s.id] < target_holidays)
    n_over = sum(1 for s in active if rest[s.id] > target_holidays)
    print(f"  ⚖️ リバランサー(貪欲): {moves}件移動 → 目標未満{n_under}名 / 超過{n_over}名", flush=True)
    return day_result_list
```

を次に置換:

```python
    rot_rest = {s.id: rest[s.id] for s in rotation}
    rep = _coexistence_report(rot_rest, target_holidays)
    print(f"  ⚖️ リバランサー(貪欲): {moves}件移動 → ローテ内 代休{rep['n_under']}名({rep['daikyu_days']}日) "
          f"/ 余剰{rep['n_over']}名({rep['surplus_days']}日)", flush=True)
    if rep["coexists"]:
        # 代休と余剰が併存して残った＝これ以上の自動解消が出来なかった。理由を明示する。
        stuck = sorted([s for s in rotation if rest[s.id] < target_holidays], key=lambda s: rest[s.id])
        for U in stuck:
            print(f"    ⚠️ 代休残存: {U.name}(公休{rest[U.id]}) — 有資格・空き平日・連勤・性別の"
                  f"いずれかが噛み合わず肩代わり不能", flush=True)
    return day_result_list
```

- [ ] **Step 6: 再生成してログを確認**

Run: `python main.py --year 2026 --month 7 --output-dir scratch/plan_t3`
Expected: リバランサー行が「ローテ内 代休N名(X日) / 余剰M名(Y日)」形式になり、
代休残存時に氏名つき理由ログが出る。

- [ ] **Step 7: コミット**

```bash
git add main.py tests/test_rebalancer_helpers.py
git commit -m "feat(rebalancer): add coexistence report and honest stuck-deficit logging"
```

---

## Task 4: 代休最優先ループ — 最後の代休を消すための 0.5 超過許容

**Files:**
- Modify: `main.py`（`rebalance_workload` 内 over/under 構築直後, Task2 改修箇所）

設計 3.2。現状は recipient O が `rest[O.id] <= target` だと候補外（=余剰者のみ受け手）。
これは維持しつつ、mover U 側で「全日移動すると U が target を 0.5 超過してしまう」ケースを
**代休が減るなら許容**するよう、ループ継続条件を明確化する。現状ループは U が under である
限り日を回し、0.5 不足の U に全日移動すると +0.5 余剰になる（これは設計上許容＝代休が減る）。
本タスクは「代休が残る限り余剰を使い切る」意図を `break` 分岐で明示する。

- [ ] **Step 1: under/over 構築直後の早期終了を明確化**

`main.py` 現 580-581 行:

```python
        if not unders or not overs:
            break
```

を次に置換（意図を 2 分岐で明示）:

```python
        if not unders:
            break          # 代休ゼロ＝残余余剰は許容。これ以上動かさない
        if not overs:
            break          # 受け手(余剰者)なし＝肩代わり不能
```

- [ ] **Step 2: 再生成して非劣化を確認**

Run: `python main.py --year 2026 --month 7 --output-dir scratch/plan_t4`
その後: `python scratch/verify_schedule.py scratch/plan_t4/勤務表_2026年7月.xlsx 2026 7`
Expected: 代休が Task2 比で非劣化（理想は減少、最低でも悪化なし）・警告0。

- [ ] **Step 3: 単体テスト回帰**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS

- [ ] **Step 4: コミット**

```bash
git add main.py
git commit -m "feat(rebalancer): deficit-first loop — stop only when no deficit remains"
```

---

## Task 5: 半休(0.5)対応 — 0.5 代休を半日移動で解消

**Files:**
- Modify: `main.py`（`rebalance_workload` 内, 半日要素の扱いを追加）

設計 3.3。松井/田﨑 の 0.5 代休は「全日移動だと相手が見つからない」上に「不足が半日」。
半日要素 `出/☆` 等を mover が持つ日では、その日の実業務 L を recipient へ移し、U を半休のまま
全休化して 0.5 を確保する経路を許可する（現状 `if req_map.get((U.id,d)): continue` が
半休日を一律スキップしているのを、半休シンボルに限り通す）。

- [ ] **Step 1: 半休シンボル集合を定義**

`main.py` `rebalance_workload` 内, `LATE = {...}`（現 498 行）の直後に追加:

```python
    HALF = {'出/☆', '出/(発)', '出(発)', '☆/(発)', '☆/(聴)'}   # 0.5公休を含む半日勤務
```

- [ ] **Step 2: mover の半休日も移動候補に通す**

現 598-599 行:

```python
                if req_map.get((U.id, d)):
                    continue
```

を次に置換:

```python
                sym_u = req_map.get((U.id, d))
                if sym_u and sym_u not in HALF:
                    continue          # 半休(0.5)日は移動候補に通す。それ以外の申請日は不可
```

- [ ] **Step 3: 再生成して 0.5 代休の挙動を確認**

Run: `python main.py --year 2026 --month 7 --output-dir scratch/plan_t5`
その後: `python scratch/verify_schedule.py scratch/plan_t5/勤務表_2026年7月.xlsx 2026 7`
Expected: 松井/田﨑 の 0.5 代休が解消 or 非劣化。半休セルが壊れていない（`出/☆` が
不正な全休/二重休になっていない）こと、警告0・全個別ルール遵守を確認。
※ 解消できない場合は Task3 の理由ログで「噛み合わず」が出ることを確認（正直性）。

- [ ] **Step 4: 単体テスト回帰**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add main.py
git commit -m "feat(rebalancer): allow half-day (0.5) movers to cover half-day deficits"
```

---

## Task 6: 連勤の厳格化 — 移動先の連勤チェック維持＋見送り可視化

**Files:**
- Modify: `main.py`（`rebalance_workload` 内, recipient ガード 現 622-623 行 と moves 初期化 現 572 行）

設計 3.4。recipient O は既に `consec_if_work(O,d) > 6` でガード済（現 622 行）。
mover U は休にする＝連勤が減るのみで悪化しない。本タスクでは締めすぎ防止のため
ハードは現状の `> 6` を維持し、連勤6到達で見送った候補数を計測・ログ化する。

- [ ] **Step 1: 連勤見送りカウンタを追加**

`main.py` 現 572 行 `moves = 0` の直後に追加:

```python
    moves = 0
    skipped_consec = 0
```

現 622-623 行:

```python
                    if consec_if_work(O.id, d) > 6:
                        continue
```

を次に置換:

```python
                    if consec_if_work(O.id, d) > 6:
                        skipped_consec += 1
                        continue
```

- [ ] **Step 2: ログに連勤見送り数を出力**

Task3 で改修した末尾ログの `print(f"  ⚖️ リバランサー(貪欲): {moves}件移動 → ローテ内 ...")`
行を次に置換:

```python
    print(f"  ⚖️ リバランサー(貪欲): {moves}件移動 (連勤6で見送り{skipped_consec}件) → "
          f"ローテ内 代休{rep['n_under']}名({rep['daikyu_days']}日) "
          f"/ 余剰{rep['n_over']}名({rep['surplus_days']}日)", flush=True)
```

- [ ] **Step 3: 再生成して連勤遵守を確認**

Run: `python main.py --year 2026 --month 7 --output-dir scratch/plan_t6`
その後: `python scratch/verify_schedule.py scratch/plan_t6/勤務表_2026年7月.xlsx 2026 7`
Expected: 連勤6超が0件（verify_schedule の連勤判定）。ログに見送り件数が出る。

- [ ] **Step 4: 単体テスト回帰**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add main.py
git commit -m "feat(rebalancer): surface consec-6 skipped candidates for visibility"
```

---

## Task 7: 統合検証 — 7月/6月 回帰・決定性・警告0・正直な総括

**Files:**
- 変更なし（検証のみ）。結果の要約を本プラン末尾に追記してよい。

- [ ] **Step 1: 7月を2回生成して決定性（MD5一致）を確認**

```bash
python main.py --year 2026 --month 7 --output-dir scratch/plan_det1
python main.py --year 2026 --month 7 --output-dir scratch/plan_det2
md5 scratch/plan_det1/勤務表_2026年7月.xlsx scratch/plan_det2/勤務表_2026年7月.xlsx
```
Expected: 2つの MD5 が一致（決定性維持）。

- [ ] **Step 2: 7月の最終品質を計測**

Run: `python scratch/verify_schedule.py scratch/plan_det1/勤務表_2026年7月.xlsx 2026 7`
Expected: 全個別ルール遵守・人員不足警告0・連勤6超0。代休は base（1.0日）比で
非劣化（理想 0、不能なら理由ログ）。

- [ ] **Step 3: 6月で回帰**

```bash
python main.py --year 2026 --month 6 --output-dir scratch/plan_jun
python scratch/verify_schedule.py scratch/plan_jun/勤務表_2026年6月.xlsx 2026 6
```
Expected: 6月 代休が従来（3.0日）比で非劣化・警告0・全ルール遵守。

- [ ] **Step 4: 精密公平性レポートで副作用なしを確認**

Run: `python scratch/fairness_report.py scratch/plan_det1/勤務表_2026年7月.xlsx 2026 7`
Expected: 保護除外の場所別ばらつきが従来比で悪化していない。

- [ ] **Step 5: 全単体テスト**

Run: `python -m pytest tests/test_rebalancer_helpers.py -v`
Expected: PASS（全件）

- [ ] **Step 6: 結果を正直に総括してコミット**

代休が0にできた場合はその旨、できなかった場合は「女性ク有資格の余剰者が河西1名・
空き平日が噛み合わない」構造的理由を `verification-before-completion` に従い証拠つきで報告。
最終出力を `output/` に反映する場合:

```bash
python main.py --year 2026 --month 7 --output-dir output
git add -A
git commit -m "chore: regenerate July with strengthened rebalancer"
```

---

## Self-Review（プラン作成者による確認結果）

- **spec カバレッジ**: 3.1→Task1/2, 3.2→Task4, 3.3→Task5, 3.4→Task6, §4検証→Task7,
  §2正直性→Task3。全項目に対応タスクあり。
- **プレースホルダ**: なし（全 step に実コード/実コマンド/期待値を記載）。
- **型・名称整合**: `_in_rotation(staff, rest_val, num_days, long_leave_slack)` /
  `_coexistence_report(rest_map, target)` をタスク間で一貫使用。`HALF`/`skipped_consec`/
  `rotation`/`rep` の参照は定義タスク内で導入済み。
- **既知の前提**: `num_days` は `rebalance_workload` 冒頭（現 487 行）で定義済みのため
  Task2 の `rotation` 構築時に利用可能。

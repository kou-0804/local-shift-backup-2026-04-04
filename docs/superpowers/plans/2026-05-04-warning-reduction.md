# Warning Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 5月2026年の勤務表警告を32件から20件以下に削減する（代休0件を維持）

**Architecture:** 2段階アプローチ。①プリシーダー（事前休み配置）の安全バッファを重要場所ごとに強化し、ソルバーに渡る候補数を増やす。②CP-SAT ソルバーの場所別不足ペナルティを調整し、CTなど重要場所の充足を優先させる。夜勤HB警告は Fix 1+2 後の残数に応じてFix 3で対処。

**Tech Stack:** Python 3.13, Google OR-Tools CP-SAT, jpholiday

---

### Task 1: プリシーダー安全バッファ強化（Fix 1）

**Files:**
- Modify: `main.py:313-351` （`_would_exceed_skill_capacity` 内の threshold 行）

ベースライン確認（変更前）:

- [ ] **Step 1: ベースライン警告数を記録する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep "⚠️.*件の警告"
```

期待出力: `⚠️ 32件の警告が発生しました`

- [ ] **Step 2: `_would_exceed_skill_capacity` の threshold 行を修正する**

`main.py` の349行目付近を以下のように変更する。

変更前（main.py line 348）:
```python
            threshold = req_count + 1  # 一律+1バッファ（1人余裕を残す）
```

変更後:
```python
            # 重要場所は大きなバッファで保護し、同日に休みが集中するのを防ぐ
            CRITICAL_BUFFER = {
                '病CT':  4,   # req=6 → threshold=10
                'CT':    3,   # req=4 → threshold=7
                '病院MR': 3,  # req=3 → threshold=6
                'CLMR':  2,   # req=4 → threshold=6
                'MG':    2,   # req=1 → threshold=3
            }
            threshold = req_count + CRITICAL_BUFFER.get(loc.code, 1)
```

- [ ] **Step 3: 変更後に実行して代休が増えていないか確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep -E "⚠️.*件の警告|代休|事前公休割り当て"
```

期待出力:
- `事前公休割り当て: NN件`（件数は前後してよい）
- `0名に計0日の代休を付与`（代休0件を維持）
- 警告数が32件以下になっていることを確認（まだ大幅減でなくてよい）

- [ ] **Step 4: Fix 1 のみをコミットする**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
git add main.py
git commit -m "Fix: Strengthen pre-seeder safety buffer for critical locations

Increase threshold from req+1 to req+N for CT/病CT/病院MR/CLMR/MG.
Prevents CT/病CT-qualified staff from clustering rest days on the same
days, giving the day scheduler more candidates on understaffed days.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: 場所別不足ペナルティ調整（Fix 2）

**Files:**
- Modify: `shift_scheduler/src/schedulers/day_scheduler.py:815-828` （DH-03 セクション）

- [ ] **Step 1: DH-03 セクションを場所別ペナルティに書き換える**

`day_scheduler.py` の815行目付近を以下のように変更する。

変更前（lines 815-828）:
```python
        # DH-03: Required Headcount with Understaffing Penalty
        DEFICIT_PENALTY = 100000 # 配置不足1名につき10万点のペナルティ
        deficit_vars = []

        for loc in target_locations:
            req = location_needs[loc.code]
            vars_l = [x[s.id, loc.code] for s in available_staff if (s.id, loc.code) in x]

            # shortage = 目標人数(req) - 実際の配置人数
            shortage = model.NewIntVar(0, req, f'shortage_{loc.code}_{current_date}')
            model.Add(sum(vars_l) + shortage == req)

            # 配置不足分をペナルティとして記録
            deficit_vars.append(shortage * DEFICIT_PENALTY)
```

変更後:
```python
        # DH-03: Required Headcount with Understaffing Penalty
        # 場所の重要度に応じてペナルティを調整する。
        # パワーバランス制約(3M)と競合しないよう、2倍程度の控えめな引き上げにとどめる。
        DEFICIT_PENALTIES = {
            'CT':    200000,  # 2倍: ポ/クへの副作用を最小化しつつCT充足を促進
            'MG':    150000,  # 1名枠の完全未配置を防ぐ
            'OP':    150000,
            '超遅':  150000,
        }
        DEFICIT_PENALTY_DEFAULT = 100000
        deficit_vars = []

        for loc in target_locations:
            req = location_needs[loc.code]
            vars_l = [x[s.id, loc.code] for s in available_staff if (s.id, loc.code) in x]

            # shortage = 目標人数(req) - 実際の配置人数
            shortage = model.NewIntVar(0, req, f'shortage_{loc.code}_{current_date}')
            model.Add(sum(vars_l) + shortage == req)

            # 場所別ペナルティを適用
            penalty = DEFICIT_PENALTIES.get(loc.code, DEFICIT_PENALTY_DEFAULT)
            deficit_vars.append(shortage * penalty)
```

- [ ] **Step 2: 実行して警告数と代休を確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep -E "⚠️.*件の警告|0名に計0日|代休"
```

期待出力:
- 警告数が 32件より少ない（目標 20件以下）
- `0名に計0日の代休を付与`（代休0件維持）

- [ ] **Step 3: 警告の内訳を確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep "^    - "
```

確認ポイント:
- CT の警告が減っているか（旧: 9件）
- 病CT の警告が減っているか（旧: 8件）
- 病院MR の警告が減っているか（旧: 7件）
- ポ・ク の新規警告が大量に発生していないか

もし ポ/ク の警告が増えた場合は、CT の DEFICIT_PENALTY を 200000 から 150000 に下げてStep 2を再実行する。

- [ ] **Step 4: Fix 2 をコミットする**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
git add shift_scheduler/src/schedulers/day_scheduler.py
git commit -m "Fix: Add location-specific deficit penalties in day scheduler

CT raised to 200K (from 100K) to break solver indifference between CT
and other locations. MG/OP/超遅 raised to 150K to prevent zero-staffing.
Keeps power balance constraints (3M) dominant to avoid rank violations.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 1+2 の結果検証

**Files:** 変更なし（確認のみ）

- [ ] **Step 1: 最終的な警告数を確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep -E "件の警告|代休|夜勤HB"
```

- [ ] **Step 2: 場所別の改善を表にまとめる（目視確認）**

出力の `- [場所]` 行から以下を確認:

| 場所 | 旧警告数 | 新警告数 | 判定 |
|------|---------|---------|------|
| CT | 9 | ? | ↓ が目標 |
| 病CT | 8 | ? | ↓ が目標 |
| 病院MR | 7 | ? | ↓ が目標 |
| 夜勤HB | 2 | ? | → Fix 3 の要否判断 |

- [ ] **Step 3: 夜勤HB警告が残っているか確認し Fix 3 の要否を判断する**

夜勤HB警告（`夜勤メンバーにHB対応可能者がいない`）が残っていれば Task 4 へ進む。  
残っていなければ Task 4 をスキップして Task 5（最終コミット）へ進む。

---

### Task 4: 夜勤HBカバレッジ改善（Fix 3、条件付き）

> Task 3 で夜勤HB警告が残っていた場合のみ実施する。

**Files:**
- Read first: `shift_scheduler/src/schedulers/night_scheduler.py:249-259`
- Modify: `shift_scheduler/src/schedulers/night_scheduler.py:251`

- [ ] **Step 1: 現在の HB 制約を確認する**

```bash
grep -n "HB\|hb\|WEIGHT_HB" "/Users/kohei/Desktop/local-shift ver1/shift_scheduler/src/schedulers/night_scheduler.py"
```

現在の実装（line 251付近）:
```python
WEIGHT_HB_COVERAGE = 100000
hb_staff = [s for s in self.night_staff if getattr(s, 'night_hb', False)]
if hb_staff:
    uncovered_hb = model.NewBoolVar(f'uncovered_hb_{d}')
    hb_sum = sum(x[s.id, d] for s in hb_staff)
    model.Add(hb_sum >= 1).OnlyEnforceIf(uncovered_hb.Not())
    model.Add(hb_sum == 0).OnlyEnforceIf(uncovered_hb)
    penalties.append(uncovered_hb * WEIGHT_HB_COVERAGE)
```

- [ ] **Step 2: WEIGHT_HB_COVERAGE を3倍に引き上げる**

`night_scheduler.py` の251行目を変更:

変更前:
```python
        WEIGHT_HB_COVERAGE = 100000
```

変更後:
```python
        WEIGHT_HB_COVERAGE = 300000  # 夜勤HB未カバーを強く抑制
```

- [ ] **Step 3: 実行して夜勤HB警告が減ったか確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep -E "件の警告|夜勤.*HB"
```

期待: `夜勤メンバーにHB対応可能者がいない` が 0件または1件に減少。

- [ ] **Step 4: Fix 3 をコミットする**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
git add shift_scheduler/src/schedulers/night_scheduler.py
git commit -m "Fix: Raise night HB coverage penalty from 100K to 300K

Stronger incentive ensures HB-capable staff are included in night teams.
Addresses uncovered HB warnings on 5/9 and 5/23.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: 最終検証とまとめ

**Files:** 変更なし（確認のみ）

- [ ] **Step 1: 最終実行して結果を確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep -E "件の警告|代休|0名に計0日"
```

合格基準:
- 警告数 ≤ 20件（目標）
- 代休0件維持（`0名に計0日の代休を付与`）

- [ ] **Step 2: 警告の内訳を最終確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
python3 main.py --year 2026 --month 5 2>&1 | grep "^    - "
```

- [ ] **Step 3: main.py に追加した警告詳細表示を保持していることを確認する**

main.py の validation_errors ループ部分が残っていることを確認:
```bash
grep -A3 "件の警告が発生しました" "/Users/kohei/Desktop/local-shift ver1/main.py"
```

期待:
```python
         print(f"  ⚠️ {len(validation_errors)}件の警告が発生しました")
         for err in validation_errors:
             print(f"    - {err}")
```

- [ ] **Step 4: git log で変更を確認する**

```bash
cd "/Users/kohei/Desktop/local-shift ver1"
git log --oneline -5
```

期待（順番は Fix 3 の有無で変わる）:
```
xxxxxxx Fix: Raise night HB coverage penalty ...  (Fix 3 実施時のみ)
xxxxxxx Fix: Add location-specific deficit penalties in day scheduler
xxxxxxx Fix: Strengthen pre-seeder safety buffer for critical locations
xxxxxxx Docs: Add warning reduction design spec
```

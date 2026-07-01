# 開発記録: ルール監査・公休上限（余剰空欄化）・実質コンプライアンスチェッカー

**日付**: 2026-07-01
**ブランチ**: feature/web-app-v1
**担当**: Claude (Opus 4.8) + kou-0804

---

## 0. 背景・きっかけ（ユーザー依頼）

1. 「勤務表の作成について、様々なルールや制約がしっかり反映されているか今一度確認してほしい」
2. 「公休数が9に対して休みが多すぎないか。エラーは出ていないが本当に勤務条件を満たしているか怪しい」
3. （方針）「余計な休みをつけるくらいなら、規定人数を満たし不要な日は空欄にしておいてほしい。組みやすいなら採用して」
4. （要望）「同じ場所にCSVを入れた場合は上書きするようにしてほしい」
5. （質問）「夜勤回数は常にWebアプリの夜勤回数マスターを参照する設定は可能か」→ **A（単一マスターを編集して運用／改修なし）を選択**

---

## 1. ルール監査（12分類 / 100制約 / 敵対的再検証）

多エージェント監査を実施。仕様書 `shift_scheduler_specification_v2.md` の全制約（NH/DH/DS/PB/SR＋個別・拘束・育成・公休/代休）を**実コードと突合**し、各不備を独立エージェントで再検証。**確定45件（High 6 / Medium 25 / Low 14）**。

### 全体を貫く構造的事実（最重要）
> このスケジューラは「月末にINFEASIBLE（解なし）にならない」ことを最優先に設計されており、**仕様上ハードの多くが実際は超高重みのソフト・ペナルティ**。解けた後の検証は**人数しか見ていない**のに、Excelは「✅ すべての配置・スキル要件が正常」と表示する。
> ⇒ **「エラーなし」≠「条件充足」。** ユーザーの疑いは正しかった。

### High（6件）
| ID | 内容 | 対応 |
|---|---|---|
| DH-06 性別 | MG女性限定ガードが死にコード（`'female'`≠`'女性のみ'`）。MGスキル者が偶然全員女性のため事故っていないだけ | **本セッションで修正済** |
| NH-07 / SYM-01 夜勤不可記号 | `出`,`出/講`,`研(座)`,`出/(役)` が夜勤禁止セットに無く、夜勤に入れてしまう（仕様§8.1は夜勤=×） | 未対応 |
| NH-06 夜勤モダリティ | MR/アンギオ/心カテを各≥1で課すのみ。3名が別人で3役を同時カバーできる保証なし（distinct-matching無し）※仕様§4.5は兼務を許容するため「情報」扱いが妥当 | チェッカーで情報検出 |
| PO-05 夜勤詰み | 夜勤INFEASIBLE時に未捕捉例外で月全体が異常終了（Web版500）。緩和ラダー未実装 | 未対応 |
| 58 業務拡大 | 育成ペアリングが本番で `disable_training=True` により全面OFF（無条件） | 未対応（意図的の可能性） |

Medium/Low の代表: 必要人数(DH-03)/ランク下限(PB-01)/夜希/夜勤回数/中3日間隔 が軒並みソフト、代休は上限なし（設計上リバランサーで実質0へ）、DS-02連続配置は仕様と逆（分散＝意図的）、NightSkillDeriver死にコード（閾値B実使用/C仕様）、拘束2名保証なし、夜勤回数合計チェック(E003)欠如 等。

**完全な監査ダイジェスト**はワークフロー実行結果（`confirmedIssues`／`fullDigest`）に保存。45件の各 file:line 付き。

---

## 2. 実装した変更

### 2-1. DH-06 性別ガードのバグ修正（High）
死にコードを4か所修正。`== '女性のみ'` → `in ('female', '女性のみ')`。
- `shift_scheduler/src/schedulers/day_scheduler.py:783`
- `main.py:675, 742, 936`

理由: `location_loader` はCSVの `女性のみ` を `'female'` に正規化するが、全消費側が `'女性のみ'` と比較し常にFalse。現状MGスキル者は全員女性なので配置・Excelは不変（パリティ影響なし）。ガードが正しく機能するようになった。

### 2-2. ② 実質コンプライアンスチェッカー（新規）
**`shift_scheduler/src/compliance_checker.py`** を新規作成し、`main.py run_schedule` に**レポート専用**で組込み（try/exceptで囲みラン中断ゼロ・Excelバイト不変＝パリティ安全）。`stats_engine` が「P3（skill/PB）」として先送りしていた層を実装。

解の**後で**以下を再検証し、未達を正直に列挙:
- DH-03 必要人数（stats_engine coverage再利用）
- DH-01 二重配置 / DH-05 夜勤明け日勤 / DH-06 性別 / DH-09 6連勤
- PB-01/02/03 ランク下限・CD上限・D単独
- SR-01(ア火A×2) / SR-03(HB第1金A×2) / SR-04(HB第4木A×3) / SR-06(精水金A限定)
- NH-06 夜勤モダリティ: **無資格=違反(high)**、**同時対応不可=情報(NH-06b)**（仕様§4.5が兼務を許容するため区別）
- OFF-SURPLUS: 公休>目標の情報集計

実データ結果: 6月=違反0/情報9、7月も同様に情報中心（=スケジューラのハード制約は機能、静かなソフト未達も可視化）。

### 2-3. ① 公休の余剰空欄化（ユーザー方針）
**`main.py assign_monthly_off_days`**: 全blank→休の変換をやめ、既に計算済みだが未使用だった `blanks_quota (= max(0, target - explicit_off))` を採用。**規定到達分だけを月内に分散(`_pick_best_day`)して`休`化し、余剰blankは空欄のまま**（未割当・公休カウント外）。公休カウント = 明示公休 + 付与`休` + 0.5×半休。

**`shift_scheduler/src/stats_engine.py recompute_off_daikyu`**: 同一ロジックで整合。`blanks_counted = min(blank, max(0, target - explicit_off))`。Web再計算とExcel/CLIの公休表示が一致（一貫性のため必須：余剰空欄を数えないと二重計上→不一致）。

**設計上の安全性**: `assign_monthly_off_days` は day-solve→rebalance→cpsat の**後**の最終段。work割当は変更せず、`休`ラベリングとカウントのみ変更。代休（不足側）ロジックは不変（余剰側だけキャップ）。`休`でも空欄でも非勤務＝6連勤カウントに等価。

**検証（7月2026, 目標9）**:
| | >9(過剰) | =9 | <9 | max | mean |
|---|---|---|---|---|---|
| Before | 24/49 | 22 | 3 | 26 | 10.23 |
| **After** | **9/49** | **39** | 1 | 21 | **9.38** |

残る>9は全て `育休/★☆` 等の**明示休**（例: 原田勝人=31は当月全日 `☆育`＝データ通り正当）。blank起因の過剰休は解消。

### 2-4. 予定申請の上書きインポート（Web）
**`webapp/api/requests_import.py store_requests`**: 同月の再インポートで旧 `requests_import`＋`request_row` を削除してから挿入（真の上書き）。docstringの「replaced by re-upload」契約を実装通りに。
- 既存DB(`webapp_data/shift.db`)の重複8月行（id 1,2）を最新1件へ整理済。
- 注: sqlite rowidは再利用され得る（機能上問題なし、テストは月内1行＋孤児0で検証）。

---

## 3. テスト

- 新規 `tests/test_compliance_checker.py`（9件）: 性別/夜勤明け/二重配置/PBランク下限/SR-01/夜勤モダリティを合成データで検出、クリーンは0違反。
- 新規 `tests/test_offday_cap.py`（5件）: 全未配置でも公休9で頭打ち／真の不足は代休4維持／半休0.5。
- 更新 `tests/test_edits.py`（2件）: 旧「blank=+1公休（無制限）」モデルを新方針（余剰=空欄=公休外、目標で頭打ち）に合わせて改名・修正。
- 更新 `tests/test_requests_import.py`（+1件）: 同月再インポート＝上書き（月内1行/孤児0）。
- **高速スイート: 215 passed**（`-m "not slow"`）。
- golden fixtures 再生成（6月実解1回）: `tests/golden/2026-06_{assignments,p2a1,p2a2,excel_parity}.json`（`scratch/regen_golden.py` ＋ 既存gen scripts。**PYTHONPATH必須**）。
- **slow スイート（10件）: 再生成後 9 passed / 1 failed**。唯一の失敗 `test_lock_resolve.py::test_night_force_occupancy_and_no_day_domain_leak` は**私の変更起因ではないことを証明**: 旧(git HEAD)goldenでも新goldenでも `_pick_night` は day6(Sn=T011) を選ぶが、その日の GENERAL 8名が全員 night-union(37) に含まれ、リーク検証用の `Sd` が None → セットアップの `assert Sd` で失敗（＝コミット済goldenに対し以前から失敗する脆いテスト。①は夜勤/GENERAL配置を変えない）。**修正**: 有効な (D,Sn,Sd) を持つ日を探索するよう堅牢化（本golddenに14日該当）。挙動アサーション(517-519)は不変。

---

## 4. アーキテクチャ上の発見（夜勤回数マスターの扱い）

- **Web生成は既に「夜勤回数マスター(`ms_night_quota`)」を参照**している。`run_job_materialized`→`materialize._rows_night_quota` が `ms_night_quota` から `夜勤回数_確定版.csv` を生成。**静的CSVを使うのはCLIのみ**。
- `ms_night_quota` は `year_month` 列を持つが、**materialize は月で絞り込まず全行を書き出す**（`replace_night_quota` も月無関係に全置換）＝**実質「単一セット」**。現状は39名・合計93（=31×3）・ラベル「7月」。
- `load_night_counts` は対象月列が無いと**先頭の回数列にフォールバック**（＝マスターの回数が任意月で使われる。CLIの「〇月列なし→フォールバック」警告と同機構、実害なし）。
- 対照的に **`ms_holiday_target` は月別対応済み**（`year_month` で `2026/08=9` 等）。
- 結論: **A案**＝マスターの夜勤回数を8月用に編集（合計93維持）→Web生成、で改修なしに機能。**B案**（月別共存）は `ms_night_quota`＋`materialize`＋編集UI契約を月別に、が必要（未着手・要望あれば実装）。

---

## 5. 8月生成の手順（A案）

1. マスター画面で `現行` セットの**夜勤回数**を8月用に編集（**合計は93のまま**＝合計チェックあり）。現状値のままで良ければ編集不要。
2. Webアプリで **2026年8月** を生成。materializeが夜勤回数マスター＋8月予定申請（DBに取込済）＋公休目標9（月別）＋他マスターを使用。
3. ①余剰空欄・②実質チェッカーは自動適用。

---

## 6. 未対応・フォローアップ

- **残りHigh監査項目**: NH-07/SYM-01（夜勤不可記号 `出`/`出/講`/`研(座)`/`出/(役)`）、NH-06 distinct-matchingのハード化要否、PO-05（夜勤詰みのgraceful化）、58（業務拡大の有効化要否）、NSKILL閾値(B/C)整理、QUOTA-01（夜勤回数合計チェック追加）。
- **Excel「✅正常」誤表示の是正**: チェッカー結果を検証シート／Web UIに反映（Excelバイト変更→golden再生成必要）。
- **B案**: 夜勤回数の月別対応。
- **データ点検**: 原田勝人=全日☆育、大島七泉=21休 等の妥当性（データ由来だが要確認）。名前解決の脆弱性（QUOTA-02）。

---

## 7. 変更ファイル一覧

| ファイル | 変更 |
|---|---|
| `main.py` | ①公休キャップ(assign_monthly_off_days)、DH-06修正(675/742/936)、②チェッカー組込み |
| `shift_scheduler/src/schedulers/day_scheduler.py` | DH-06修正(783) |
| `shift_scheduler/src/stats_engine.py` | ①公休カウント整合(recompute_off_daikyu) |
| `shift_scheduler/src/compliance_checker.py` | **新規** ②実質チェッカー |
| `webapp/api/requests_import.py` | 予定申請 上書きインポート(store_requests) |
| `tests/test_compliance_checker.py` | **新規** 9件 |
| `tests/test_offday_cap.py` | **新規** 5件 |
| `tests/test_edits.py` | 2件を新方針へ更新 |
| `tests/test_requests_import.py` | 上書きテスト +1件 |
| `tests/golden/2026-06_*.json` | 再生成（4ファイル） |
| `scratch/regen_golden.py` | **新規** golden再生成ツール |

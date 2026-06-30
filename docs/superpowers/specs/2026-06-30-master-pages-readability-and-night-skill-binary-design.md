# マスター画面の可読性向上 ＋ 夜勤スキルの2状態（可/不可）化 — 設計

- 日付: 2026-06-30
- ブランチ: feature/web-app-v1
- 対象: 院内Webアプリ（FastAPI + React + SQLite）のマスター管理画面

## 1. 目的 / 背景

現状のマスター画面はブラウザ既定スタイルのままで素っ気なく見づらい。特に2点を改善する。

1. **スキルマスタ**：ランク（A〜D・「-」）が文字だけで、習熟度が一目で分からない。→ 視覚的に判別できる色分け＋全体の見た目を「病院ITシステムらしいクリーンなUI」に刷新する。
2. **夜勤スキル一覧**：現状は `TRUE` / `継承`（および `FALSE`）の3状態で、文言が分かりにくい。実態として「**日中勤務は可能でも夜勤帯はNG**」というケースがあり、夜勤可否は日中スキルから機械的に決まらない独立属性である。→ **「夜勤可 / 夜勤不可」の2状態**として明示的・独立に管理できるUIにする。

## 2. 確定した決定事項

| 項目 | 決定 |
|---|---|
| スキルランク色分け | A=🟩エメラルド / B=🟦ブルー / C=🟨アンバー / D=🟧オレンジ / -=⬜スレート（無効）。文字（A〜D）も併記しアクセシビリティ確保。 |
| マスター全体の見た目 | 白＋スレートグレー基調、アクセントは医療系ティール（#0f766e）。ヘッダー強調・行ホバー・余白・ヘッダー固定・ピル型タブ・カード枠。専用CSS `masters.css` を1枚追加（既存のプレーンCSS方針を踏襲。Tailwind等は導入しない）。 |
| 夜勤スキルのラベル | 🟩 **夜勤可**（TRUE）／🟥 **夜勤不可**（FALSE）。色分けあり。 |
| 夜勤スキルの管理方式 | **① 全員明示化（独立管理）**。現在の自動判定値を一度だけ全セルに焼き込み、以後は日中スキルと完全に切り離して手動管理。 |

## 3. 非目標（やらないこと）

- スケジューラ（`shift_scheduler/`）の配置ロジックの変更。
- 夜勤可否の派生規則（スキルB以上＝可）の規則そのものの変更。**派生ロジックは削除しない**（HBの夜勤要員判定に必須のため）。
- スキル列（＝勤務場所）の追加・削除（別途・管理者機能）。
- ロスター（勤務表）グリッドの再スタイル（直近で整備済み。今回はマスター画面のみ）。

## 4. 重要な制約（安全性）

ユーザーの最優先要件は「**不具合を出さない**」。本変更は以下を厳守する。

- **スケジュール出力はビット単位で不変**：移行（焼き込み）後にスケジューラを走らせた結果が、移行前と完全一致すること。既存のパリティ／決定性テストで検証する（cutover gate）。
- **保存値フォーマットは不変**：`ms_night_override` のスキーマは変えない。値は引き続き `TRUE` / `FALSE` 文字列（移行後は空欄を使わない）。
- **Excel materialize / Power Apps 往復は機能的に不変**：`夜勤スキル一覧.csv` の列構成は不変。セル内容が空欄→`TRUE`/`FALSE` に増えるのみ。
- **HB等、この画面に項目を持たない夜勤対象**：従来どおりエンジン内でスキルから自動判定。本エディタには出さない（変更なし）。

## 5. 現状の仕組み（調査で確定した事実）

- 夜勤可否は2段構え：**(a) 日中スキルのランクから base を派生（B以上＝可）→ (b) CSVの `TRUE`/`FALSE` で上書き**。空欄＝上書きなし（＝base＝自動判定）。
  - 派生: `shift_scheduler/src/loaders/data_loader.py`（`get_bool_override`, 〜L50-82）。空欄→`None`→上書きせず。
- 夜勤フィールドは `night_mr` / `night_cath` / `night_angio` の3つ。**HB は本マスターに項目が存在せず常にスキル派生**。
- 実データ（技師77名・`webapp_data/shift.db` の `ms_night_override`）：約74%が空欄（自動）。
  - 夜勤MR: 可26 / 不可0 / 自動51、夜勤心カテ: 19/1/57、夜勤アンギオ: 13/2/62。
- 関連コード：
  - 保存/CRUD: `webapp/api/masters/crud.py`（〜L287-299）、`routes.py`（`PUT /masters/{id}/night_overrides` 〜L218-224）
  - 検証: `webapp/api/masters/validation.py`（`validate_night_override_state` 〜L128,153-156、許容値 `{TRUE, FALSE, ""}`）
  - materialize: `webapp/api/masters/materialize.py`（〜L109-116、DB→CSV）
  - import: `webapp/api/masters/import_dir.py`（〜L242-253、CSV→DB）
  - フロント: `frontend/src/masters/editors/NightSkillEditor.tsx`（L85 ラベル `{t==='inherit'?'継承':t}`、`TRIS`、`FIELDS`）、`transforms/nightSkill.ts`（`triToWire`/`wireToTri`）、`types.ts`（`Tri`, `NightOverrideRow`）

## 6. 設計詳細

### 6.1 スキルマスタの色分け＋見た目刷新（フロントのみ・安全）

- `SkillMatrixEditor.tsx`：各セル `<td>`（および `<select>`）に選択中ランクを表す `data-rank={value}` を付与。表示文字（A〜D・-）はそのまま残す。
- 新規 `frontend/src/masters/masters.css` に以下を定義し、`MastersPage.tsx` で1回 import：
  - ランク配色（背景／文字）: A `#dcfce7`/`#15803d`、B `#dbeafe`/`#1d4ed8`、C `#fef3c7`/`#b45309`、D `#ffedd5`/`#c2410c`、- `#f1f5f9`/`#94a3b8`。
  - 全体トーン：テーブルヘッダー背景＋下線、`tbody tr:hover`、セル余白、`position: sticky` のヘッダー、`.master-nav` のピル型アクティブ表示（ティール）、`.master-editor` のカード化（白＋微シャドウ）。
  - スコープは `.masters-page` 配下に限定し、ロスター用 `grid.css`/`roster.css` に影響させない。
- データ・型・APIには触れない。`data-testid` は不変。

### 6.2 夜勤スキルの2状態化（フロント）

- `NightSkillEditor.tsx`：三択（`TRUE`/`FALSE`/`inherit`→`継承`）を **二択（夜勤可=`TRUE` / 夜勤不可=`FALSE`）** に変更。
  - `<option>` ラベル: `TRUE`→「夜勤可」、`FALSE`→「夜勤不可」。
  - セル `<td>`（/`<select>`）に `data-night={value}` を付与し、`masters.css` で 🟩可=緑／🟥不可=赤に色分け。
  - 注記文（旧「空欄（inherit）は…」）は新方針に合わせて書き換え。
- `transforms/nightSkill.ts` / `types.ts`：`Tri` から `inherit` を除いた2値モデルへ整理。**ワイヤ値は引き続き `TRUE`/`FALSE`**（`triToWire`/`wireToTri` は2値前提に簡素化）。
- **フロントは派生ロジックを持たない**：バックエンドが常に解決済みの `TRUE`/`FALSE` を返すため（§6.3）、フロントはそれをそのまま描画する。万一空欄が来た場合は安全側（`夜勤不可`相当）でフォールバック表示しつつ、原則バックエンドが空欄を出さない。

### 6.3 一度きりの明示化（バックエンド・移行）＋ 往復耐性

「独立管理」を成立させるため、`night_mr/cath/angio` の空欄を**現在の解決値**で `TRUE`/`FALSE` に確定する。

- **派生の単一ソース化**：解決値は **既存のスキル→夜勤派生ロジックを再利用して算出**する（JS等で再実装しない）。これによりズレを構造的に防ぐ。
- **(A) 既存データの移行（one-time）**：対象マスターセットの `ms_night_override` の空欄セルを解決値で `TRUE`/`FALSE` に置換。
- **(B) 往復耐性（import 時解決）**：`import_dir.py` で夜勤スキルCSVを取り込む際、空欄セルを同一セットのスキルマトリクスから解決して `TRUE`/`FALSE` で格納する。これにより Power Apps/Excel 往復後も2状態モデルが維持される（HBはCSVに無いので無影響）。
- **検証ゲート（cutover）**：移行の前後でスケジューラをフル実行し、出力が**完全一致**することをパリティ／決定性テストで確認してから確定する。
- 派生ロジック（loader の base 算出）は**残す**（HBおよび安全なフォールバックのため。`night_mr/cath/angio` は全上書きされるので実害なし）。
- 検証 `validate_night_override_state` は変更しない（`TRUE`/`FALSE`/`""` を許容のまま。`""` は使わなくなるが後方互換のため許容を維持）。

## 7. 影響を受けるファイル

| ファイル | 変更 |
|---|---|
| `frontend/src/masters/masters.css` | 新規。ランク配色＋全体スタイル |
| `frontend/src/masters/MastersPage.tsx` | `masters.css` を import |
| `frontend/src/masters/editors/SkillMatrixEditor.tsx` | セルに `data-rank` 付与 |
| `frontend/src/masters/editors/NightSkillEditor.tsx` | 三択→二択（夜勤可/不可）＋`data-night`＋注記文 |
| `frontend/src/masters/editors/transforms/nightSkill.ts` | 2値モデルへ簡素化（ワイヤ値は不変） |
| `frontend/src/masters/types.ts` | `Tri` から `inherit` を除去 |
| `webapp/api/masters/import_dir.py` | import時に空欄→解決値で格納（往復耐性） |
| バックエンド移行（one-time） | 既存 `ms_night_override` の空欄を解決値で確定（スクリプト/管理処理） |
| テスト | フロントの inherit 系テスト（約4件）を2値前提に書き換え。夜勤CSV内容をスナップショットする正解データがあれば再生成。パリティ/決定性テストは不変で通ること。 |

## 8. テスト方針

- **パリティ/決定性（最重要）**：移行後にスケジュール出力が移行前と完全一致。既存テストでガード。
- **バックエンド**：`tests/test_master_write_endpoints.py` の夜勤往復テストは `TRUE`/`FALSE` 保存・CSV反映・loader解釈を引き続き検証（空欄ケースは独立管理方針に合わせ調整）。import時解決の新規テストを追加。
- **フロント（vitest）**：`NightSkillEditor.test.tsx` を二択前提に書き換え。表示テキストで選択しているテストは新ラベル（夜勤可/夜勤不可）へ更新。スキルマスタは色（CSS）追加のみで `data-testid` 不変＝既存テストは原則影響なし。
- **ビルド**：`frontend` の本番ビルドが通ること。

## 9. 残リスクと対処

- **解決値のズレ**：派生を再実装せず既存ロジックを再利用＋パリティゲートで担保。
- **往復で自動が再混入**：import時解決（§6.3-B）で防止。
- **移行対象セットの取り違え**：移行は明示的に対象セットを指定し、実行前後でパリティ確認。

## 10. ロールアウト順序（実装計画の素案）

1. スキルマスタ色分け＋`masters.css`（独立・安全）。フロントビルド／既存テスト確認。
2. 派生再利用ユーティリティの確認（既存ロジックの再利用点を特定）。
3. import時解決（§6.3-B）＋テスト。
4. 既存データ移行（§6.3-A）＋**パリティ/決定性ゲート**で出力一致を確認。
5. 夜勤スキル二択UI＋`data-night`色分け＋transforms/types整理。フロントテスト書き換え。
6. 全テスト（バック＋フロント）＋本番ビルド＋実APIでの目視確認。

## 11. 実装メモ（確定）

§6.3 では当初バックエンドGETでの解決＋一度きり移行を想定したが、検証の結果
**バックエンド無改造・フロント側解決**に変更した（より安全）。理由と最終形:

- バックエンドGETで空欄を解決すると、API往復（GET→PUT→materialize）で
  `夜勤スキル一覧.csv` がバイト単位で変化し、必須制約「Excel/Power Apps 完全一致」
  を破る（`test_noop_put_roundtrip_is_byte_identical` が検知）。
- そこで **解決は表示層（フロント）で実施**。バックエンド（crud/routes/materialize/
  loader）は一切変更しない＝往復のバイト同一性とスケジューラ出力を完全維持。
- フロント `NightSkillEditor.tsx`:
  - `useSkillMatrix` を併用し、空欄セルを `data_loader.py:38-44` と同一規則で
    `TRUE`/`FALSE` に解決して2状態表示（MR=max(病院MR,CLMR)≥B / angio=ア≥B / cath=心≥B）。
  - 保存(PUT)で全セルを明示値 `TRUE`/`FALSE` として書き込み＝以後は日中スキルと独立（①）。
  - `data-night` で 🟩可/🟥不可 を色分け（`masters.css`）。
- 別途の移行スクリプト・import時解決は不要化（保存で確定するため）。GET/PUTの生値仕様は不変。
- 検証: frontend 124 / backend(master write) 16 すべて合格。コミット 078fc21（視覚刷新）・062763e（夜勤2状態）。

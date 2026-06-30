# 勤務表 Web アプリ — 運用者・開発者ガイド

放射線技師の勤務表を作成する院内 Web アプリ（v1）の運用・開発ドキュメントです。
設計の詳細は [設計書](../superpowers/specs/2026-06-29-web-app-shift-scheduler-design.md) を参照してください。

---

## 1. 概要

- ローカル CLI（`python main.py --year 2026 --month 6`）で動いていた既存ツールを、**院内サーバー設置の Web アプリ**にしたものです。
- **絶対要件＝設定とロジックの引き継ぎ**：同じ入力なら、Web 版が出す**配置データ（各技師×各日の配置・公休/代休・集計値）は現行 CLI と完全一致**します。マスタは SQLite に保持しつつ、生成時に**バイト等価の CSV 群**へ書き戻し（materialize）、**無改造の既存スケジューラ**で解きます。決定性（`seed=42` / `num_workers=1` / 決定論的時間停止）は一切変更していません。
- **既存 CLI はそのまま動きます**（`main.py` は薄いラッパーになり、ロジックは共有）。Excel の**見た目だけ**は方向 A で刷新（配置データは一致）。
- データは**院内 LAN から外に出しません**（外部公開しない前提）。

---

## 2. 主な機能

- **勤務表の生成**：年月を指定してジョブ投入 → バックグラウンドで `run_schedule()` を実行 → 進捗ポーリング → 結果表示。生成は 1 ワーカーで直列実行（決定性とCPU保護）。
- **手修正グリッド**：セル編集／ドラッグ＆ドロップ（人↔場所・日↔日）／**Undo・Redo**。編集対象は表示文字ではなく内部の割り当てモデルで、保存後に**サーバー側が表示文字を再導出**して返します。
- **リアルタイム警告**（編集のたびにサーバーで再計算）：
  - **勤務不足の場所**（必要人数 vs 実配置）
  - **公休数が目標未満の人**（公休/代休を割り当てから再計算）
  - **連続勤務**（連勤ウィンドウ検出）
  - **夜勤 HB ギャップ**（夜勤スキルのカバレッジ）
- **部分ロック → 再生成**：`locked=1` のセルを固定したまま残りだけ解き直す（`POST /rosters/{rid}/resolve`）。構造的に不可能なロックは 422 で該当セルを返します。
- **方向 A の Excel 出力**：凍結済みの割り当て（手修正反映後）から再計算せずに新レイアウトで生成。タイトル幅は当月日数に追従、2 段ヘッダ・固定ペイン・集計/凡例シート・印刷設定。
- **全マスタの CRUD（8 マスタ）＋ 予定申請の取り込み**：技師・スキル・勤務場所(＋パワーバランス)・特殊配置ルール・業務拡大・夜勤回数・夜勤スキル(上書き)・公休数を Web 編集。**予定申請（Power Apps 出力）は取り込み専用**（アップロード → 検証 → プレビュー → 確定）。
- **認証（admin / editor / viewer）＋ 確定ロック ＋ 月別アーカイブ ＋ バックアップ**：確定でその月の Excel バイトを `archives` に保存（viewer は確定版のみ閲覧/DL）。日次バックアップで DB と確定 xlsx を取り出し。

---

## 3. アーキテクチャ

```
[ React / TypeScript (ブラウザ) ]      勤務表グリッド / マスタ編集 / ログイン
        │  HTTP(JSON) + httpOnly セッション Cookie（同一オリジン → CORS 無し）
        ▼
[ FastAPI (webapp/api) ]               REST API + ジョブ投入 + 認証 + 確定/アーカイブ
        │   ・既存 shift_scheduler/ を無改造で import
        │   ・SPA(frontend/dist) も同一プロセスで静的配信（本番）
        ▼
[ SQLite ]   users / master_set / 各マスタ / requests_import /
             jobs / rosters / roster_assignments / roster_meta /
             roster_edits / archives
```

- **設定引き継ぎの肝（materialize → solve → freeze → render）**：
  1. **materialize**：選択した `master_set` ＋ 当月の予定申請を、現行とバイト等価の CSV 群としてテンポラリ `data_dir` に書き出す（utf-8-sig の有無、勤務場所の 2 表構造、夜勤回数のタイトル/footer、予定申請の月サフィックスを厳密再現）。
  2. **solve**：`run_schedule(year, month, data_dir, ...)` を**無改造**で実行。
  3. **freeze**：割り当て・`off_counts`・`daikyu_counts` を `roster_assignments` / `roster_meta` に凍結保存。
  4. **render**：Excel DL は**再計算せず**、凍結割り当て（手修正後）を方向 A レンダラに渡して生成。
- 本番は**1 つの uvicorn プロセス**が SPA と API を**同一オリジン**で配信（`webapp/api/static.py:mount_spa`）。API 名前空間（`/health /auth /jobs /rosters /masters /master-sets /archives`）に当たらない GET は SPA の `index.html` を返します。

---

## 4. 開発環境での起動

2 プロセス（API ＋ Vite dev）で動かします。

```bash
# 1) API（リポジトリ直下）
source .venv/bin/activate
pip install -r webapp/requirements.txt
python -m uvicorn webapp.api.main:app --reload --port 8000

# 2) フロント（別ターミナル）
cd frontend
npm install
npm run dev            # http://localhost:5173 （Vite が :8000 へプロキシ）
```

- Vite dev は `/jobs /rosters /masters /master-sets` を `:8000` にプロキシします（`frontend/vite.config.ts`）。`VITE_API_BASE` は**空のまま**（同一オリジン）。
- データは `SHIFT_DATA_DIR`（既定 `shift_scheduler/data`）、DB は `SHIFT_DB_PATH`（既定 `webapp_data/shift.db`）。
- **使い方の例**：
  1. master_set と roster をシード（`master_set` が無い場合は生成が on-disk の `data_dir` にフォールバック）。
  2. `POST /jobs` `{"year":2026,"month":6}` → `GET /jobs/{id}` が `done` になるまでポーリング → `POST /jobs/{id}/freeze` で roster 化。
  3. ブラウザで **`http://localhost:5173/?rid=<roster_id>`**（編集グリッド）、**`http://localhost:5173/?view=masters`**（マスタ管理）を開く。
  - ルートはパスではなく**クエリ**（`?rid=` / `?view=masters`）で切替（`/rosters/...` は API 名前空間なので SPA を読めないため）。

### テスト

```bash
python -m pytest -m "not slow"        # 高速（モック）
python -m pytest -m slow              # 実ソルバー（数分）：抽出・決定性・データ一致
cd frontend && npx vitest run         # フロント単体
cd frontend && npx playwright test    # E2E（シード済み roster に対する操作）
```

---

## 5. 本番（Windows）での起動

`deploy/` のスクリプトを順に実行します。詳細は [deploy/README.md](../../deploy/README.md) と [deploy/install_service.md](../../deploy/install_service.md)。

1. **フロントをビルド**：`deploy\build_frontend.bat` → `frontend\dist` が生成（`VITE_API_BASE` は空＝同一オリジン）。
2. **環境変数を設定**（`start.bat` 内、または NSSM の `AppEnvironmentExtra`）：
   - `SHIFT_DB_PATH`（例 `C:\shift\data\shift.db`）
   - `SHIFT_FRONTEND_DIST`（`...\frontend\dist`）
   - 初回 `SHIFT_ADMIN_ID` / `SHIFT_ADMIN_PW`（8 文字以上）
   - 任意 `SHIFT_AUTH_SECRET`（未設定なら `webapp_data\.auth_secret` を自動生成）
3. **起動**：`deploy\start.bat` → venv 作成・依存インストール・**管理者ブートストラップ（冪等）**・`uvicorn webapp.api.main:app --host 0.0.0.0 --port 8000`。
4. **Windows ファイアウォール（最重要）**：TCP **8000** の受信を **LAN サブネット限定**で許可。`--host 0.0.0.0` は全インターフェースにバインドするだけで、**アクセス範囲を絞るのはファイアウォール**。外部公開しない。
5. **サービス化（NSSM 推奨）**：`nssm install ShiftScheduler ...`（`AppDirectory` / `AppEnvironmentExtra` / `AppStdout` / `AppStderr` / `Start=SERVICE_AUTO_START`）。代替はタスクスケジューラの「コンピューター起動時」トリガー。
6. **日次バックアップ**：`deploy\backup.bat` をタスクスケジューラで毎日実行（SQLite オンラインバックアップ＋確定月 xlsx＋`manifest.json`）。

- 本番は**単一プロセス・同一オリジン**（dev==prod、**CORS 無し**）。Docker Compose（`deploy/docker-compose.yml`）は任意の代替。
- 利用者は `http://<ホスト名 or IP>:8000/` にアクセス。初回 admin で**ログイン後に必ずパスワードを変更**し、admin が editor/viewer を作成（`/auth/users`）。

---

## 6. 役割と権限（v1 = ローカルアカウント）

| ロール | できること |
|---|---|
| **admin** | 生成（`POST /jobs`）・**全マスタ編集**・**確定（confirm）**・ユーザー管理（`/auth/users`） |
| **editor** | ロスター手修正・Undo/Redo・部分ロック再生成・マスタ**閲覧**・ドラフト含む読み取り |
| **viewer** | **確定済み月のアーカイブ閲覧/DL のみ**（ドラフトは見えない） |

- パスワードは `hashlib.pbkdf2_hmac`（ユーザー毎 salt、最小 8 文字）。セッションは HMAC 署名トークンを httpOnly / SameSite=Strict の `session` Cookie で配信（CLI/テスト用に Bearer も可）。TTL は既定 12 時間。
- マスタ名前空間は 1 つの method-aware ガード：読み取り(GET)＝admin|editor、書き込み(POST/PUT/DELETE)＝admin（`masters/routes.py:masters_guard`）。

---

## 7. API 概要

| 領域 | 主なエンドポイント | 権限 |
|---|---|---|
| 認証 | `POST /auth/login` `POST /auth/logout` `GET /auth/me`、`GET/POST/PUT /auth/users` | login は公開／users は admin |
| 生成ジョブ | `POST /jobs`、`GET /jobs/{id}`、`GET /jobs/{id}/result`、`GET /jobs/{id}/excel`、`POST /jobs/{id}/freeze` | POST /jobs=admin、他=admin\|editor |
| ロスター | `GET /rosters/{rid}`(+`/grid`)、`POST .../edits`・`/undo`・`/redo`・`/resolve`、`GET .../excel` | admin\|editor |
| マスタ | `GET/POST/PUT/DELETE /masters/{set_id}/...`（staff/skill/location_set/special_rules/training/night_quota/night_overrides/holiday_targets）、`/clone`、`/safety-check` | GET=admin\|editor、書込=admin |
| マスタ集合 | `GET /master-sets` | admin\|editor |
| 予定申請 | `POST /masters/requests/preview`、`POST /masters/requests/{year}/{month}` | admin |
| 確定/履歴 | `POST /rosters/{rid}/confirm`、`GET /archives`、`GET /archives/{id}/excel` | confirm=admin、archives=admin\|editor\|viewer |
| ヘルス | `GET /health` | 公開 |

- 楽観ロック：編集は `expected_version` を送り、不一致は **409** で現在のグリッドを返す（クライアントがリベース）。
- 部分ロック再生成：ロックが構造的不可能/ハード制約衝突なら **422** で該当セルを返す。
- 非 ASCII ファイル名は RFC 5987（`filename*=UTF-8''...`）でエンコードして配信。

---

## 8. 運用者（院内 IT）が決める項目

設計書 §13 のチェックリスト（[deploy/README.md](../../deploy/README.md) に詳細）：

- **設置マシン / 固定ホスト名・IP / ポート**（既定 8000）と、利用者がアクセスする URL。
- **ファイアウォール**：TCP 8000 を LAN サブネット限定で許可（外部公開しない）。
- **バックアップ媒体・頻度・保持世代**（ネットワーク共有 or 外付け、IT と合意）。
- **AD / SSO の要否**：v1 は**ローカルアカウント**（`service.authenticate()` が将来の差し込み口）。
- **初回 admin パスワードの変更**と資格情報の保管者。
- **TLS**：v1 は院内 LAN の**平文 HTTP** 前提（Cookie に `Secure` を付けない）。IT が TLS を提供できる場合は `session` Cookie に `Secure` を付与し `SameSite=Strict` を維持。
- 電源/常時起動（スリープ無効・自動起動）、OS アップデート時の再起動方針。

---

## 9. 既知の残課題

- **致命的なものは無し**。`set_symbol`（申請記号の設定/クリア、Undo 可能）は配線済み、E2E はグリーン。
- スキル/パワーバランス違反の警告はバックエンドで `skill: []` のプレースホルダ（編集 API の `_warnings_payload`）。マスタ参照を伴う本実装は後続。
- 多病院対応（コード固定の技師 ID・場所コード・日本暦などの外出し）は v1 スコープ外（設計書 §3.5）。安全装置として、生成前に固定 ID の存在を `safety-check` で検証し、欠ければ**生成ジョブを失敗**させます。

---

## 10. テスト（現状: 緑）

| 種別 | コマンド | 件数 |
|---|---|---|
| バックエンド（高速） | `python -m pytest -m "not slow"` | 194 |
| バックエンド（実ソルバー） | `python -m pytest -m slow` | 抽出・決定性・データ一致 |
| フロント単体 | `cd frontend && npx vitest run` | 123 |
| E2E | `cd frontend && npx playwright test` | 5 |

`-m slow` は実ソルバーを回すため数分かかります（抽出の等価性・決定性・現行 CLI とのデータ一致を検証）。

---

## 11. 関連ドキュメント

- 設計書：[`docs/superpowers/specs/2026-06-29-web-app-shift-scheduler-design.md`](../superpowers/specs/2026-06-29-web-app-shift-scheduler-design.md)
- 本番デプロイ：[`deploy/README.md`](../../deploy/README.md) ／ サービス登録：[`deploy/install_service.md`](../../deploy/install_service.md)
- API クイック確認：[`webapp/README.md`](../../webapp/README.md)
- 実装計画（フェーズ別 P1..P4）：
  - P1 基盤＋Excel データ一致ゲート：[`...p1-foundation.md`](../superpowers/plans/2026-06-29-web-app-p1-foundation.md)
  - P2a-1 抽出（build_grid + recompute_stats）：[`...p2a1-extractions.md`](../superpowers/plans/2026-06-29-web-app-p2a1-extractions.md)
  - P2a-2 編集バックエンド：[`...p2a2-edit-backend.md`](../superpowers/plans/2026-06-29-web-app-p2a2-edit-backend.md)
  - P2b 部分ロック再生成：[`...p2b-lock-resolve.md`](../superpowers/plans/2026-06-29-web-app-p2b-lock-resolve.md)
  - P2c 方向 A Excel：[`...p2c-excel-directiona.md`](../superpowers/plans/2026-06-29-web-app-p2c-excel-directiona.md)
  - P2d React エディタ：[`...p2d-react.md`](../superpowers/plans/2026-06-29-web-app-p2d-react.md)
  - P3a マスタ管理（SQLite）：[`...p3-master-management.md`](../superpowers/plans/2026-06-29-web-app-p3-master-management.md)
  - P3b React マスタ UI：[`...p3b-react-master-ui.md`](../superpowers/plans/2026-06-30-web-app-p3b-react-master-ui.md)
  - P4 本番配信＋認証＋確定/アーカイブ＋Windows デプロイ：[`...p4-auth-deploy.md`](../superpowers/plans/2026-06-30-web-app-p4-auth-deploy.md)

# 勤務表システム — Windows 本番デプロイ

## アーキテクチャ（1行）
**1 つの Python(uvicorn) プロセス**が、ビルド済み SPA(`frontend/dist`) と JSON API
(`/jobs` `/rosters` `/masters` `/master-sets` `/auth` `/archives`) を**同一オリジン**で配信する。
データは **SQLite ファイル DB** 1 つ。**院内 LAN 限定**（外部公開しない）。Docker は任意。

```
ブラウザ(LAN) ──► http://<ホスト>:8000/ ──► uvicorn(webapp.api.main:app)
                                            ├─ /            -> frontend/dist/index.html (SPA)
                                            ├─ /assets/*    -> 静的配信
                                            └─ /jobs /rosters /masters /auth /archives -> JSON API
                                            └─ SQLite: C:\shift\data\shift.db  (+ users / archives)
```

## 設置場所（IT と調整・例）
| 用途 | パス（例） |
|---|---|
| アプリ（リポジトリ） | `C:\shift\app\` |
| DB + 認証秘密鍵 | `C:\shift\data\`（`shift.db` / `.auth_secret`） |
| ログ | `C:\shift\logs\` |
| バックアップ先 | ネットワーク共有 or 外付けドライブ（**IT と合意**） |

## 固定ホスト / ポート
- バインド: `0.0.0.0:8000`（設置 PC）。利用者は `http://<ホスト名 or IP>:8000/` でアクセス。
- **ホスト名 / IP / ポートは IT が確定**（既定ポート 8000）。

## Windows ファイアウォール（最重要）
- TCP **8000** の受信規則を **LAN サブネットのみ**（スコープ = ローカルサブネット / 臨床 VLAN）で許可。
- `--host 0.0.0.0` は全インターフェースにバインドするだけで、**アクセス範囲を絞るのはファイアウォール**。
- **外部公開しない**（spec §13）。

## 初回セットアップ手順
1. `deploy\build_frontend.bat` を実行 → `frontend\dist` が生成される（`VITE_API_BASE` は空＝同一オリジン）。
2. 環境変数を設定（`start.bat` 内、または NSSM の AppEnvironmentExtra）：
   `SHIFT_DB_PATH` / `SHIFT_FRONTEND_DIST` / 初回 `SHIFT_ADMIN_ID` `SHIFT_ADMIN_PW`(8 文字以上)。
3. `deploy\start.bat` を実行 → venv 作成・依存インストール・**管理者ブートストラップ（冪等）**・uvicorn 起動。
4. ブラウザでログイン（初回 admin）。**ログイン後に管理者パスワードを変更**。
5. admin が editor / viewer ユーザーを作成（`/auth/users`）。

> 常時稼働サービス化は `deploy\install_service.md`（NSSM 推奨 / タスクスケジューラ代替）。

## 認証・ロール（v1 = ローカルアカウント）
| ロール | できること |
|---|---|
| **admin** | 生成(`POST /jobs`)・マスタ編集・**確定(confirm)**・ユーザー管理 |
| **editor** | ロスター手修正・再ソルブ・読み取り（確定前ドラフト含む） |
| **viewer** | **確定済み月のアーカイブ閲覧/DL のみ**（ドラフトは見えない） |

- パスワードは `hashlib.pbkdf2_hmac`（ユーザー毎 salt）。セッションは HMAC 署名トークンを
  httpOnly / SameSite=Strict の `session` Cookie で配信（CLI/テスト用に Bearer も可）。
- 秘密鍵は `SHIFT_AUTH_SECRET` 環境変数、未設定なら `webapp_data\.auth_secret` を自動生成。
  鍵の入れ替えで全セッションが無効化される。TTL は 12 時間（既定）。

## バックアップ
- `deploy\backup.bat` を**毎日**タスクスケジューラで実行（SQLite オンラインバックアップ + 確定月 xlsx 取り出し + `manifest.json`）。
- 稼働中でも整合コピー可能。復旧時は `manifest.json` のチェックサムを検証。

## 更新（アップデート）手順
1. サービス停止（`net stop ShiftScheduler`）。
2. コード更新（`git pull` またはビルド成果物のコピー）。
3. `deploy\build_frontend.bat` 再実行。
4. サービス再起動（`net start ShiftScheduler`）。

## TLS について（決定事項）
v1 は院内 LAN の**平文 HTTP**前提（Cookie に `Secure` は付与しない）。IT が TLS を提供できる場合
（リバースプロキシ / 端末に信頼させた自己署名証明書）は `session` Cookie に `Secure` を付与し
`SameSite=Strict` を維持すること。

---

## §13 院内 IT 調整チェックリスト（spec §13）
- [ ] **設置場所**（常時起動 PC / サーバー 1 台、例 `C:\shift\`）
- [ ] **固定ホスト名 / IP**（利用者がアクセスする URL を確定）
- [ ] **ポート**（既定 8000）
- [ ] **ファイアウォール**: TCP 8000 を **LAN サブネット限定**で許可（外部公開しない）
- [ ] **バックアップ媒体・頻度**（ネットワーク共有 / 外付け、保持世代）
- [ ] **電源 / 常時起動**（スリープ無効、再起動後の自動起動）
- [ ] **OS アップデート方針**（再起動タイミングの調整）
- [ ] **管理者資格情報の保管者**（初回 admin の引き継ぎ）
- [ ] **データは LAN 内に留まる**ことの確認（外部送信なし）

## 運用上の決定（このフェーズで採用済みの既定）
- 認証 = **ローカルアカウント**（AD/SSO は将来フェーズ。`authenticate()` が差し込み口）。
- セッション = **httpOnly Cookie**（+ Bearer フォールバック）、TTL 12h、失効時は再ログイン。
- 秘密鍵 = `webapp_data\.auth_secret` ファイル（自動生成）or `SHIFT_AUTH_SECRET`。
- パスワード最小長 = 8。初回 admin はブートストラップが空/短パスワードを**明確に拒否**。
- 配信 = **同一プロセス・同一オリジン**（dev==prod、CORS なし）。Docker Compose は任意の代替。

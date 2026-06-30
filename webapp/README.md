# 勤務表 Web API (P1 backend foundation)

## セットアップ
```bash
source .venv/bin/activate
pip install -r webapp/requirements.txt
```

## 起動
```bash
uvicorn webapp.api.main:app --reload --port 8000
```

## 使い方（手動確認）
1. `POST http://localhost:8000/jobs`  body: `{"year":2026,"month":6}` → `{"id":"...","status":"queued"}`
2. `GET http://localhost:8000/jobs/{id}` → `status` が `done` になるまでポーリング（実ソルバーで数分）
3. `GET http://localhost:8000/jobs/{id}/result` → 配置 JSON
4. `GET http://localhost:8000/jobs/{id}/excel` → 現行レイアウトの .xlsx ダウンロード

データは環境変数 `SHIFT_DATA_DIR`（既定 `shift_scheduler/data`）から読む。
P1 はマスタを CSV のまま使い、認証・手修正・新レイアウトは後続フェーズ。

## 本番ビルド（同一オリジン配信 / P4a）
開発は Vite プロキシ、本番は **1 つの uvicorn プロセス**が SPA と API を同時配信する（dev==prod、CORS なし）。

```bash
# 1. フロントをビルド -> frontend/dist が生成される
cd frontend && npm run build        # VITE_API_BASE は空のまま（同一オリジン）

# 2. ビルド成果物を指してサーバ起動（--reload なし）
cd ..
SHIFT_FRONTEND_DIST="$PWD/frontend/dist" \
  python -m uvicorn webapp.api.main:app --host 0.0.0.0 --port 8000
```

- `GET /` と任意のクライアントルートは `index.html`、`/assets/*` は静的配信、
  `/health` `/jobs` `/rosters` `/masters` `/master-sets` `/auth` `/archives` は JSON API。
- `SHIFT_FRONTEND_DIST` を設定しなければ従来どおり API のみ（Vite が SPA を配信）。
- Windows 本番手順は `deploy/README.md` を参照。

## テスト
```bash
python -m pytest -m "not slow" -v   # 高速（モック）
python -m pytest -m slow -v         # 実ソルバー（数分）：抽出・決定性・パリティ
```

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

## テスト
```bash
python -m pytest -m "not slow" -v   # 高速（モック）
python -m pytest -m slow -v         # 実ソルバー（数分）：抽出・決定性・パリティ
```

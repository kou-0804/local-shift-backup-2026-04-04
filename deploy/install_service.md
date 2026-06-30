# Windows サービス登録 (NSSM)

`start.bat` を手動で起動する代わりに、常時稼働サービスとして登録する手順。
推奨は **NSSM** (the Non-Sucking Service Manager)。Docker より軽量で、
病院 IT の標準的な Windows 運用に馴染む。

## 1. NSSM の取得
<https://nssm.cc/> から `nssm.exe` を入手し、例として `C:\shift\nssm.exe` に置く。

## 2. サービス作成
管理者権限の cmd で:

```bat
C:\shift\nssm.exe install ShiftScheduler ^
  "C:\shift\app\.venv\Scripts\python.exe" ^
  "-m uvicorn webapp.api.main:app --host 0.0.0.0 --port 8000"

REM 作業ディレクトリ（リポジトリ直下）
C:\shift\nssm.exe set ShiftScheduler AppDirectory "C:\shift\app"

REM 環境変数（固定パス / フロント dist / 初回管理者）
C:\shift\nssm.exe set ShiftScheduler AppEnvironmentExtra ^
  SHIFT_DB_PATH=C:\shift\data\shift.db ^
  SHIFT_FRONTEND_DIST=C:\shift\app\frontend\dist ^
  SHIFT_ADMIN_ID=admin ^
  SHIFT_ADMIN_PW=changeme123

REM ログ（標準出力 / エラー）
C:\shift\nssm.exe set ShiftScheduler AppStdout "C:\shift\logs\app.out.log"
C:\shift\nssm.exe set ShiftScheduler AppStderr "C:\shift\logs\app.err.log"

REM 自動起動
C:\shift\nssm.exe set ShiftScheduler Start SERVICE_AUTO_START
```

> 初回起動前に一度 `deploy\start.bat` を実行して venv 作成・依存インストール・
> 管理者ブートストラップを済ませておくと確実（サービスは uvicorn 起動のみ担う）。

## 3. 起動 / 停止 / 削除
```bat
net start ShiftScheduler
net stop  ShiftScheduler
C:\shift\nssm.exe remove ShiftScheduler confirm
```

## 代替: タスクスケジューラ
NSSM を使わない場合、「コンピューター起動時」トリガーで `deploy\start.bat` を
実行するタスクを「最上位の特権で実行」設定で登録してもよい（ログイン不要）。

## バックアップの自動化
`deploy\backup.bat` を **毎日** タスクスケジューラで実行し、`manifest.json` の
チェックサムを定期的に検証すること（バックアップ先は IT と合意した媒体）。

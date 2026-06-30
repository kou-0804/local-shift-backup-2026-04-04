@echo off
REM === 勤務表システム 本番起動 (単一プロセスで SPA + API を配信) ===
REM venv 作成 -> 依存インストール -> 管理者ブートストラップ -> LAN 向け uvicorn。
REM --host 0.0.0.0 は全インターフェースにバインドするため、アクセス範囲は
REM Windows ファイアウォール(LAN サブネット限定)で絞ること。詳細は deploy\README.md。
setlocal
cd /d %~dp0\..

REM --- 固定パス / 初期認証情報 (IT と調整) -----------------------------
if "%SHIFT_DB_PATH%"=="" set SHIFT_DB_PATH=C:\shift\data\shift.db
set SHIFT_FRONTEND_DIST=%CD%\frontend\dist
REM 任意: 秘密鍵を固定。未設定なら webapp_data\.auth_secret を自動生成。
REM set SHIFT_AUTH_SECRET=長いランダム文字列に変更すること
REM 初回起動時の管理者(ログイン後にパスワード変更すること):
if "%SHIFT_ADMIN_ID%"=="" set SHIFT_ADMIN_ID=admin
if "%SHIFT_ADMIN_PW%"=="" set SHIFT_ADMIN_PW=changeme123

REM --- venv -------------------------------------------------------------
if not exist .venv ( py -3 -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r webapp\requirements.txt
if errorlevel 1 ( echo PIP INSTALL FAILED & exit /b 1 )

REM --- 初回管理者ブートストラップ (冪等) -------------------------------
python -m webapp.api.auth.bootstrap
if errorlevel 1 ( echo ADMIN BOOTSTRAP FAILED ^(set SHIFT_ADMIN_PW ^>=8 chars^) & exit /b 1 )

REM --- 起動 (LAN 向け; --reload なしの単一決定的プロセス) --------------
python -m uvicorn webapp.api.main:app --host 0.0.0.0 --port 8000
endlocal

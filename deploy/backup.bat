@echo off
REM === 勤務表システム 日次バックアップ (Windows Task Scheduler 用) ===
REM SQLite オンラインバックアップで DB を整合コピーし、確定済み月の xlsx を
REM 取り出して manifest.json を書き出す。サーバ稼働中でも安全。
REM
REM 使い方: deploy\backup.bat   （バックアップ先は下の SET で IT と調整）

setlocal
cd /d %~dp0\..

REM --- 環境設定（IT が調整） ---------------------------------------------
if "%SHIFT_DB_PATH%"=="" set SHIFT_DB_PATH=C:\shift\data\shift.db
REM バックアップ先（ネットワーク共有 or 外付けドライブ）。タイムスタンプ付き。
set BACKUP_ROOT=D:\shift-backup
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set STAMP=%DT:~0,8%T%DT:~8,6%
set TARGET=%BACKUP_ROOT%\%STAMP%

call .venv\Scripts\activate.bat
python deploy\backup.py --db "%SHIFT_DB_PATH%" --target "%TARGET%"
if errorlevel 1 (
  echo BACKUP FAILED
  exit /b 1
)
echo backup written to %TARGET%
endlocal

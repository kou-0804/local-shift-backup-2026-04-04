@echo off
REM === 勤務表システム 現地更新 (Mac で push した変更を Windows へ反映) ===
REM 流れ: サービス停止 -> git pull -> フロント再ビルド -> 依存更新 -> サービス再起動。
REM 使い方: 管理者権限の cmd で deploy\update.bat を実行（NSSM でサービス登録済み前提）。
REM 先に Mac 側で `git push` しておくこと。取得ブランチはこの PC で現在チェックアウト中のもの。
setlocal
cd /d %~dp0\..

set SERVICE=ShiftScheduler

echo [1/4] サービス停止...
net stop %SERVICE%

echo [2/4] コード取得 (git pull)...
git pull
if errorlevel 1 ( echo *** GIT PULL FAILED - 旧コードのまま再起動します *** & goto :restart )

echo [3/4] フロントエンド再ビルド...
call deploy\build_frontend.bat
if errorlevel 1 ( echo *** FRONTEND BUILD FAILED - 旧 dist のまま再起動します *** & goto :restart )

echo [3b/4] 依存を更新 (冪等)...
call .venv\Scripts\activate.bat
python -m pip install -r webapp\requirements.txt

:restart
echo [4/4] サービス再起動...
net start %SERVICE%
echo.
echo === 完了 ===
echo ブラウザで http://（このPCのIP または ホスト名）:8000/ を再読み込みして確認してください。
endlocal

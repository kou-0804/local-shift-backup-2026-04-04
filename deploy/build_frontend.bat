@echo off
REM === フロントエンド本番ビルド (同一オリジン配信) ===
REM VITE_API_BASE は空のまま（dev==prod、CORS なし）。出力は frontend\dist。
setlocal
cd /d %~dp0\..\frontend

set VITE_API_BASE=
call npm ci
if errorlevel 1 ( echo NPM CI FAILED & exit /b 1 )
call npm run build
if errorlevel 1 ( echo FRONTEND BUILD FAILED & exit /b 1 )

echo.
echo Built frontend\dist
echo Set SHIFT_FRONTEND_DIST to:
echo   %~dp0..\frontend\dist
endlocal

@echo off
title RaipurNetra AI - Public Website Launcher
echo ==========================================================
echo   RaipurNetra AI - starting public website
echo   (keep this window and the server window open)
echo ==========================================================
cd /d "%~dp0"

set PY=C:\Users\princ\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python

echo [1/3] Starting server...
start "RaipurNetra Server" cmd /c "%PY% -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo [2/3] Opening public Cloudflare tunnel...
start "RaipurNetra Tunnel" /min cmd /c "cloudflared.exe tunnel --url http://127.0.0.1:8000 --no-autoupdate > tunnel.log 2>&1"

echo [3/3] Waiting for public URL...
ping -n 14 127.0.0.1 >nul

set URL=
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-Content tunnel.log -Raw | Select-String -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches).Matches[0].Value"') do set URL=%%i

if "%URL%"=="" (
    echo Could not read the tunnel URL - check tunnel.log
) else (
    echo ==========================================================
    echo   PUBLIC WEBSITE:  %URL%
    echo ==========================================================
    echo   Share this link anywhere. It works while this PC
    echo   is on and the server/tunnel windows are open.
    echo   (A new link is generated each time you run this.)
    start "" %URL%
)
pause

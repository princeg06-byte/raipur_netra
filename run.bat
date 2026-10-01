@echo off
title RaipurNetra AI - The Intelligent Eye of Raipur
echo ============================================
echo   RaipurNetra AI - Starting demo server
echo   Open http://localhost:8000 in your browser
echo ============================================
cd /d "%~dp0"
set PY=C:\Users\princ\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python
start "" http://localhost:8000
"%PY%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause

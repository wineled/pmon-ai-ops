@echo off
chcp 65001 >nul
title PMON-AI-OPS Backend

echo [PMON] Starting backend on port 8000...

REM Ensure tftp_receive directory exists
if not exist "tftp_receive" mkdir "tftp_receive"

REM Start uvicorn
python -X utf8 -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level debug

pause

@echo off
REM ── WhatsApp AI Demo — Quick Start ──
echo ============================================
echo   WhatsApp AI Demo — Exhibition Mode
echo ============================================
echo.

REM Use port 5050 to avoid conflict with thursday-web (5000)
cd /d "%~dp0"
python main.py

pause

@echo off
REM ── Start ngrok tunnel for WhatsApp Demo ──
echo Starting ngrok tunnel on port 5050...
echo.
echo After it starts, copy the https:// URL and paste into Twilio:
echo   https://YOUR-URL.ngrok-free.app/whatsapp
echo.
ngrok http 5050
pause

@echo off
REM ── Optimised llama-server launch for Thursday ──
REM Reads MODEL_PATH and SERVER_PATH from .env if present.

REM Load .env values
FOR /F "usebackq tokens=1,* delims==" %%A IN (".env") DO (
    SET "%%A=%%B"
)

REM Defaults if not set in .env
IF NOT DEFINED MODEL_PATH  SET MODEL_PATH=llama.cpp\models\meta-llama-3-8b-instruct.Q4_K_M.gguf
IF NOT DEFINED SERVER_PATH SET SERVER_PATH=llama.cpp\build\bin\Release\llama-server.exe
IF NOT DEFINED LLAMA_HOST  SET LLAMA_HOST=127.0.0.1
IF NOT DEFINED LLAMA_PORT  SET LLAMA_PORT=8080

echo Starting llama-server...
echo   Model:  %MODEL_PATH%
echo   Server: %SERVER_PATH%
echo   Listen: %LLAMA_HOST%:%LLAMA_PORT%
echo.

"%SERVER_PATH%" ^
  -m "%MODEL_PATH%" ^
  -ngl 99 ^
  -c 2048 ^
  -b 512 ^
  -ub 128 ^
  -t 16 ^
  -fa on ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --host %LLAMA_HOST% ^
  --port %LLAMA_PORT%

pause

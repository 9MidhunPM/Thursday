@echo off
REM ── Optimised llama-server launch for Thursday ──
REM Update MODEL_PATH to your actual .gguf file location

SET MODEL_PATH=D:\Codaing\ThursdayV2\llama.cpp\models\meta-llama-3-8b-instruct.Q4_K_M.gguf
SET SERVER=D:\Codaing\ThursdayV2\llama.cpp\build\bin\Release\llama-server.exe

%SERVER% ^
  -m "%MODEL_PATH%" ^
  -ngl 99 ^
  -c 2048 ^
  -b 512 ^
  -ub 128 ^
  -t 16 ^
  -fa on ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --host 127.0.0.1 ^
  --port 8080

pause

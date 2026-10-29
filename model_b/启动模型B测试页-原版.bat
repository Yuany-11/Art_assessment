@echo off
setlocal
set "URL=http://127.0.0.1:8010/old"
set "DIR=E:\Lab_Files\Project\Art_assessment\repo\model_b"
set "PYW=D:\Software_Program\anaconda3\envs\art_assessment_gpu\pythonw.exe"
set "PY=D:\Software_Program\anaconda3\envs\art_assessment_gpu\python.exe"

"%SystemRoot%\System32\curl.exe" -s -o nul --max-time 2 "%URL%" && (
  start "" "%URL%"
  exit /b
)

cd /d "%DIR%"
if exist "%PYW%" (
  start "" "%PYW%" test_ui_v3.py
) else (
  start "model_b_test_ui" "%PY%" test_ui_v3.py
)

for /l %%i in (1,1,30) do (
  "%SystemRoot%\System32\curl.exe" -s -o nul --max-time 1 "%URL%" && goto open
  %SystemRoot%\System32\PING.EXE -n 2 127.0.0.1 >nul
)

:open
start "" "%URL%"

@echo off
cd /d "%~dp0"
start "model_b_test_ui" "D:\Software_Program\anaconda3\envs\art_assessment_gpu\python.exe" test_ui_v3.py
timeout /t 8 /nobreak >nul
start "" "http://127.0.0.1:8010/"

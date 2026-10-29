@echo off
cd /d "%~dp0monitor"
start "model_b_monitor" "D:\Software_Program\anaconda3\envs\art_assessment\python.exe" app_v3.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8002/"

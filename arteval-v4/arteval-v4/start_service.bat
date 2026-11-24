@echo off
rem 启动 arteval-v4 音频标签服务（默认 http://127.0.0.1:8100）
rem 默认使用校准后的评分规则；可用 ARTEVAL_RUBRIC 指向机构审定版本。
cd /d "%~dp0"
if not defined ARTEVAL_RUBRIC set "ARTEVAL_RUBRIC=scoring\rubric.calibrated.json"
if exist "%~dp0..\.venv\Scripts\python.exe" (
  "%~dp0..\.venv\Scripts\python.exe" service.py --host 127.0.0.1 --port 8100
) else (
  python service.py --host 127.0.0.1 --port 8100
)

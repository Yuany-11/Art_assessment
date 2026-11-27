@echo off
chcp 936 >nul
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%\01_给后端A(1)\服务代码"

set "PY=%ROOT%\01_给后端A(1)\.venv\Scripts\python.exe"
set "ADAPTER=%ROOT%\01_给后端A(1)\模型权重\qgen_lora_3b_v4"

if not exist "%PY%" goto :no_env
if not defined QGEN_MODEL goto :no_model
if not exist "%QGEN_MODEL%\config.json" goto :no_model

set "QGEN_ADAPTER=%ADAPTER%"
set "QGEN_LOAD_4BIT=1"

echo ============================================================
echo   AI 出题模型（Model B）
echo   基座模型: %QGEN_MODEL%
echo   适配器:   %QGEN_ADAPTER%
echo   地址:     http://127.0.0.1:8002
echo ============================================================
echo.

"%PY%" -m uvicorn model_b_qgen.app:app --host 127.0.0.1 --port 8002
goto :eof

:no_env
echo [跳过] AI 出题模型未启动：缺少运行环境
echo        预期 Python: %PY%
echo        请在 01_给后端A(1) 目录创建 .venv 并安装 requirements.txt
pause
exit /b 1

:no_model
echo [跳过] AI 出题模型未启动：未找到基座模型 Qwen2.5-3B-Instruct
echo        请把模型放到 D:\models\Qwen2.5-3B-Instruct，
echo        或设置环境变量 QGEN_MODEL 指向模型目录。
pause
exit /b 1

@echo off
chcp 936 >nul
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"

echo ============================================================
echo   艺术素质测评系统 - 一键启动
echo   后端 8000 / 前端 5173 / 音频模型 8100 / AI 出题 8002
echo ============================================================
echo.

rem ---------- 检查 AI 出题模型能否启动 ----------
set "MODEL_READY="
set "QGEN_BASE="
if defined QGEN_MODEL if exist "%QGEN_MODEL%\config.json" set "QGEN_BASE=%QGEN_MODEL%"
if not defined QGEN_BASE if exist "D:\models\Qwen2.5-3B-Instruct\config.json" set "QGEN_BASE=D:\models\Qwen2.5-3B-Instruct"
if not defined QGEN_BASE if exist "%USERPROFILE%\models\Qwen2.5-3B-Instruct\config.json" set "QGEN_BASE=%USERPROFILE%\models\Qwen2.5-3B-Instruct"
if not defined QGEN_BASE goto :model_check_done
if not exist "%ROOT%01_给后端A(1)\.venv\Scripts\python.exe" goto :model_check_done
set "MODEL_READY=1"
:model_check_done

rem ---------- 后端 Django ----------
call :port_open 8000
if errorlevel 1 goto :start_backend
echo [跳过] 后端 8000 已在运行
goto :frontend

:start_backend
if defined MODEL_READY goto :start_backend_with_qgen
echo [启动] 后端 Django  http://127.0.0.1:8000  ^(使用 .env 中的 QGEN 配置^)
start "Art-Backend-8000" /D "%ROOT%Art_assessment_backend" cmd /k "python manage.py runserver 127.0.0.1:8000"
goto :frontend

:start_backend_with_qgen
echo [启动] 后端 Django  http://127.0.0.1:8000  ^(AI 出题开关打开^)
start "Art-Backend-8000" /D "%ROOT%Art_assessment_backend" cmd /k "set QGEN_ENABLED=1 && python manage.py runserver 127.0.0.1:8000"

rem ---------- 前端 Vite ----------
:frontend
call :port_open 5173
if errorlevel 1 goto :start_frontend
echo [跳过] 前端 5173 已在运行
goto :audio

:start_frontend
echo [启动] 前端 Vite  http://127.0.0.1:5173
start "Art-Frontend-5173" /D "%ROOT%Art_assessment_frontend" cmd /k "npm run dev -- --port 5173 --strictPort"

rem ---------- 音频标签模型 ----------
:audio
call :port_open 8100
if errorlevel 1 goto :start_audio
echo [跳过] 音频模型 8100 已在运行
goto :qgen

:start_audio
echo [启动] 音频标签模型  http://127.0.0.1:8100
start "Art-Audio-8100" /D "%ROOT%arteval-v4\arteval-v4" cmd /k start_service.bat

rem ---------- AI 出题模型 ----------
:qgen
call :port_open 8002
if errorlevel 1 goto :start_qgen
echo [跳过] AI 出题模型 8002 已在运行
goto :done

:start_qgen
if defined MODEL_READY goto :do_start_qgen
echo [跳过] AI 出题模型 8002：未找到基座模型或运行环境
echo        基座模型可放到 D:\models\Qwen2.5-3B-Instruct，
echo        或设置环境变量 QGEN_MODEL 指向模型目录；
echo        首次使用需在 01_给后端A(1)\.venv 安装 requirements.txt。
goto :done

:do_start_qgen
echo [启动] AI 出题模型  http://127.0.0.1:8002
set "QGEN_MODEL=%QGEN_BASE%"
start "Art-AI-QGen-8002" /D "%ROOT%01_给后端A(1)\服务代码" cmd /k "%ROOT%scripts\start_model_b.bat"

:done
echo.
echo 全部处理完成。服务窗口会保持打开，关闭窗口即停止对应服务。
echo.
pause
exit /b 0

rem ---------- 端口检测：已监听返回 1，未监听返回 0 ----------
:port_open
netstat -ano | findstr "LISTENING" | findstr ":%~1 " >nul
exit /b %errorlevel%

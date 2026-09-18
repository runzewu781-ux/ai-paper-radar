@echo off
REM AI Paper Radar + AutoPR 一键启动
REM 用法：双击本文件，或在本目录执行 start_all.bat

set PY_RADAR=C:\Users\Administrator\.workbuddy-ai\binaries\python\envs\paperradar\Scripts\python.exe
set PY_AUTOPR=C:\Users\Administrator\.workbuddy-ai\binaries\python\envs\autopr\Scripts\python.exe
set NODE=C:\Users\Administrator\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe
set ROOT=%~dp0

set PYTHONIOENCODING=utf-8

echo [1/3] 启动论文雷达后端 :8000
start "PaperRadar-Backend" cmd /k "cd /d %ROOT%PaperRadar\backend && %PY_RADAR% -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/3] 启动论文雷达前端 :5173
start "PaperRadar-Frontend" cmd /k "cd /d %ROOT%PaperRadar\frontend && %NODE% .\node_modules\vite\bin\vite.js --port 5173 --host 127.0.0.1"

echo [3/3] 启动 AutoPR 界面 :7860
start "AutoPR" cmd /k "cd /d %ROOT%AutoPR && %PY_AUTOPR% app.py"

echo.
echo 等待服务就绪（约 60 秒）...
timeout /t 3 /nobreak >nul

echo.
echo   论文雷达界面   http://127.0.0.1:5173
echo   AutoPR 界面    http://127.0.0.1:7860
echo   后端 API 文档  http://127.0.0.1:8000/docs
echo.
pause

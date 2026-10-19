@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
setlocal enabledelayedexpansion
title Khởi Chạy Cụm Fleet Runner 10 Tài Khoản Muse AI

cd /d "%~dp0"

echo ======================================================================
echo    [*] CỤM ĐIỀU PHỐI FLEET RUNNER 10 TÀI KHOẢN (CƠ CHẾ B)
echo ======================================================================
echo.

:: 1. Xác định Python (.venv hoặc hệ thống)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo [*] Sử dụng Virtual Environment: .venv
) else if exist "%~dp0projects\story-studio\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0projects\story-studio\.venv\Scripts\python.exe"
    echo [*] Sử dụng Virtual Environment: projects\story-studio\.venv
) else (
    set "PYTHON_EXE=python"
)

:: 2. Thông tin kết nối
echo [*] Loopback Backend: http://127.0.0.1:8000/api/muse-bridge
echo [*] Concurrency khống chế: N = 2 slots (Kiểm soát RAM ^< 1.5GB)
echo [*] Khởi động Fleet Runner ở chế độ Daemon...
echo.

:: 3. Chạy runner ngầm / daemon
"%PYTHON_EXE%" backend\runners\muse_fleet_runner.py --daemon --concurrency 2

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Fleet Runner kết thúc với mã lỗi %errorlevel%.
    pause
)

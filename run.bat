@echo off
setlocal enabledelayedexpansion
title YouTube Story Maker Studio

echo ============================================================
echo   [*] YOUTUBE STORY MAKER - DESKTOP LAUNCHER
echo ============================================================
echo.

cd /d "%~dp0"

:: Check if dedicated virtual environment on Drive D exists
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo [*] Using Drive D Virtual Environment: .venv
) else (
    set "PYTHON_EXE=python"
    where python >nul 2>nul
    if !errorlevel! neq 0 (
        echo [ERROR] Python not found in system PATH.
        echo Please install Python 3.10+ or create .venv.
        pause
        exit /b 1
    )
)

:: Check if FFmpeg is available
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg was not detected in system PATH.
    echo Video rendering requires FFmpeg. Please ensure FFmpeg is installed and added to PATH.
    echo.
)

echo [*] Starting YouTube Story Maker Web Server...
echo [*] Browser will open automatically at http://localhost:8000
echo.

:: Run server (python run.py)
"%PYTHON_EXE%" run.py %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server terminated with error code %errorlevel%.
    pause
)

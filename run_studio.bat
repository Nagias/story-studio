@echo off
chcp 65001 >nul
title YouTube Storyboard & Video Production Studio - 1-Click Runner

echo ===============================================================================
echo 🎬 AI YOUTUBE STORYBOARD & VIDEO PRODUCTION STUDIO (CINEMA & PODCAST)
echo    Powered by OP_CTOOL Master Spec Engine:
echo    - 3-Layer Audio Design (Voiceover + SFX + Adaptive Ducking BGM)
echo    - 9-Grid Composite Narrative Slicing (100%% Character Consistency)
echo    - 2.5D Parallax Optical Motion
echo    - Kinetic Karaoke Subtitles (ASS #FFD700 Word-Level Highlight)
echo ===============================================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Python venv tai: %PYTHON_EXE%
    echo Vui long kiem tra lai moi truong .venv!
    pause
    exit /b 1
)

echo [*] Python Runtime: %PYTHON_EXE%
echo [*] Dang khoi chay CLI Orchestrator...
echo.

if "%~1"=="" (
    "%PYTHON_EXE%" "%SCRIPT_DIR%run_studio.py" produce
) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%run_studio.py" %*
)

echo.
echo ===============================================================================
echo [*] Tac vu hoan tat!
pause

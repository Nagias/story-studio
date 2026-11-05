@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
setlocal
title Cai dat Story Studio

:: File nằm trong tools\, thư mục dự án là thư mục cha
cd /d "%~dp0.."

echo ======================================================================
echo   CÀI ĐẶT STORY STUDIO (chạy lại nhiều lần cũng được)
echo ======================================================================
echo.

if exist ".venv\Scripts\python.exe" goto HAVE_VENV

:: Ưu tiên trình chạy "py" của python.org để chọn đúng Python 3.14
set "PY="
where py >nul 2>nul && py -3.14 --version >nul 2>nul && set "PY=py -3.14"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto NO_PYTHON

echo [1/3] Tạo môi trường Python riêng .venv bằng: %PY%
%PY% -m venv .venv
if errorlevel 1 goto FAIL
goto CHECK_VERSION

:HAVE_VENV
echo [1/3] Đã có .venv, dùng lại.

:CHECK_VERSION
".venv\Scripts\python.exe" -c "import sys; print('      Python', sys.version.split()[0]); sys.exit(0 if sys.version_info[:2] == (3, 14) else 3)"
if errorlevel 3 echo [CẢNH BÁO] App đã kiểm trên Python 3.14. Bản khác có thể cài thư viện không được.
echo.

echo [2/3] Cài thư viện Python (lần đầu mất vài phút)...
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto FAIL
echo.

:: Không tải Chromium của Playwright: Fleet Runner mở Chrome hoặc Edge có sẵn trên máy
:: (get_installed_browser_channel trong backend\runners\muse_fleet_runner.py).

echo [3/3] File cấu hình .env
if exist ".env" goto ENV_KEEP
copy ".env.example" ".env" >nul
if errorlevel 1 goto FAIL
echo       Đã tạo .env từ .env.example. Mở .env và điền NINEROUTER_API_KEY.
goto TOOLS
:ENV_KEEP
echo       Đã có .env, giữ nguyên.

:TOOLS
echo.
echo Kiểm tra công cụ ngoài:
where ffmpeg >nul 2>nul && where ffprobe >nul 2>nul
if errorlevel 1 (echo   [THIẾU] ffmpeg/ffprobe: không dựng được video. Xem README.md mục 1.) else (echo   [CÓ] ffmpeg, ffprobe)
where node >nul 2>nul
if errorlevel 1 (echo   [THIẾU] Node.js: cần để chạy 9router. Xem README.md mục 1.) else (echo   [CÓ] Node.js)
where 9router >nul 2>nul
if errorlevel 1 (echo   [THIẾU] 9router: AI viết lời kể không chạy được. Xem README.md mục 4.) else (echo   [CÓ] 9router)
where uv >nul 2>nul
if errorlevel 1 (echo   [TUỲ CHỌN] uv chưa có: không dùng được giọng VieNeu, giọng Edge vẫn dùng được.) else (echo   [CÓ] uv)

echo.
echo ======================================================================
echo   XONG. Bước tiếp theo: điền .env, bật 9router, rồi chạy run.bat
echo ======================================================================
pause
exit /b 0

:NO_PYTHON
echo [LỖI] Không tìm thấy Python. Cài Python 3.14 từ python.org (xem README.md mục 1) rồi chạy lại file này.
pause
exit /b 1

:FAIL
echo.
echo [LỖI] Bước vừa rồi bị lỗi, đọc thông báo phía trên. Sửa xong thì chạy lại file này.
pause
exit /b 1

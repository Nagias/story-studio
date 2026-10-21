@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
setlocal enabledelayedexpansion
title Thiết Lập Đăng Nhập Fleet 10 Tài Khoản Muse

cd /d "%~dp0"

:: 1. Xác định đường dẫn Python (.venv hoặc Python hệ thống)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:MENU
cls
echo ======================================================================
echo       [*] THIẾT LẬP ĐĂNG NHẬP 10 TÀI KHOẢN META MUSE (FLEET)
echo ======================================================================
echo.
echo   [NHÓM 1: TÀI KHOẢN CHUYÊN TẠO ẢNH (2K / 16:9)]
echo     1. muse_acc_img_01 (Image Account 01)
echo     2. muse_acc_img_02 (Image Account 02)
echo     3. muse_acc_img_03 (Image Account 03)
echo     4. muse_acc_img_04 (Image Account 04)
echo     5. muse_acc_img_05 (Image Account 05)
echo.
echo   [NHÓM 2: TÀI KHOẢN CHUYÊN TẠO VIDEO (5s/10s Motion)]
echo     6. muse_acc_vid_01 (Video Account 01)
echo     7. muse_acc_vid_02 (Video Account 02)
echo     8. muse_acc_vid_03 (Video Account 03)
echo     9. muse_acc_vid_04 (Video Account 04)
echo    10. muse_acc_vid_05 (Video Account 05)
echo.
echo   [CÔNG CỤ KHÁC]
echo     L. Xem danh sách trạng thái 10 tài khoản
echo     0. Thoát
echo.
echo ======================================================================
set "CHOICE="
set /p "CHOICE=>> Nhập số lựa chọn (1-10, L, 0) và nhấn ENTER: "

if "%CHOICE%"=="" goto EXIT_SCRIPT
if "%CHOICE%"=="0" goto EXIT_SCRIPT
if /i "%CHOICE%"=="L" (
    echo.
    "%PYTHON_EXE%" backend\runners\muse_fleet_runner.py --list
    pause
    goto MENU
)
if "%CHOICE%"=="1" set "ACC_TARGET=muse_acc_img_01" & goto RUN_SETUP
if "%CHOICE%"=="2" set "ACC_TARGET=muse_acc_img_02" & goto RUN_SETUP
if "%CHOICE%"=="3" set "ACC_TARGET=muse_acc_img_03" & goto RUN_SETUP
if "%CHOICE%"=="4" set "ACC_TARGET=muse_acc_img_04" & goto RUN_SETUP
if "%CHOICE%"=="5" set "ACC_TARGET=muse_acc_img_05" & goto RUN_SETUP
if "%CHOICE%"=="6" set "ACC_TARGET=muse_acc_vid_01" & goto RUN_SETUP
if "%CHOICE%"=="7" set "ACC_TARGET=muse_acc_vid_02" & goto RUN_SETUP
if "%CHOICE%"=="8" set "ACC_TARGET=muse_acc_vid_03" & goto RUN_SETUP
if "%CHOICE%"=="9" set "ACC_TARGET=muse_acc_vid_04" & goto RUN_SETUP
if "%CHOICE%"=="10" set "ACC_TARGET=muse_acc_vid_05" & goto RUN_SETUP

echo [!] Lựa chọn không hợp lệ. Vui lòng nhập từ 1 đến 10.
ping 127.0.0.1 -n 2 >nul
goto MENU

:RUN_SETUP
echo.
echo [*] Đang khởi chạy Google Chrome / Edge có giao diện để thiết lập tài khoản: %ACC_TARGET%...
echo [*] Vui lòng đăng nhập trên cửa sổ trình duyệt vừa mở ra.
echo.
"%PYTHON_EXE%" backend\runners\muse_fleet_runner.py --setup %ACC_TARGET%
if errorlevel 1 (
    echo.
    echo [!] Đã xảy ra lỗi khi khởi chạy trình duyệt thiết lập (Mã lỗi: %errorlevel%).
) else (
    echo.
    echo [*] Hoàn tất phiên thiết lập cho %ACC_TARGET%.
)
pause
goto MENU

:EXIT_SCRIPT
echo [*] Đã đóng trình thiết lập. Chúc bạn một ngày làm việc hiệu quả!
exit /b 0

@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   WeChat Spider CI Build Script
echo ============================================

:: Read version from environment
set "TAG_VERSION=%CI_VERSION%"
set "VERSION=%TAG_VERSION:v=%"

if "%VERSION%"=="" (
    echo ERROR: CI_VERSION env var not set or empty
    set
    exit /b 1
)

:: Read UPX path from environment
set "UPX_PATH=%UPX_EXE%"

cd /d "%~dp0.."
set "PROJECT_DIR=%CD%"

echo Project: %PROJECT_DIR%
echo Version: %VERSION%
if not "%UPX_PATH%"=="" ( echo UPX: %UPX_PATH% ) else ( echo UPX: not set )
echo.

echo [1/6] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found
    exit /b 1
)

echo [2/6] Installing PyInstaller...
pip install pyinstaller --quiet --upgrade
if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
)

echo [3/6] Cleaning...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [4/6] Running PyInstaller...
if not "%UPX_PATH%"=="" (
    for %%i in ("%UPX_PATH%") do set "UPX_DIR=%%~dpi"
    echo Using UPX: !UPX_DIR!
    pyinstaller --clean --noconfirm --upx-dir "!UPX_DIR!" WeChatSpider.spec
) else (
    pyinstaller --clean --noconfirm WeChatSpider.spec
)
if errorlevel 1 (
    echo ERROR: PyInstaller failed
    exit /b 1
)

echo [5/6] UPX post-compression...
if not "%UPX_PATH%"=="" if exist "%UPX_PATH%" (
    "%UPX_PATH%" -t "dist\WeChatSpider\WeChatSpider.exe" >nul 2>&1
    if errorlevel 1 "%UPX_PATH%" --best --lzma "dist\WeChatSpider\WeChatSpider.exe" 2>nul

    set "COMPRESS_COUNT=0"
    set "SKIP_COUNT=0"
    for /r "dist\WeChatSpider" %%f in (*.dll) do (
        echo %%f | findstr /i "Qt6WebEngine Qt6Quick vcruntime ucrtbase api-ms-win msvcp python3" >nul 2>&1
        if errorlevel 1 (
            "%UPX_PATH%" -t "%%f" >nul 2>&1
            if errorlevel 1 (
                "%UPX_PATH%" --best --lzma "%%f" >nul 2>&1
                if not errorlevel 1 set /a COMPRESS_COUNT+=1
            )
        ) else ( set /a SKIP_COUNT+=1 )
    )
    echo DLL: compressed !COMPRESS_COUNT!, skipped !SKIP_COUNT!.

    set "PYD_COUNT=0"
    for /r "dist\WeChatSpider" %%f in (*.pyd) do (
        "%UPX_PATH%" -t "%%f" >nul 2>&1
        if errorlevel 1 (
            "%UPX_PATH%" --best --lzma "%%f" >nul 2>&1
            if not errorlevel 1 set /a PYD_COUNT+=1
        )
    )
    echo PYD: compressed !PYD_COUNT! files.
) else (
    echo Skipping UPX post-compression.
)

echo [6/6] Cleanup...
del /s /q "dist\WeChatSpider\*test*.py" "dist\WeChatSpider\*_test.py" 2>nul
for /d /r "dist\WeChatSpider" %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul
del /s /q "dist\WeChatSpider\*.pyc" 2>nul

echo ============================================
echo   Build completed!
echo   Version: %VERSION%
echo ============================================

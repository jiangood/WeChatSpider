@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   WeChat Spider CI Build Script
echo ============================================

set "TAG_VERSION=%CI_VERSION%"
set "VERSION=%TAG_VERSION:v=%"

if "%VERSION%"=="" (
    echo ERROR: CI_VERSION=[%CI_VERSION%] - env var not set
    goto :debug_env
    exit /b 1
)

set "UPX_PATH=%UPX_EXE%"

cd /d "%~dp0.."
set "PROJECT_DIR=%CD%"

echo Project: %PROJECT_DIR%
echo Version: %VERSION%
if not "%UPX_PATH%"=="" ( echo UPX: %UPX_PATH% ) else ( echo UPX: not set )

echo [1/6] Python check
python --version
if errorlevel 1 exit /b 1

echo [2/6] Install PyInstaller
pip install pyinstaller --quiet --upgrade
if errorlevel 1 exit /b 1

echo [3/6] Clean
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [4/6] PyInstaller
if not "%UPX_PATH%"=="" (
    for %%i in ("%UPX_PATH%") do set "UPX_DIR=%%~dpi"
    pyinstaller --clean --noconfirm --upx-dir "!UPX_DIR!" WeChatSpider.spec
) else (
    pyinstaller --clean --noconfirm WeChatSpider.spec
)
if errorlevel 1 exit /b 1

echo [5/6] UPX post-compression
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
    set "PYD_COUNT=0"
    for /r "dist\WeChatSpider" %%f in (*.pyd) do (
        "%UPX_PATH%" -t "%%f" >nul 2>&1
        if errorlevel 1 (
            "%UPX_PATH%" --best --lzma "%%f" >nul 2>&1
            if not errorlevel 1 set /a PYD_COUNT+=1
        )
    )
) else (
    echo Skipping UPX
)

echo [6/6] Cleanup
del /s /q "dist\WeChatSpider\*test*.py" "dist\WeChatSpider\*_test.py" 2>nul
for /d /r "dist\WeChatSpider" %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul
del /s /q "dist\WeChatSpider\*.pyc" 2>nul

echo Build OK! Version: %VERSION%
exit /b 0

:debug_env
echo Dumping environment variables for debugging:
set
exit /b 1

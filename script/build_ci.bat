@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   WeChat Spider CI Build Script
echo ============================================
echo.

:: ===== Parameters =====
:: %1 = tag version (e.g. v1.0.1)
set "TAG_VERSION=%~1"

:: Strip "v" prefix from version
set "VERSION=%TAG_VERSION:v=%"

:: Validate version
if "%VERSION%"=="" (
    echo ERROR: Version parameter is required
    exit /b 1
)

:: Get UPX path from environment (set by GitHub Actions in previous step)
set "UPX_PATH=%UPX_EXE%"

cd /d "%~dp0.."
set "PROJECT_DIR=%CD%"
echo Project Directory: %PROJECT_DIR%
echo Version: %VERSION%
if not "%UPX_PATH%"=="" (
    echo UPX: %UPX_PATH%
) else (
    echo UPX: not found in environment, skipping
)
echo.

:: Check Python
echo [1/6] Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo %PYTHON_VER% found.
echo.

:: Install PyInstaller
echo [2/6] Installing PyInstaller...
pip install pyinstaller --quiet --upgrade
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    exit /b 1
)
echo PyInstaller ready.
echo.

:: Clean previous build
echo [3/6] Cleaning previous build...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo Clean completed.
echo.

:: Run PyInstaller
echo [4/6] Running PyInstaller...
echo This may take several minutes...
echo.
if not "%UPX_PATH%"=="" (
    for %%i in ("%UPX_PATH%") do set "UPX_DIR=%%~dpi"
    echo Using UPX directory: !UPX_DIR!
    pyinstaller --clean --noconfirm --upx-dir "!UPX_DIR!" WeChatSpider.spec
) else (
    echo WARNING: No UPX provided, building without UPX
    pyinstaller --clean --noconfirm WeChatSpider.spec
)
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)
echo PyInstaller build completed.
echo.

:: Copy icon file
echo Copying icon file...
if exist "%PROJECT_DIR%\gnivu-cfd69-001.ico" (
    copy /y "%PROJECT_DIR%\gnivu-cfd69-001.ico" "%PROJECT_DIR%\dist\WeChatSpider\" >nul
)
echo.

:: Additional UPX Compression
echo [5/6] Additional UPX compression...
if "%UPX_PATH%"=="" (
    echo Skipping - no UPX available.
    goto :skip_upx
)
if not exist "%UPX_PATH%" (
    echo WARNING: UPX not found at %UPX_PATH%, skipping.
    goto :skip_upx
)

echo Compressing additional executable files...

:: Compress main exe
if exist "dist\WeChatSpider\WeChatSpider.exe" (
    "%UPX_PATH%" -t "dist\WeChatSpider\WeChatSpider.exe" >nul 2>&1
    if errorlevel 1 (
        "%UPX_PATH%" --best --lzma "dist\WeChatSpider\WeChatSpider.exe" 2>nul
    )
)

:: Compress DLLs
set "COMPRESS_COUNT=0"
set "SKIP_COUNT=0"
for /r "dist\WeChatSpider" %%f in (*.dll) do (
    call :compress_dll "%%f" "%%~nxf"
)
echo DLL: compressed !COMPRESS_COUNT!, skipped !SKIP_COUNT!.

:: Compress PYDs
set "PYD_COUNT=0"
for /r "dist\WeChatSpider" %%f in (*.pyd) do (
    "%UPX_PATH%" -t "%%f" >nul 2>&1
    if errorlevel 1 (
        "%UPX_PATH%" --best --lzma "%%f" >nul 2>&1
        if not errorlevel 1 set /a PYD_COUNT+=1
    )
)
echo PYD: compressed !PYD_COUNT! files.
echo UPX compression done.
goto :after_upx

:compress_dll
set "FILEPATH=%~1"
set "FILENAME=%~2"
echo %FILENAME% | findstr /i "Qt6WebEngine Qt6Quick vcruntime ucrtbase api-ms-win msvcp python3" >nul 2>&1
if not errorlevel 1 (
    set /a SKIP_COUNT+=1
    goto :eof
)
"%UPX_PATH%" -t "%FILEPATH%" >nul 2>&1
if errorlevel 1 (
    "%UPX_PATH%" --best --lzma "%FILEPATH%" >nul 2>&1
    if not errorlevel 1 set /a COMPRESS_COUNT+=1
)
goto :eof

:skip_upx
:after_upx
echo.

:: Cleanup
echo [6/6] Cleaning up unnecessary files...
set "CLEANUP_COUNT=0"

:: Remove test files
for /r "%PROJECT_DIR%\dist\WeChatSpider" %%f in (*test*.py *_test.py test_*.py) do (
    del /q "%%f" 2>nul
    if not errorlevel 1 set /a CLEANUP_COUNT+=1
)

:: Remove __pycache__
for /d /r "%PROJECT_DIR%\dist\WeChatSpider" %%d in (__pycache__) do (
    rmdir /s /q "%%d" 2>nul
    if not errorlevel 1 set /a CLEANUP_COUNT+=1
)

:: Remove .pyc files
for /r "%PROJECT_DIR%\dist\WeChatSpider" %%f in (*.pyc) do (
    del /q "%%f" 2>nul
    if not errorlevel 1 set /a CLEANUP_COUNT+=1
)

echo Cleaned up !CLEANUP_COUNT! items.
echo.

:: Done
echo ============================================
echo   CI Build completed successfully!
echo   Version: %VERSION%
echo   Output: %PROJECT_DIR%\dist\WeChatSpider\
echo ============================================

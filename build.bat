@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
::  build.bat — Package download_split.py into a standalone exe
::  Output : dist\ytdl-splitter.exe
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "PY_SCRIPT=%SCRIPT_DIR%download_split.py"

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║   Build : youtube-to-playlist.exe  (PyInstaller)  ║
echo  ╚═══════════════════════════════════════════════╝
echo.

:: ── Python check ─────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo   [ERROR]  Python not found. Install Python 3.10+ from https://python.org
    goto :FAIL
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [OK]  %%v

:: ── PyInstaller check / install ──────────────────────────
echo.
python -m PyInstaller --version >nul 2>&1
if not errorlevel 1 goto :PYINSTALLER_READY
echo   [ ! ] PyInstaller not found. Installing...
python -m pip install pyinstaller
if errorlevel 1 (
    echo   [ERROR]  PyInstaller installation failed.
    goto :FAIL
)
:PYINSTALLER_READY
for /f "tokens=*" %%v in ('python -m PyInstaller --version 2^>^&1') do echo   [OK]  PyInstaller %%v

:: ── yt-dlp Python module (must be pip-installed to be bundled) ──────────
echo.
python -c "import yt_dlp" >nul 2>&1
if not errorlevel 1 goto :YTDLP_READY
echo   [ ! ] yt-dlp Python module not found. Installing...
python -m pip install yt-dlp
if errorlevel 1 (
    echo   [ERROR]  yt-dlp installation failed.
    goto :FAIL
)
:YTDLP_READY
for /f "tokens=*" %%v in ('python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2^>nul') do echo   [OK]  yt-dlp %%v  (will be bundled in exe)

:: ── Check source script ──────────────────────────────────
if not exist "%PY_SCRIPT%" (
    echo   [ERROR]  download_split.py not found in %SCRIPT_DIR%
    goto :FAIL
)

:: ── Build ────────────────────────────────────────────────
echo.
echo  ┌─ Building ──────────────────────────────────────────────────────────┐
echo  │  Source  : download_split.py                                        │
echo  │  Output  : dist\youtube-to-playlist.exe                                │
echo  │  Mode    : --onefile  (single executable, no extra files)           │
echo  └─────────────────────────────────────────────────────────────────────┘
echo.

pushd "%SCRIPT_DIR%"
python -m PyInstaller --onefile --name youtube-to-playlist --console "%PY_SCRIPT%"
if errorlevel 1 (
    popd
    echo.
    echo   [ERROR]  Build failed. See output above for details.
    goto :FAIL
)
popd

:: ── Result ───────────────────────────────────────────────
echo.
if exist "%SCRIPT_DIR%dist\youtube-to-playlist.exe" (
    echo  ┌─ Build successful ──────────────────────────────────────────────────┐
    echo  │                                                                      │
    echo  │   dist\youtube-to-playlist.exe  is ready.                             │
    echo  │                                                                      │
    echo  │   To distribute without Python:                                     │
    echo  │     copy  launcher.bat  +  dist\ytdl-splitter.exe                   │
    echo  │     (yt-dlp and ffmpeg still need to be installed on target)        │
    echo  │                                                                      │
    echo  │   launcher.bat will auto-detect ytdl-splitter.exe.                  │
    echo  │                                                                      │
    echo  └─────────────────────────────────────────────────────────────────────┘
) else (
    echo   [ERROR]  exe not found after build. Something went wrong.
    goto :FAIL
)

echo.
echo   Press any key to close.
pause >nul
endlocal
exit /b 0

:FAIL
echo.
echo   Press any key to close.
pause >nul
endlocal
exit /b 1

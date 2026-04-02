@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
::  YouTube Audio Downloader & Splitter — Launcher  v2.0
:: ============================================================
::  - Timestamps auto-fetched from YouTube (chapters / desc)
::  - Output folder suggested from video title
::  - Base folder saved in config.ini
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.ini"
set "PY_SCRIPT=%SCRIPT_DIR%download_split.py"
set "EXE_PATH=%SCRIPT_DIR%dist\ytdl-splitter.exe"
set "DEFAULT_URL=https://www.youtube.com/watch?v=Nr82n2P-IDA"
set "PYTHONUTF8=1"

:: Auto-detect compiled exe vs python script
set "USE_EXE=0"
if exist "%EXE_PATH%" set "USE_EXE=1"

:: ── Check / install dependencies ──────────────────────────
call :CHECK_DEPS
if errorlevel 1 (
    echo.
    echo  Press any key to quit.
    pause >nul
    exit /b 1
)

:: ── Load config ───────────────────────────────────────────
set "BASE_FOLDER="
if exist "%CONFIG_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%CONFIG_FILE%") do (
        if "%%a"=="base_folder" set "BASE_FOLDER=%%b"
    )
)
if "%BASE_FOLDER%"=="" set "BASE_FOLDER=%SCRIPT_DIR%output"

:MAIN_MENU
cls
echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║   YouTube Audio Downloader ^& Splitter  v2.0   ║
echo  ╚═══════════════════════════════════════════════╝
echo.
echo   Base folder : %BASE_FOLDER%
echo.
echo   [1]  Download ^& split a video
echo   [2]  Change base folder
echo   [3]  Quit
echo.
set /p "MENU_CHOICE=  Your choice [1-3] : "

if "%MENU_CHOICE%"=="1" goto DOWNLOAD
if "%MENU_CHOICE%"=="2" goto CHANGE_FOLDER
if "%MENU_CHOICE%"=="3" goto EXIT
goto MAIN_MENU

:: ────────────────────────────────────────────────────────────
:CHANGE_FOLDER
cls
echo.
echo   Current folder : %BASE_FOLDER%
echo.
set /p "NEW_FOLDER=  New path (Enter = keep current) : "
if not "%NEW_FOLDER%"=="" (
    set "BASE_FOLDER=%NEW_FOLDER%"
    (echo base_folder=%NEW_FOLDER%) > "%CONFIG_FILE%"
    echo.
    echo   Saved.
    timeout /t 1 /nobreak >nul
)
goto MAIN_MENU

:: ────────────────────────────────────────────────────────────
:DOWNLOAD
cls
echo.
echo  ┌─ New extraction ────────────────────────────────────────────────────┐
echo.

:: ── URL ───────────────────────────────────────────────────────────────────
echo   Default URL : %DEFAULT_URL%
echo.
set /p "URL=  YouTube URL (Enter = use default) : "
if "%URL%"=="" set "URL=%DEFAULT_URL%"

:: ── Fetch video info (title + tracks) ─────────────────────────────────────
echo.
echo  ┌─ Video info ────────────────────────────────────────────────────────┐
echo.
set "TMPINFO=%TEMP%\yt_info_%RANDOM%.txt"
if "!USE_EXE!"=="1" goto :SI_EXE
python "%PY_SCRIPT%" --url "%URL%" --show-info > "%TMPINFO%" 2>&1
goto :SI_DONE
:SI_EXE
"%EXE_PATH%" --url "%URL%" --show-info > "%TMPINFO%" 2>&1
:SI_DONE

if %ERRORLEVEL% neq 0 (
    type "%TMPINFO%"
    del "%TMPINFO%" 2>nul
    echo.
    echo  [ERROR] Could not fetch video info. Check the URL and your connection.
    echo.
    pause
    goto MAIN_MENU
)

:: Print everything except the __SLUG__ marker line
findstr /v /c:"__SLUG__=" "%TMPINFO%"

:: Extract the slug
set "VID_SLUG="
for /f "tokens=2 delims==" %%a in ('findstr /c:"__SLUG__=" "%TMPINFO%"') do set "VID_SLUG=%%a"
del "%TMPINFO%" 2>nul

if "%VID_SLUG%"=="" set "VID_SLUG=video_%RANDOM%"

:: ── Output sub-folder ─────────────────────────────────────────────────────
echo.
echo  └─────────────────────────────────────────────────────────────────────┘
echo.
echo   Suggested folder name : %VID_SLUG%
echo.
set /p "SUBFOLDER=  Sub-folder (Enter = keep suggestion) : "
if "%SUBFOLDER%"=="" set "SUBFOLDER=%VID_SLUG%"
set "OUTPUT_PATH=%BASE_FOLDER%\%SUBFOLDER%"

:: ── Format ────────────────────────────────────────────────────────────────
echo.
echo   Audio format :
echo     [1]  MP3  (recommended, universal compatibility)
echo     [2]  OGG  (open format, equivalent quality)
echo.
set /p "FMT_CHOICE=  Choice [1/2] (Enter = MP3) : "
set "FORMAT=mp3"
if "%FMT_CHOICE%"=="2" set "FORMAT=ogg"

:: ── Quality ───────────────────────────────────────────────────────────────
echo.
echo   Audio quality :
echo     [1]  320 kbps  - High quality      (recommended)
echo     [2]  192 kbps  - Good quality
echo     [3]  128 kbps  - Limited bandwidth
echo     [4]   96 kbps  - Smallest files
echo.
set /p "Q_CHOICE=  Choice [1-4] (Enter = 320 kbps) : "
set "BITRATE=320"
if "%Q_CHOICE%"=="2" set "BITRATE=192"
if "%Q_CHOICE%"=="3" set "BITRATE=128"
if "%Q_CHOICE%"=="4" set "BITRATE=96"

:: ── Summary + confirm ─────────────────────────────────────────────────────
set "TIMESTAMPS_ARG="
echo.
echo  ┌─ Summary ───────────────────────────────────────────────────────────┐
echo  │  URL     : %URL%
echo  │  Output  : %OUTPUT_PATH%
echo  │  Format  : %FORMAT% @ %BITRATE% kbps
echo  └─────────────────────────────────────────────────────────────────────┘
echo.
set /p "CONFIRM=  Start download? [Y/n] : "
if /i "%CONFIRM%"=="n" goto MAIN_MENU

:: ── Check ffmpeg before launching ────────────────────────────────────────
call :FIND_FFMPEG
if "!FFMPEG_FOUND!"=="1" goto :DO_LAUNCH
echo.
echo   [ ! ] ffmpeg is required to split the audio.
echo.
echo         Install options :
echo           [1]  winget  (Windows 10/11 - recommended)
echo           [2]  choco   (if Chocolatey is installed)
echo           [3]  Cancel
echo.
set /p "INST_FFMPEG2=        Your choice [1/2/3] : "
if "!INST_FFMPEG2!"=="1" call :INSTALL_FFMPEG winget
if "!INST_FFMPEG2!"=="2" call :INSTALL_FFMPEG choco
if "!INST_FFMPEG2!"=="3" goto MAIN_MENU
if "!FFMPEG_FOUND!"=="0" goto MAIN_MENU

:DO_LAUNCH
echo.
if "!USE_EXE!"=="1" goto :LAUNCH_EXE
python "%PY_SCRIPT%" --url "%URL%" %TIMESTAMPS_ARG% --output "%OUTPUT_PATH%" --format %FORMAT% --bitrate %BITRATE% --no-dep-check
goto :LAUNCH_DONE
:LAUNCH_EXE
"%EXE_PATH%" --url "%URL%" %TIMESTAMPS_ARG% --output "%OUTPUT_PATH%" --format %FORMAT% --bitrate %BITRATE% --no-dep-check
:LAUNCH_DONE

echo.
echo  ┌─────────────────────────────────────────────────────────────────────┐
echo  │  Done.  Press any key to return to the menu.                        │
echo  └─────────────────────────────────────────────────────────────────────┘
pause >nul
set "URL="
goto MAIN_MENU

:EXIT
endlocal
exit /b 0

:: ════════════════════════════════════════════════════════════
::  Subroutine : CHECK_DEPS  (flat goto, no nested if/else)
:: ════════════════════════════════════════════════════════════
:CHECK_DEPS
cls
echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║        Dependency check                       ║
echo  ╚═══════════════════════════════════════════════╝
echo.

:: ── Python ───────────────────────────────────────────────
:: Check if pre-built exe is present (no Python needed)
if "!USE_EXE!"=="1" (
    echo   [OK]  Using pre-built ytdl-splitter.exe  (Python not required)
    goto :DEPS_YTDLP
)
where python >nul 2>&1
if errorlevel 1 goto :DEPS_NO_PYTHON
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   [OK]  %%v
goto :DEPS_YTDLP

:DEPS_NO_PYTHON
echo   [!!]  Python not found.
echo         Install Python 3.10+ from https://python.org
echo         and check "Add Python to PATH" during setup.
exit /b 1

:: ── yt-dlp ───────────────────────────────────────────────
:DEPS_YTDLP
where yt-dlp >nul 2>&1
if errorlevel 1 goto :DEPS_INSTALL_YTDLP
for /f %%v in ('yt-dlp --version 2^>nul') do echo   [OK]  yt-dlp %%v
goto :DEPS_FFMPEG

:DEPS_INSTALL_YTDLP
echo   [ ! ] yt-dlp not installed.
set /p "INST_YTDLP=        Install now? [Y/N] : "
if /i "!INST_YTDLP!" neq "Y" goto :DEPS_YTDLP_ABORT
echo.
echo        Installing yt-dlp...
python -m pip install --upgrade yt-dlp
where yt-dlp >nul 2>&1
if errorlevel 1 goto :DEPS_YTDLP_FAIL
echo        [OK]  yt-dlp installed.
goto :DEPS_FFMPEG

:DEPS_YTDLP_ABORT
echo        yt-dlp is required. Aborting.
exit /b 1

:DEPS_YTDLP_FAIL
echo        [ERROR]  yt-dlp installation failed.
exit /b 1

:: ── ffmpeg ───────────────────────────────────────────────
:DEPS_FFMPEG
call :FIND_FFMPEG
if "!FFMPEG_FOUND!"=="1" goto :DEPS_FFMPEG_OK
echo   [ ! ] ffmpeg not installed.
echo.
echo         Install options :
echo           [1]  winget  (Windows 10/11 - recommended)
echo           [2]  choco   (if Chocolatey is installed)
echo           [3]  Skip    (ffmpeg will be needed later)
echo.
set /p "INST_FFMPEG=        Your choice [1/2/3] : "
if "!INST_FFMPEG!"=="1" call :INSTALL_FFMPEG winget
if "!INST_FFMPEG!"=="2" call :INSTALL_FFMPEG choco
goto :DEPS_DONE

:DEPS_FFMPEG_OK
for /f "tokens=3" %%v in ('ffmpeg -version 2^>nul') do (
    echo   [OK]  ffmpeg %%v
    goto :DEPS_DONE
)

:DEPS_DONE
echo.
echo  -------------------------------------------------
timeout /t 2 /nobreak >nul
exit /b 0

:: ════════════════════════════════════════════════════════════
::  Subroutine : FIND_FFMPEG
:: ════════════════════════════════════════════════════════════
:FIND_FFMPEG
set "FFMPEG_FOUND=0"
where ffmpeg >nul 2>&1
if not errorlevel 1 ( set "FFMPEG_FOUND=1" & exit /b 0 )

set "NEWPATH_M="
for /f "skip=2 tokens=1,2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do (
    if /i "%%a"=="Path" set "NEWPATH_M=%%c"
)
set "NEWPATH_U="
for /f "skip=2 tokens=1,2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do (
    if /i "%%a"=="Path" set "NEWPATH_U=%%c"
)
if defined NEWPATH_M set "PATH=!NEWPATH_M!;!NEWPATH_U!"

where ffmpeg >nul 2>&1
if not errorlevel 1 ( set "FFMPEG_FOUND=1" & exit /b 0 )
exit /b 0

:: ════════════════════════════════════════════════════════════
::  Subroutine : INSTALL_FFMPEG  [winget|choco]
:: ════════════════════════════════════════════════════════════
:INSTALL_FFMPEG
echo.
if "%~1"=="winget" (
    echo        Installing via winget...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
) else (
    echo        Installing via chocolatey...
    choco install ffmpeg -y
)
echo.
echo        Searching for ffmpeg...
call :FIND_FFMPEG
if "!FFMPEG_FOUND!"=="1" goto :INSTALL_FFMPEG_OK
echo        [ ! ] ffmpeg not found in this session.
echo              Close and relaunch the .bat once installation is complete.
exit /b 0

:INSTALL_FFMPEG_OK
echo        [OK]  ffmpeg installed and ready.
exit /b 0

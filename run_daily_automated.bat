@echo off
REM ABQ Daily Intelligence - Automated Execution Script
REM This script is designed to run via Windows Task Scheduler
REM Triggers: daily at 7 AM, on logon, on session unlock
REM Guard: skips if already ran successfully today

setlocal

REM Set project directory
set PROJECT_DIR=c:\Users\mfont\projects\ABQ-veille
cd /d "%PROJECT_DIR%"

REM Skip on weekends (Saturday=6, Sunday=0)
for /f %%i in ('powershell -NoProfile -Command "[int](Get-Date).DayOfWeek"') do set DOW=%%i
if "%DOW%"=="0" (
    echo %date% %time% - Sunday, skipping >> "%PROJECT_DIR%\logs\skipped.log"
    REM Weekend heartbeat: UptimeRobot is interval-based and would page every
    REM Saturday otherwise. Proves the machine and the task are alive.
    "%PROJECT_DIR%\.venv\Scripts\python.exe" scripts\heartbeat.py "Sunday - digest skipped by design" >> "%PROJECT_DIR%\logs\skipped.log" 2>&1
    exit /b 0
)
if "%DOW%"=="6" (
    echo %date% %time% - Saturday, skipping >> "%PROJECT_DIR%\logs\skipped.log"
    REM Weekend heartbeat: UptimeRobot is interval-based and would page every
    REM Saturday otherwise. Proves the machine and the task are alive.
    "%PROJECT_DIR%\.venv\Scripts\python.exe" scripts\heartbeat.py "Saturday - digest skipped by design" >> "%PROJECT_DIR%\logs\skipped.log" 2>&1
    exit /b 0
)

REM Create logs directory if it doesn't exist
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM Build today's marker file path (YYYY-MM-DD format). Locale-independent:
REM slicing %date% assumed US mm/dd/yyyy; on this machine (yyyy-mm-dd) it
REM produced names like ".last_success_0-05-20-6-".
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
set MARKER=%PROJECT_DIR%\logs\.last_success_%TODAY%

REM Skip if already ran successfully today
if exist "%MARKER%" (
    echo %date% %time% - Already ran successfully today, skipping >> "%PROJECT_DIR%\logs\skipped.log"
    exit /b 0
)

REM Set log file with timestamp
set LOGFILE=%PROJECT_DIR%\logs\automated_run_%TODAY%.log

echo ============================================= >> "%LOGFILE%"
echo ABQ Daily Intelligence - Automated Run >> "%LOGFILE%"
echo Started: %date% %time% >> "%LOGFILE%"
echo ============================================= >> "%LOGFILE%"

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if activation succeeded
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment >> "%LOGFILE%"
    exit /b 1
)

REM Run the daily pipeline (production mode - sends email)
python run_daily.py >> "%LOGFILE%" 2>&1

REM Capture exit code
set EXIT_CODE=%errorlevel%

echo ============================================= >> "%LOGFILE%"
echo Completed: %date% %time% >> "%LOGFILE%"
echo Exit Code: %EXIT_CODE% >> "%LOGFILE%"
echo ============================================= >> "%LOGFILE%"

REM On success, write marker so we don't re-run today
if %EXIT_CODE% equ 0 (
    echo %date% %time% > "%MARKER%"
    REM Clean up old markers (keep last 7 days)
    forfiles /p "%PROJECT_DIR%\logs" /m ".last_success_*" /d -7 /c "cmd /c del @path" 2>nul

    REM Report days that never got a digest. On a Monday this surfaces the
    REM Friday and Saturday skipped by the weekend guard above.
    REM Report-only: backfilling sends a real email, so it stays manual.
    REM Recover with: python run_backfill.py --run
    echo --- Missed-day check --- >> "%LOGFILE%"
    python run_backfill.py >> "%LOGFILE%" 2>&1

    REM Weekly publisher audit (Mondays): emails ALERT_EMAIL only when a
    REM content-farm-looking publisher needs a decision. Never the member list.
    if "%DOW%"=="1" (
        echo --- Publisher audit --- >> "%LOGFILE%"
        python scriptsudit_publishers.py --email >> "%LOGFILE%" 2>&1
    )
)

REM Deactivate virtual environment
call deactivate

exit /b %EXIT_CODE%

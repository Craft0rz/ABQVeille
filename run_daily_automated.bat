@echo off
REM ABQ Daily Intelligence - Automated Execution Script
REM This script is designed to run via Windows Task Scheduler

setlocal

REM Set project directory
set PROJECT_DIR=c:\Users\mfont\projects\ABQ
cd /d "%PROJECT_DIR%"

REM Create logs directory if it doesn't exist
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM Set log file with timestamp
set LOGFILE=%PROJECT_DIR%\logs\automated_run_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log

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

REM Deactivate virtual environment
call deactivate

exit /b %EXIT_CODE%

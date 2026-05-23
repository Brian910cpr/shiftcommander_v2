@echo off
setlocal
title ShiftCommander Backend - http://127.0.0.1:5000

set "REPO_DIR=E:\GitHub\shiftcommander_v2"
set "PYTHON_CMD=python"

echo ============================================================
echo ShiftCommander Backend
echo ============================================================
echo Repo: %REPO_DIR%
echo URL:  http://127.0.0.1:5000
echo.

if not exist "%REPO_DIR%\server.py" (
    echo ERROR: server.py was not found at "%REPO_DIR%\server.py".
    echo Check that the repo path is correct.
    goto :fail
)

cd /d "%REPO_DIR%" || goto :fail

echo Starting backend with: %PYTHON_CMD% server.py
echo Keep this window open while Base44 is using the local bridge.
echo.
%PYTHON_CMD% server.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Backend process exited with code %EXIT_CODE%.
if not "%SHIFTCOMMANDER_TASK_MODE%"=="1" pause
exit /b %EXIT_CODE%

:fail
set "EXIT_CODE=1"
if not "%SHIFTCOMMANDER_TASK_MODE%"=="1" pause
exit /b %EXIT_CODE%

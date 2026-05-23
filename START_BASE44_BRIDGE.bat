@echo off
title ShiftCommander Base44 Bridge Launcher
color 0A

set REPO_DIR=E:\GitHub\shiftcommander_v2
set PYTHON_CMD=python
set CLOUDFLARED_EXE=C:\Tools\cloudflared.exe
set LOCAL_BASE=http://127.0.0.1:5000

echo ============================================================
echo ShiftCommander Base44 Bridge Launcher
echo ============================================================
echo.
echo This will start:
echo   1. ShiftCommander Flask backend
echo   2. Cloudflare public tunnel
echo   3. A test helper window
echo.
echo KEEP THE BACKEND AND TUNNEL WINDOWS OPEN.
echo If either one closes, Base44 loses the live connection.
echo.
pause

echo.
echo Checking repo folder...
if not exist "%REPO_DIR%\server.py" (
    echo ERROR: Could not find server.py at:
    echo %REPO_DIR%\server.py
    echo.
    pause
    exit /b 1
)

echo Checking cloudflared...
if not exist "%CLOUDFLARED_EXE%" (
    echo ERROR: cloudflared.exe not found at:
    echo %CLOUDFLARED_EXE%
    echo.
    echo Expected location:
    echo C:\Tools\cloudflared.exe
    echo.
    echo Fix by downloading cloudflared.exe into C:\Tools.
    pause
    exit /b 1
)

echo.
echo Starting ShiftCommander backend...
start "ShiftCommander Flask Backend - DO NOT CLOSE" cmd /k "cd /d %REPO_DIR% && %PYTHON_CMD% server.py"

echo.
echo Waiting 5 seconds for backend to start...
timeout /t 5 /nobreak >nul

echo.
echo Starting Cloudflare Tunnel...
start "ShiftCommander Cloudflare Tunnel - DO NOT CLOSE" cmd /k "%CLOUDFLARED_EXE% tunnel --url %LOCAL_BASE%"

echo.
echo Opening test/helper window...
start "ShiftCommander Bridge Test Helper" cmd /k "echo Wait for the Cloudflare window to print a URL like https://something.trycloudflare.com && echo. && echo Copy that URL, then run these tests by replacing YOUR_URL below: && echo. && echo irm YOUR_URL/api/health && echo irm YOUR_URL/api/base44/manifest && echo irm YOUR_URL/api/bootstrap && echo irm YOUR_URL/api/schedule && echo. && echo If all tests return JSON/data, give Base44 the base URL only. && echo Example: https://something.trycloudflare.com && echo. && powershell"

echo.
echo ============================================================
echo Started.
echo ============================================================
echo.
echo NEXT:
echo 1. Look at the Cloudflare Tunnel window.
echo 2. Copy the trycloudflare.com URL.
echo 3. Test it in the helper window.
echo 4. Give Base44 the base URL.
echo.
pause
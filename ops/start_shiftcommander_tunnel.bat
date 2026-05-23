@echo off
setlocal
title ShiftCommander Cloudflare Tunnel - sc-api.adr-fr.org

set "REPO_DIR=E:\GitHub\shiftcommander_v2"
set "CLOUDFLARED_EXE=C:\Tools\cloudflared.exe"
set "LOCAL_SERVICE=http://127.0.0.1:5000"
set "PUBLIC_HOSTNAME=sc-api.adr-fr.org"
set "DEFAULT_TUNNEL_NAME=shiftcommander-api"
set "USER_CONFIG=%USERPROFILE%\.cloudflared\config.yml"
set "SYSTEM_CONFIG=C:\Windows\System32\config\systemprofile\.cloudflared\config.yml"

echo ============================================================
echo ShiftCommander Cloudflare Tunnel
echo ============================================================
echo Target public hostname: https://%PUBLIC_HOSTNAME%
echo Local backend:          %LOCAL_SERVICE%
echo.

if not exist "%CLOUDFLARED_EXE%" (
    echo ERROR: cloudflared was not found at:
    echo   %CLOUDFLARED_EXE%
    echo.
    echo Install step:
    echo   1. Create C:\Tools if needed.
    echo   2. Download cloudflared-windows-amd64.exe from:
    echo      https://github.com/cloudflare/cloudflared/releases/latest
    echo   3. Save it as:
    echo      C:\Tools\cloudflared.exe
    goto :fail
)

set "CONFIG_PATH="
if exist "%USER_CONFIG%" set "CONFIG_PATH=%USER_CONFIG%"
if not defined CONFIG_PATH if exist "%SYSTEM_CONFIG%" set "CONFIG_PATH=%SYSTEM_CONFIG%"

if not defined CONFIG_PATH (
    echo No Cloudflare named tunnel config was found.
    echo.
    echo Complete these one-time setup steps after logging into the Cloudflare account
    echo that manages adr-fr.org:
    echo.
    echo   "%CLOUDFLARED_EXE%" tunnel login
    echo   "%CLOUDFLARED_EXE%" tunnel create %DEFAULT_TUNNEL_NAME%
    echo   "%CLOUDFLARED_EXE%" tunnel route dns %DEFAULT_TUNNEL_NAME% %PUBLIC_HOSTNAME%
    echo.
    echo Then create %USER_CONFIG% with:
    echo.
    echo   tunnel: ^<TUNNEL-UUID-FROM-CREATE^>
    echo   credentials-file: %USERPROFILE%\.cloudflared\^<TUNNEL-UUID-FROM-CREATE^>.json
    echo   ingress:
    echo     - hostname: %PUBLIC_HOSTNAME%
    echo       service: %LOCAL_SERVICE%
    echo     - service: http_status:404
    echo.
    echo After that, rerun this script.
    goto :fail
)

echo Using Cloudflare config:
echo   %CONFIG_PATH%
echo.
echo Starting named tunnel. Keep this window open while Base44 is using the bridge.
echo.
"%CLOUDFLARED_EXE%" tunnel --config "%CONFIG_PATH%" run
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Cloudflare tunnel process exited with code %EXIT_CODE%.
if not "%SHIFTCOMMANDER_TASK_MODE%"=="1" pause
exit /b %EXIT_CODE%

:fail
set "EXIT_CODE=1"
if not "%SHIFTCOMMANDER_TASK_MODE%"=="1" pause
exit /b %EXIT_CODE%

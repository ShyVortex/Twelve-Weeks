@echo off
rem ============================================================================
rem  run-local.bat - runs the relay and the matchmaker locally, each in its own
rem  window, building first if the binaries are missing.
rem
rem  Ports:  relay      UDP 7000
rem          matchmaker clients TCP 7001, admin 7002
rem
rem  accounts.db is created in servers\build\data\.
rem ============================================================================
setlocal

set "ROOT=%~dp0"
set "OUT=%ROOT%build"
set "DATA=%OUT%\data"

rem ---- build anything missing ------------------------------------------------
set "NEED_BUILD="
if not exist "%OUT%\relay-server.exe" set "NEED_BUILD=1"
if not exist "%OUT%\matchmaker.exe"   set "NEED_BUILD=1"

if defined NEED_BUILD (
    echo [run]  binaries missing - building first...
    call "%ROOT%build.bat" all nopause
    if errorlevel 1 (
        echo.
        echo [ERROR] Build failed - not starting anything.
        pause
        exit /b 1
    )
)

if not exist "%DATA%" mkdir "%DATA%" >nul 2>&1

rem ---- relay -----------------------------------------------------------------
if not exist "%OUT%\relay-server.exe" (
    echo [ERROR] relay-server.exe missing.
    pause
    exit /b 1
)
echo [run]  relay        UDP 7000
start "to1 relay :7000" cmd /k ""%OUT%\relay-server.exe" 7000"

rem The relay must bind before the matchmaker health-probes it; the first probe round otherwise logs DOWN.
ping -n 2 127.0.0.1 >nul

rem ---- matchmaker --------------------------------------------------------------
rem cwd = DATA so accounts.db lands there rather than in servers\.
if not exist "%OUT%\matchmaker.exe" (
    echo [WARN] matchmaker.exe not built. Run build.bat for details.
) else (
    echo [run]  matchmaker   clients 7001, admin 7002
    start "to1 matchmaker :7001" /D "%DATA%" cmd /k ""%OUT%\matchmaker.exe" 7001 127.0.0.1 7000 15"
)

echo.
echo ============================================================
echo   Running. To attach the control panel:
echo     1. untick "SSH tunnel" in the Connection view
echo     2. host 127.0.0.1, admin port 7002
echo     3. Connect
echo.
echo   accounts.db starts empty - nobody can log in until you
echo   create an account in the panel's Accounts view.
echo.
echo   data: %DATA%
echo   stop: close the server windows
echo ============================================================

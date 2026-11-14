@echo off
rem ============================================================================
rem  build.bat - builds the to1 servers with MSVC into servers\build\.
rem
rem  Usage:  build.bat [target] [nodeps] [nopause]
rem            target = all (default) | relay | matchmaker
rem            nodeps = never auto-install dependencies, just skip what needs them
rem            nopause = don't wait for a keypress at the end
rem
rem  The relay has no external dependencies. The matchmaker requires SQLite +
rem  OpenSSL, installed via vcpkg into %LOCALAPPDATA%\vcpkg when missing.
rem ============================================================================
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "OUT=%ROOT%build"

rem ---- 0. arguments ----------------------------------------------------------
set "TARGET="
set "NOPAUSE="
set "NODEPS="
:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="nopause" goto :arg_nopause
if /i "%~1"=="nodeps"  goto :arg_nodeps
if not defined TARGET set "TARGET=%~1"
shift
goto :parse
:arg_nopause
set "NOPAUSE=1"
shift
goto :parse
:arg_nodeps
set "NODEPS=1"
shift
goto :parse
:parsed
if not defined TARGET set "TARGET=all"

set "FAILED="
set "BUILT="
set "SKIPPED="

if not exist "%OUT%\obj" mkdir "%OUT%\obj" >nul 2>&1

rem ---- 1. MSVC toolchain -----------------------------------------------------
rem Must run at top level, never inside a parenthesised if-block: the vswhere path
rem contains "(x86)" and cmd parses that ")" as the end of the block.
call :setup_msvc
if errorlevel 1 goto :fail

rem ---- 2. matchmaker dependencies (SQLite + OpenSSL via vcpkg) ---------------
call :find_deps
if defined DEPS_OK goto :deps_ready
if defined NODEPS goto :deps_ready
if /i "%TARGET%"=="relay" goto :deps_ready
call :install_deps
if errorlevel 1 set "DEPS_FAILED=1"
call :find_deps

:deps_ready
if defined DEPS_OK echo [env]  deps at %VCPKG_DIR%

rem ---- 3. build --------------------------------------------------------------
if /i "%TARGET%"=="all"        goto :build_relay
if /i "%TARGET%"=="relay"      goto :build_relay
if /i "%TARGET%"=="matchmaker" goto :build_mm
echo [ERROR] Unknown target "%TARGET%" - use: all ^| relay ^| matchmaker
goto :fail

:build_relay
echo.
echo [build] relay-server.exe
cl /nologo /O2 /EHsc /W3 "%ROOT%relay\relay-server.cpp" /Fe:"%OUT%\relay-server.exe" /Fo:"%OUT%\obj\\" ws2_32.lib
if errorlevel 1 (set "FAILED=!FAILED! relay") else (set "BUILT=!BUILT! relay-server.exe")
if /i not "%TARGET%"=="all" goto :summary

:build_mm
if not defined DEPS_OK goto :no_deps
echo.
echo [build] matchmaker.exe
cl /nologo /O2 /EHsc /W3 "%ROOT%matchmaker\matchmaker-server.cpp" /Fe:"%OUT%\matchmaker.exe" /Fo:"%OUT%\obj\\" /I "%VCPKG_INC%" /link /LIBPATH:"%VCPKG_LIB%" sqlite3.lib libcrypto.lib ws2_32.lib
if errorlevel 1 (set "FAILED=!FAILED! matchmaker") else (set "BUILT=!BUILT! matchmaker.exe")

:copy_dlls
rem Runtime DLLs go next to the exes so they start without PATH changes.
if defined DEPS_OK (
    for %%D in (sqlite3.dll libcrypto-3-x64.dll libcrypto-1_1-x64.dll) do (
        if exist "%VCPKG_BIN%\%%D" copy /y "%VCPKG_BIN%\%%D" "%OUT%\%%D" >nul 2>&1
    )
)
goto :summary

:no_deps
set "SKIPPED=1"
goto :summary


rem ============================================================================
rem  subroutines
rem ============================================================================

:setup_msvc
rem cl.exe on PATH is NOT sufficient: INCLUDE and LIB must be set too, or the
rem compiler starts and then fails with "stdint.h: no include path set". vcvars is
rem skipped only when the whole environment is already present.
where cl >nul 2>&1
if errorlevel 1 goto :run_vcvars
if not defined INCLUDE goto :run_vcvars
if not defined LIB goto :run_vcvars
echo [env]  MSVC environment already initialised
exit /b 0

:run_vcvars
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo [ERROR] vswhere.exe not found - is Visual Studio installed?
    echo         Install "Desktop development with C++" from the VS Installer.
    exit /b 1
)
set "VSPATH="
rem !VSWHERE! must be delayed-expanded: the path contains "(x86)", and a parse-time %VAR% closes the for-clause early.
for /f "usebackq tokens=*" %%i in (`"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
if not defined VSPATH (
    echo [ERROR] No Visual Studio install with the C++ toolset was found.
    echo         Install "Desktop development with C++" from the VS Installer.
    exit /b 1
)
set "VCVARS=%VSPATH%\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VCVARS%" (
    echo [ERROR] vcvars64.bat missing under %VSPATH%
    exit /b 1
)
echo [env]  using %VSPATH%
rem stderr is suppressed: vcvars64.bat prints "'vswhere.exe' is not recognized" on some installs and still succeeds; errorlevel is the failure signal.
call "%VCVARS%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] vcvars64.bat failed.
    exit /b 1
)
if not defined INCLUDE (
    echo [ERROR] vcvars64.bat ran but INCLUDE is still unset, so the compiler would
    echo         fail on stdint.h. The Windows SDK is probably not installed.
    echo         In the Visual Studio Installer, Modify -^> Individual components,
    echo         and add a "Windows 11 SDK" ^(or Windows 10 SDK^).
    exit /b 1
)
exit /b 0


rem Locates a vcpkg that has both packages built for x64-windows.
rem Sets DEPS_OK + VCPKG_INC/VCPKG_LIB/VCPKG_BIN when found, and VCPKG_DIR to the
rem best candidate for installing into when not.
rem The VCPKG_ prefix is required: bare LIB is MSVC's library search path, and
rem overwriting it drops the Windows SDK path.
:find_deps
set "DEPS_OK="
set "VCPKG_DIR="
set "VCPKG_HAVE_EXE="
if defined VCPKG_ROOT call :try_dep_dir "%VCPKG_ROOT%"
call :try_dep_dir "%LOCALAPPDATA%\vcpkg"
call :try_dep_dir "C:\vcpkg"
call :try_dep_dir "C:\dev\vcpkg"
call :try_dep_dir "%USERPROFILE%\vcpkg"
if defined DEPS_OK exit /b 0
rem Install target: an existing vcpkg checkout, else a per-user location that needs no admin rights.
rem Not collapsible to "if defined X set ... & exit /b 0": "&" runs the exit unconditionally, yielding an empty path.
if not defined VCPKG_HAVE_EXE goto :find_deps_default
set "VCPKG_DIR=%VCPKG_HAVE_EXE%"
exit /b 0
:find_deps_default
set "VCPKG_DIR=%LOCALAPPDATA%\vcpkg"
exit /b 0

:try_dep_dir
if defined DEPS_OK exit /b 0
set "CAND=%~1"
if "%CAND%"=="" exit /b 0
rem A ports tree marks a full checkout, the only kind that can be installed into: the vcpkg.exe
rem bundled with Visual Studio is manifest-mode only and rejects "vcpkg install pkg:triplet".
if exist "%CAND%\vcpkg.exe" if exist "%CAND%\ports" if not defined VCPKG_HAVE_EXE set "VCPKG_HAVE_EXE=%CAND%"
if not exist "%CAND%\installed\x64-windows\include\sqlite3.h" exit /b 0
if not exist "%CAND%\installed\x64-windows\include\openssl\sha.h" exit /b 0
set "DEPS_OK=1"
set "VCPKG_DIR=%CAND%"
set "VCPKG_INC=%CAND%\installed\x64-windows\include"
set "VCPKG_LIB=%CAND%\installed\x64-windows\lib"
set "VCPKG_BIN=%CAND%\installed\x64-windows\bin"
exit /b 0


rem One-time dependency install: fetches vcpkg (git clone, or a zip download when
rem git is unavailable) and builds sqlite3 + openssl for x64-windows.
:install_deps
echo.
echo ============================================================
echo   First-time setup: the matchmaker needs SQLite and OpenSSL.
echo   Installing them now with vcpkg into:
echo     %VCPKG_DIR%
echo.
echo   This takes a while - most of it is compiling OpenSSL - but
echo   it only happens once. Re-runs of this script skip it.
echo   Pass "nodeps" to skip and build only the relay.
echo ============================================================
echo.

if exist "%VCPKG_DIR%\vcpkg.exe" goto :install_pkgs

if not exist "%VCPKG_DIR%" mkdir "%VCPKG_DIR%" >nul 2>&1
where git >nul 2>&1
if errorlevel 1 goto :get_vcpkg_zip

echo [deps] cloning vcpkg...
rmdir "%VCPKG_DIR%" >nul 2>&1
git clone --depth 1 https://github.com/microsoft/vcpkg "%VCPKG_DIR%"
if errorlevel 1 (
    echo [WARN] git clone failed - falling back to a zip download.
    goto :get_vcpkg_zip
)
goto :bootstrap_vcpkg

:get_vcpkg_zip
rem Bootstrap needs only the source tree; it downloads the vcpkg tool binary itself.
echo [deps] downloading vcpkg archive...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $z=Join-Path $env:TEMP 'vcpkg-src.zip'; $x=Join-Path $env:TEMP 'vcpkg-src'; Invoke-WebRequest -UseBasicParsing 'https://github.com/microsoft/vcpkg/archive/refs/heads/master.zip' -OutFile $z; if (Test-Path $x) { Remove-Item -Recurse -Force $x }; Expand-Archive $z -DestinationPath $x -Force; $inner=Get-ChildItem $x -Directory | Select-Object -First 1; New-Item -ItemType Directory -Force '%VCPKG_DIR%' | Out-Null; Copy-Item (Join-Path $inner.FullName '*') '%VCPKG_DIR%' -Recurse -Force; Remove-Item -Force $z"
if errorlevel 1 (
    echo [ERROR] Could not download vcpkg. Check your internet connection.
    exit /b 1
)

:bootstrap_vcpkg
echo [deps] bootstrapping vcpkg...
call "%VCPKG_DIR%\bootstrap-vcpkg.bat" -disableMetrics
if not exist "%VCPKG_DIR%\vcpkg.exe" (
    echo [ERROR] vcpkg bootstrap failed.
    exit /b 1
)

:install_pkgs
echo.
echo [deps] building sqlite3 + openssl  ^(x64-windows^)...
echo.
rem --vcpkg-root is required: vcvars64.bat exports VCPKG_ROOT pointing at Visual
rem Studio's manifest-only vcpkg, which is adopted otherwise and rejects the install.
"%VCPKG_DIR%\vcpkg.exe" install sqlite3:x64-windows openssl:x64-windows --disable-metrics --vcpkg-root "%VCPKG_DIR%"
if errorlevel 1 (
    echo.
    echo [ERROR] vcpkg failed to install the packages.
    echo         Scroll up for its error; re-running this script resumes the work.
    exit /b 1
)
echo.
echo [deps] done.
exit /b 0


rem ---- summary ---------------------------------------------------------------
:summary
echo.
echo ============================================================
if not "%BUILT%"=="" echo   built:  %BUILT%
if not "%FAILED%"=="" echo   FAILED: %FAILED%
if defined SKIPPED (
    echo   skipped: matchmaker - SQLite/OpenSSL not installed
    if defined NODEPS echo   reason:  "nodeps" was passed - re-run without it to install them
    if defined DEPS_FAILED echo   reason:  the dependency install above failed - see its error
)
echo   output: %OUT%
echo ============================================================
if not "%FAILED%"=="" goto :fail
rem A failed dependency install exits non-zero even when the relay built.
if defined DEPS_FAILED goto :fail
if not defined NOPAUSE pause
exit /b 0

:fail
echo.
if not defined NOPAUSE pause
exit /b 1
@echo off
echo %date% %time% Play.bat start >> "%~dp0t2r-play.log" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0T2R-Play.ps1" %*
set RC=%errorlevel%
rem exit code 3 = the script already showed its error and waited for Enter
if not "%RC%"=="0" if not "%RC%"=="3" (
  echo.
  echo Play.bat: the launcher script did not run to the end ^(code %RC%^). Details: "%~dp0t2r-play.log"
  echo If PowerShell itself did not run, check that it is not blocked by your antivirus or policy.
  pause
)

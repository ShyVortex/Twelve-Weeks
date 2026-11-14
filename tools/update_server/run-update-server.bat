@echo off
rem Update server (launcher updates, /clan.json, /clanfeed.json, bug reports) on port 7002 - needs a playit tunnel to local port 7002.
rem Same data dir the admin site reads: %LOCALAPPDATA%\T2R-Factions2\update-data
cd /d "%~dp0..\.."
if not exist "%LOCALAPPDATA%\T2R-Factions2\update-data\reports" mkdir "%LOCALAPPDATA%\T2R-Factions2\update-data\reports"
python tools\update_server\server.py --data "%LOCALAPPDATA%\T2R-Factions2\update-data" --db "%LOCALAPPDATA%\T2R-Factions2\t2r.db" --daemon 127.0.0.1:7001 --status-file "%LOCALAPPDATA%\T2R-Factions2\t2r-status.json" --port 7002

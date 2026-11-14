@echo off
rem Local admin site for the live server (read-only DB, binds 127.0.0.1 only). Open http://127.0.0.1:7010/
rem Update-server data (manifests, bug reports) lives next to the DB: %LOCALAPPDATA%\T2R-Factions2\update-data
cd /d "%~dp0..\.."
if not exist "%LOCALAPPDATA%\T2R-Factions2\update-data\reports" mkdir "%LOCALAPPDATA%\T2R-Factions2\update-data\reports"
python tools\admin_site\admin.py --db "%LOCALAPPDATA%\T2R-Factions2\t2r.db" --daemon-log auto --reports "%LOCALAPPDATA%\T2R-Factions2\update-data\reports" --update-data "%LOCALAPPDATA%\T2R-Factions2\update-data" --port 7010

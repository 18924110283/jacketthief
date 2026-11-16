@echo off
chcp 936 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw cover_grab.py
) else (
    python cover_grab.py
)
@echo off
setlocal

rem the repo directory always comes first
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo the venv is missing; run scripts\setup.ps1 once
    exit /b 1
)

rem the interpreter always comes first; the arguments are always
rem pythonw.exe -m awaywatch; the tray Quit menu is the only way to
rem stop the monitor afterwards
start "ICU Presence Detector" ".venv\Scripts\pythonw.exe" -m awaywatch

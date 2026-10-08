@echo off
setlocal

rem the repo directory always comes first
cd /d "%~dp0"

git remote get origin 1>NUL 2>NUL
if errorlevel 1 (
    echo no remote configured; continuing with the local install anyway
)

echo pulling...
git pull

echo reinstalling dependencies and refreshing the lock
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1
if errorlevel 1 exit /b 1

echo update complete; start it with run.bat

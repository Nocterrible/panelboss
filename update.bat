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
if errorlevel 1 (
    echo update FAILED - the app stays closed; start it by run.bat
    echo when you have read this
    pause
    exit /b 1
)

echo update complete
if /i not "%~1"=="relaunch" exit /b 0

rem launched by the app's own update button: that instance quit so
rem these very files could be replaced - the script owes it a ride
rem home. the ping gives the new window a moment before this
rem console closes itself.
echo reopening the app...
start "" "%~dp0run.bat"
ping -n 5 127.0.0.1 >nul

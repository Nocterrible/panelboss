@echo off
setlocal

rem the repo directory always comes first
cd /d "%~dp0"

rem flags in any order: "deps" also installs requirements-optional.txt
rem (the features the app prompts for, like the hello IR bridge);
rem "relaunch" reopens the app at the end - the app's own buttons pass
rem exactly the arguments that make up their promises
set "want_relaunch="
set "want_deps="
for %%A in (%*) do (
    if /i "%%~A"=="relaunch" set "want_relaunch=1"
    if /i "%%~A"=="deps" set "want_deps=1"
)

git remote get origin 1>NUL 2>NUL
if errorlevel 1 (
    echo no remote configured; continuing with the local install anyway
)

echo pulling...
git pull

set "psargs="
if defined want_deps set "psargs=-Optional"
if defined want_deps echo including the optional dependencies
echo reinstalling dependencies and refreshing the lock
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 %psargs%
if errorlevel 1 (
    echo update FAILED - the app stays closed; start it by run.bat
    echo when you have read this
    pause
    exit /b 1
)

echo update complete
if not defined want_relaunch exit /b 0

rem launched by the app's own update button: that instance quit so
rem these very files could be replaced - the script owes it a ride
rem home. the ping gives the new window a moment before this
rem console closes itself.
echo reopening the app...
start "" "%~dp0run.bat"
ping -n 5 127.0.0.1 >nul

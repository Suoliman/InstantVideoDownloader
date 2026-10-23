@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
echo Instant - Windows Chrome companion installer
echo.
where py >nul 2>nul
if errorlevel 1 goto missing_python
py -3 scripts\install_companion.py --interactive
set "instant_result=%errorlevel%"
echo.
if not "%instant_result%"=="0" echo Installation failed. Read the message above and WINDOWS.md for help.
pause
exit /b %instant_result%
:missing_python
echo Install Python 3.11 or newer with the Python launcher, then run this installer again.
echo In Terminal: winget install --id Python.Python.3.12 --exact --source winget
echo See WINDOWS.md for the complete setup steps.
pause
exit /b 1

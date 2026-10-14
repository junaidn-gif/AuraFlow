@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto check_python
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3.12 bootstrap.py %*
    goto finish
)
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3.11 bootstrap.py %*
    goto finish
)
:check_python
where python >nul 2>nul
if errorlevel 1 goto missing
python bootstrap.py %*
goto finish
:missing
echo AuraFlow needs 64-bit Python 3.11 or 3.12.
echo Install it from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH" during installation, then run this file again.
pause
exit /b 1
:finish
if errorlevel 1 (
    echo.
    echo AuraFlow did not start. Read the error above for details.
    pause
    exit /b 1
)
endlocal

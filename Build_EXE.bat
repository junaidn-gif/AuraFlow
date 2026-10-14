@echo off
setlocal
cd /d "%~dp0"
call Start_AuraFlow.bat --install-only
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install pyinstaller==6.13.0
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name AuraFlow --collect-all mediapipe --collect-all pycaw --collect-all screen_brightness_control --hidden-import comtypes.stream --add-data "models;models" main.py
if errorlevel 1 goto failed
echo.
echo App created: dist\AuraFlow\AuraFlow.exe
echo Keep the entire dist\AuraFlow folder together when sharing it.
pause
exit /b 0
:failed
echo.
echo The Windows EXE build failed. Read the error above. The Python launcher is still available.
pause
exit /b 1

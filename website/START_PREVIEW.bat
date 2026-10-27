@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PHYSAG_VIEWER_DEPS=%~dp0.viewer-python"
"%~dp0runtime\python.exe" -B "%~dp0launch.py" %*
if errorlevel 1 pause

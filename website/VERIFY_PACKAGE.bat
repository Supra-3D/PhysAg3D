@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
"%~dp0runtime\python.exe" -B "%~dp0verify_package.py"
pause

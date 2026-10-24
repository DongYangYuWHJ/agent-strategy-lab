@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0lab.py" %*
  exit /b
)
set "LAB_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%LAB_PYTHON%" goto installed
"%LAB_PYTHON%" "%~dp0lab.py" %*
exit /b %errorlevel%
:installed
py -3 "%~dp0lab.py" %*
exit /b %errorlevel%

@echo off
setlocal
set "PYTHONPATH=%~dp0src"
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m litradar %*
  exit /b %ERRORLEVEL%
)
python -m litradar %*

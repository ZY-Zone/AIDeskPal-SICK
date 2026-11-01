@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
  py -3 bootstrap.py
  if not errorlevel 1 exit /b 0
)

where python >nul 2>&1
if not errorlevel 1 (
  python bootstrap.py
  if not errorlevel 1 exit /b 0
)

powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Python 3.11+ was not found. Install Python and enable Add Python to PATH.','AIDeskPal-SICK',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null"
exit /b 1

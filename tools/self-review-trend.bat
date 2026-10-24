@echo off
rem Double-click: updates the self-review trend report and opens it in the browser (no AI, no tokens).
python -I "%~dp0benchmark_summary.py"
if errorlevel 1 (
  echo.
  echo Could not update the report. Press a key to close.
  pause >nul
  exit /b 1
)
start "" "%~dp0..\..\self-review-trend.html"

@echo off
cd /d "%~dp0"
title Talent Pool Server
python launch.py
if errorlevel 1 (
  echo.
  echo Could not start. Check that Python and requirements are installed.
)
echo.
pause

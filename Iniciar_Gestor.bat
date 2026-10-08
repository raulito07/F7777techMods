@echo off
chcp 65001 >nul
cd /d "%~dp0"
title F7777techMods
python -m app
if errorlevel 1 (
  echo.
  echo Si falta customtkinter:  pip install -r requirements.txt
  pause
)

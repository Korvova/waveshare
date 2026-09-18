@echo off
title Unirack-1 update
rem Zapusk obnovleniya Unirack-1. Okno ne zakroetsya samo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_unirack.ps1"
echo.
pause

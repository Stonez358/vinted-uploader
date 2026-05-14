@echo off
title Playwright Setup
cd /d "%~dp0"
echo Installiere Playwright...
pip install playwright
echo.
echo Installiere Chromium Browser...
python -m playwright install chromium
echo.
echo Fertig! Du kannst jetzt posten.bat verwenden.
pause

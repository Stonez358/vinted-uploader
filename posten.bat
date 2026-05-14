@echo off
title Vinted - Artikel posten
cd /d "%~dp0"
echo.
echo Welchen Artikel-Ordner posten?
echo (Name des Unterordners aus dem 'artikel'-Verzeichnis)
echo.
set /p ORDNER="Ordnername: "
echo.
python poster.py "artikel\%ORDNER%"
echo.
pause

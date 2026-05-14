@echo off
title Listing neu generieren
cd /d "%~dp0"
echo.
echo Welchen Artikel-Ordner neu generieren?
echo (Ordner aus dem 'artikel'-Verzeichnis angeben)
echo.
set /p ORDNER="Ordnername: "
echo.
python generator.py "artikel\%ORDNER%" --force
echo.
pause

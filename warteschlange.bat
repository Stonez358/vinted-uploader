@echo off
title Vinted - Warteschlange
cd /d "%~dp0"
echo.
echo ================================================
echo   VINTED WARTESCHLANGE
echo ================================================
echo   Mehrere Artikel nacheinander als Entwurf
echo   speichern. Ordnernamen eingeben, einer pro
echo   Zeile. Leere Zeile = Starten.
echo ================================================
echo.

set LISTE=
set COUNT=0

:eingabe
set /p ORDNER="Ordner (oder Enter zum Starten): "
if "%ORDNER%"=="" goto starten
set LISTE=%LISTE% "%ORDNER%"
set /a COUNT+=1
echo   + %ORDNER% hinzugefuegt
goto eingabe

:starten
if %COUNT%==0 (
    echo Keine Artikel eingegeben.
    pause
    exit
)

echo.
echo Starte Verarbeitung von %COUNT% Artikel(n)...
echo.

for %%A in (%LISTE%) do (
    echo ------------------------------------------------
    echo Verarbeite: %%A
    echo ------------------------------------------------
    python poster.py "artikel\%%~A"
    echo.
)

echo ================================================
echo   Alle %COUNT% Artikel verarbeitet!
echo ================================================
pause

@echo off
rem MechLoadout Renamer - lanceur Windows (double-clic)
cd /d "%~dp0"

rem "py" est le lanceur officiel de python.org ; "python" peut n'etre que le
rem raccourci du Microsoft Store qui ouvre le Store au lieu de Python.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 mwobuildmanager.py
    goto :end
)
where python >nul 2>nul
if %errorlevel%==0 (
    python mwobuildmanager.py
    goto :end
)

echo Python 3 est introuvable / Python 3 was not found.
echo Installe-le depuis / Install it from: https://www.python.org/downloads/
echo (coche "Add python.exe to PATH" / tick "Add python.exe to PATH")
pause
exit /b 1

:end
rem garde la fenetre ouverte si le programme s'est arrete sur une erreur
if errorlevel 1 pause

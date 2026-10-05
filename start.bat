@echo off
rem Prospect Solution launcher: prepares the Python environment on first run, then starts the application.
setlocal
cd /d "%~dp0"
set "PYTHON_LAUNCHER=python"
where py >nul 2>nul && set "PYTHON_LAUNCHER=py -3"
if not exist ".venv\Scripts\python.exe" (
    echo [Prospect Solution] Creation de l'environnement Python...
    %PYTHON_LAUNCHER% -m venv .venv || goto :python_missing
)
set "VENV_PYTHON=.venv\Scripts\python.exe"
echo [Prospect Solution] Verification des dependances...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :installation_failed
"%VENV_PYTHON%" -m playwright install chromium || goto :installation_failed
echo [Prospect Solution] Demarrage : l'interface va s'ouvrir dans votre navigateur.
"%VENV_PYTHON%" -m app
goto :eof
:python_missing
echo Python 3.11 ou plus recent est requis : https://www.python.org/downloads/
echo Pendant l'installation, cochez "Add python.exe to PATH".
pause
exit /b 1
:installation_failed
echo L'installation des dependances a echoue. Verifiez votre connexion Internet puis relancez.
pause
exit /b 1

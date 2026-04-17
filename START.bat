@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: ---- Check folder structure ----
if not exist "_engine\app.py" (
    echo  [!] Folder structure is broken.
    echo  Please re-download and unzip the folder again.
    echo.
    pause
    exit /b 1
)

:: ---- Check outputs folder is writable ----
echo test > "outputs\_test.txt" 2>nul
if errorlevel 1 (
    echo.
    echo  [!] Cannot write to the outputs folder.
    echo  Move this folder to your Desktop or Documents and try again.
    echo.
    pause
    exit /b 1
)
del "outputs\_test.txt" >nul 2>&1

cd /d "_engine"

:: ---- Find Python ----
set PYTHON_CMD=

py -3 --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=py -3 & goto :python_ready )

python --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=python & goto :python_ready )

python3 --version >nul 2>&1
if not errorlevel 1 ( set PYTHON_CMD=python3 & goto :python_ready )

echo.
echo  [!] Python not found. Run SETUP.bat first.
echo.
pause
exit /b 1

:python_ready

:: ---- Check dependencies are installed ----
%PYTHON_CMD% -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Required libraries are not installed.
    echo  Please run SETUP.bat first, then try again.
    echo.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   990 Compensation Pipeline is starting...
echo  ============================================
echo.
echo  Your browser will open automatically in a few seconds.
echo  If it does not open, check above in this window for the correct URL.
echo.
echo  NOTE: If Windows asks about firewall access, click Allow access.
echo.
echo  To stop the server: close this window.
echo.

set PYTHONWARNINGS=ignore
%PYTHON_CMD% app.py

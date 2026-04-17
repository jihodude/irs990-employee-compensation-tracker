@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo  ============================================
echo   990 Pipeline -- Windows Setup
echo  ============================================
echo.
echo  Checking your computer has everything needed...
echo  This only needs to be run ONCE.
echo.

echo  [STEP 1] Checking current directory...
echo  Current directory: %CD%
echo.

:: ---- Check folder structure ----
echo  [STEP 2] Looking for _engine\app.py...
if not exist "_engine\app.py" (
    echo.
    echo  [!] Folder structure is broken.
    echo  Could not find: %CD%\_engine\app.py
    echo  Please re-download and unzip the folder again.
    echo.
    pause
    exit /b 1
)
echo  Found _engine\app.py -- OK
echo.

cd /d "_engine"
echo  [STEP 3] Changed to _engine directory: %CD%
echo.

:: ---- Find Python ----
echo  [STEP 4] Searching for Python...
set PYTHON_CMD=

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3
    echo   Found Python (py -3)
    goto :python_found
)

python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
    echo   Found Python (python)
    goto :python_found
)

python3 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python3
    echo   Found Python (python3)
    goto :python_found
)

echo.
echo  [!] Python is NOT installed on this computer.
echo.
echo  To install Python (takes about 3 minutes):
echo    1. A browser window will open to python.org.
echo    2. Click the big Download Python button.
echo    3. Run the installer.
echo    4. IMPORTANT: Check "Add Python to PATH" before clicking Install Now.
echo    5. Come back and run SETUP.bat again.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:python_found
echo.
echo  [STEP 5] Installing required libraries...
echo  (This may take 1-2 minutes on first run)
echo.

%PYTHON_CMD% -m pip install -r requirements.txt --quiet --disable-pip-version-check
if not errorlevel 1 goto :install_done

echo  Standard install failed. Trying user install...
%PYTHON_CMD% -m pip install --user -r requirements.txt --quiet --disable-pip-version-check
if not errorlevel 1 goto :install_done

echo.
echo  [!] Could not install required libraries.
echo  Try right-clicking SETUP.bat and choosing "Run as administrator"
echo  then run it again.
echo.
pause
exit /b 1

:install_done
echo  Libraries installed -- OK
echo.

:: ---- Verify libraries are actually importable ----
echo  [STEP 6] Verifying libraries...

%PYTHON_CMD% -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Libraries installed but Python cannot find them.
    echo  Try restarting your computer, then run START.bat.
    echo  If it still fails, contact your IT department.
    echo.
    pause
    exit /b 1
)

:: ---- Health check summary ----
echo.
echo  ============================================
echo   System Check
echo  ============================================
echo.
%PYTHON_CMD% --version

%PYTHON_CMD% -c "import flask" >nul 2>&1
if errorlevel 1 ( echo   Flask      FAILED ) else ( echo   Flask      OK )

%PYTHON_CMD% -c "import pandas" >nul 2>&1
if errorlevel 1 ( echo   Pandas     FAILED ) else ( echo   Pandas     OK )

%PYTHON_CMD% -c "import lxml" >nul 2>&1
if errorlevel 1 ( echo   lxml       FAILED ) else ( echo   lxml       OK )

%PYTHON_CMD% -c "import requests" >nul 2>&1
if errorlevel 1 ( echo   Requests   FAILED ) else ( echo   Requests   OK )

%PYTHON_CMD% -c "import inflate64" >nul 2>&1
if errorlevel 1 ( echo   inflate64  FAILED ) else ( echo   inflate64  OK )

echo.
echo  ============================================
echo.
echo  All good! Double-click START.bat to run the pipeline.
echo.
pause

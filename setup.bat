@echo off
REM ============================================================
REM  setup.bat -- run this ONCE before the first run.bat
REM  Creates a separate virtual environment per backend service
REM  and installs its dependencies, then installs the frontend's
REM  npm packages. Safe to re-run later if you add new packages.
REM ============================================================

setlocal enabledelayedexpansion
set ROOT=%~dp0

echo.
echo This will take a while the first time (each service installs
echo its own PyTorch/etc into its own isolated environment). That's
echo expected -- subsequent runs of run.bat will be fast.
echo.

for %%S in (gateway edge_ingestion spectral_service prosody_service consistency_service fusion_engine alerting_service fraud_ledger_service) do (
    echo.
    echo ==== Setting up backend\%%S ====
    cd /d "%ROOT%backend\%%S"
    if not exist venv (
        python -m venv venv
    )
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo *** pip install failed for %%S -- see the error above. ***
        echo *** Fix it, then re-run setup.bat.                     ***
        pause
        exit /b 1
        )
    if "%%S"=="gateway" (
        echo Generating gRPC proto stubs for gateway...
        python generate_proto.py
    )
    call venv\Scripts\deactivate.bat
)

echo.
echo ==== Setting up frontend (npm install) ====
cd /d "%ROOT%frontend"
call npm install
if errorlevel 1 (
    echo.
    echo *** npm install failed -- make sure Node.js is installed. ***
    echo *** Download it from https://nodejs.org if needed.        ***
    pause
    exit /b 1
)

cd /d "%ROOT%"
echo.
echo ============================================================
echo  Setup complete. Run run.bat to start every service.
echo ============================================================


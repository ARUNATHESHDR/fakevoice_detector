@echo off
REM ============================================================
REM  run.bat -- starts all backend microservices, gRPC server,
REM  and the frontend console. Run setup.bat first once.
REM ============================================================

setlocal enabledelayedexpansion
set ROOT=%~dp0

REM --- load .env if present (simple KEY=VALUE parser, ignores blank/# lines) ---
if exist "%ROOT%.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ROOT%.env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

REM --- service-to-service URLs (native/no-Docker mode: everything is localhost) ---
set GATEWAY_URL=http://localhost:8000/ingest/window
set SPECTRAL_URL=http://localhost:8002/analyze
set PROSODY_URL=http://localhost:8003/analyze
set CONSISTENCY_URL=http://localhost:8004/analyze
set FUSION_URL=http://localhost:8005/fuse
set ALERTING_URL=http://localhost:8006/alert
set SCORE_UPDATE_URL=http://localhost:8006/score_update
set FRAUD_LEDGER_URL=http://localhost:8007/ledger/append
set MOCK_NOTIFICATIONS=true

REM --- what the BROWSER connects to ---
set NEXT_PUBLIC_GATEWAY_URL=http://localhost:8000
set NEXT_PUBLIC_EDGE_WS_URL=ws://localhost:8001/ws/audio
set NEXT_PUBLIC_ALERTING_WS_URL=ws://localhost:8006/ws/alerts
set NEXT_PUBLIC_LEDGER_URL=http://localhost:8007

echo Starting all services in separate windows...
echo Each window's title tells you which service it is and which port.
echo.

start "1-GatewayREST :8000" cmd /k "cd /d "%ROOT%backend\gateway" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 >nul

start "1b-GatewaygRPC :50051" cmd /k "cd /d "%ROOT%backend\gateway" && call venv\Scripts\activate.bat && python grpc_server.py"
timeout /t 1 >nul

start "2-EdgeIngestion :8001" cmd /k "cd /d "%ROOT%backend\edge_ingestion" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload"
timeout /t 2 >nul

start "3-SpectralService :8002" cmd /k "cd /d "%ROOT%backend\spectral_service" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload"
timeout /t 2 >nul

start "4-ProsodyService :8003" cmd /k "cd /d "%ROOT%backend\prosody_service" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8003 --reload"
timeout /t 2 >nul

start "5-ConsistencyService :8004" cmd /k "cd /d "%ROOT%backend\consistency_service" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8004 --reload"
timeout /t 2 >nul

start "6-FusionEngine :8005" cmd /k "cd /d "%ROOT%backend\fusion_engine" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8005 --reload"
timeout /t 2 >nul

start "7-AlertingService :8006" cmd /k "cd /d "%ROOT%backend\alerting_service" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8006 --reload"
timeout /t 2 >nul

start "8-FraudLedgerService :8007" cmd /k "cd /d "%ROOT%backend\fraud_ledger_service" && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8007 --reload"
timeout /t 2 >nul

start "9-Frontend :3000" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo.
echo ============================================================
echo  All services launched!
echo  REST API Gateway  : http://localhost:8000
echo  gRPC Server       : localhost:50051
echo  Frontend Dashboard: http://localhost:3000
echo ============================================================

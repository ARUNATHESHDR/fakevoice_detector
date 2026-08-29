@echo off
REM ============================================================
REM  stop.bat -- kills all backend services that run.bat started
REM ============================================================

echo Stopping all services...

REM Kill python processes on the known ports
for %%p in (8000 8001 8002 8003 8004 8005 8006 8007 50051 3000) do (
    for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :%%p ^| findstr LISTENING') do (
        taskkill /F /PID %%a >nul 2>&1
    )
)

echo All services stopped.

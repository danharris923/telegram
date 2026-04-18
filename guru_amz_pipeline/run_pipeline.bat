@echo off
setlocal
cd /d "%~dp0"

echo === Phase 1: guru_scrape.py ===
python guru_scrape.py
if errorlevel 1 (
    echo [X] Phase 1 failed with exit code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo === Phase 2: amz_scrape.py ===
python amz_scrape.py
if errorlevel 1 (
    echo [X] Phase 2 failed with exit code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo === Phase 3: finalize.py ===
python finalize.py
if errorlevel 1 (
    echo [X] Phase 3 failed with exit code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo === Pipeline complete ===
pause

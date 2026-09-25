@echo off
REM ============================================================
REM  The Ultimate Image Processing - one-command setup (Windows)
REM  Double-click this file on a fresh laptop and it will:
REM    1. create the virtual environment
REM    2. install all dependencies
REM    3. create the database
REM    4. seed demo data + run the self-tests
REM    5. start the server at http://127.0.0.1:8000
REM ============================================================
cd /d "%~dp0"

echo [1/5] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    echo       and tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [2/5] Installing dependencies (Django, OpenCV, NumPy, Pillow)...
venv\Scripts\python -m pip install --upgrade pip --quiet
venv\Scripts\pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)

echo [3/5] Creating database...
venv\Scripts\python manage.py migrate

echo [4/5] Seeding demo data + running self-tests...
venv\Scripts\python seed_demo.py
if errorlevel 1 (
    echo WARNING: some self-tests failed - the site should still work.
)

echo [5/5] Starting server at http://127.0.0.1:8000 ...
echo.
echo   Admin panel:  http://127.0.0.1:8000/admin/   (admin / admin1234)
echo   Press CTRL+C to stop.
echo.
start "" http://127.0.0.1:8000
venv\Scripts\python manage.py runserver

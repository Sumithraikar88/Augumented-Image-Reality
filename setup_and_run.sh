#!/usr/bin/env bash
# ============================================================
#  The Ultimate Image Processing - one-command setup (macOS/Linux)
#  Run:  bash setup_and_run.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo "[1/5] Creating virtual environment..."
python3 -m venv venv

echo "[2/5] Installing dependencies (Django, OpenCV, NumPy, Pillow)..."
venv/bin/python -m pip install --upgrade pip --quiet
venv/bin/pip install -r requirements.txt --quiet

echo "[3/5] Creating database..."
venv/bin/python manage.py migrate

echo "[4/5] Seeding demo data + running self-tests..."
venv/bin/python seed_demo.py || echo "WARNING: some self-tests failed - the site should still work."

echo "[5/5] Starting server at http://127.0.0.1:8000 ..."
echo "  Admin panel: http://127.0.0.1:8000/admin/  (admin / admin1234)"
echo "  Press CTRL+C to stop."
venv/bin/python manage.py runserver

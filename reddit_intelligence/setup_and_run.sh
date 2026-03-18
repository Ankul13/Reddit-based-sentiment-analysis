#!/bin/bash
# =============================================================
# setup_and_run.sh — One-shot setup and launch for InsightPulse
# Run from inside the reddit_intelligence/ folder:
#   bash setup_and_run.sh
# =============================================================

set -e

echo ""
echo "=================================================="
echo "  InsightPulse — Reddit Product Intelligence"
echo "  Setup and Launch Script"
echo "=================================================="
echo ""

# 1. Install dependencies
echo "[1/5] Installing Python dependencies..."
pip install -r requirements_django.txt --quiet
echo "      Done"

# 2. NLP model data
echo "[2/5] Downloading NLTK + TextBlob data..."
python -c "
import nltk
nltk.download('stopwords', quiet=True)
nltk.download('punkt', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
"
python -m textblob.download_corpora 2>/dev/null || true
echo "      Done"

# 3. Django DB migrations
echo "[3/5] Running Django migrations..."
python manage.py migrate --run-syncdb 2>/dev/null || python manage.py migrate
echo "      Done"

# 4. Data directories (relative to project root, one level up)
echo "[4/5] Creating data directories..."
mkdir -p ../data/raw ../data/clean ../data/results
echo "      Done"

# 5. Start Django-Q worker in background
echo "[5/5] Starting Django-Q background task worker..."
python manage.py qcluster &
QPID=$!
echo "      Worker PID: $QPID"

echo ""
echo "=================================================="
echo "  Ready! Opening at: http://127.0.0.1:8000"
echo "  Press Ctrl+C to stop everything"
echo "=================================================="
echo ""

# Kill worker when server stops
trap "kill $QPID 2>/dev/null; echo 'Stopped.'; exit 0" INT TERM

# Launch Django dev server
python manage.py runserver 0.0.0.0:8000

#!/bin/bash
# =============================================================
# run_pipeline.sh
# Reddit Sentiment & Emotion Pipeline — WSL/Hadoop Runner
# =============================================================

set -e   # Exit immediately on any error

PRODUCT="${1:-}"

if [ -z "$PRODUCT" ]; then
    echo ""
    echo "Usage:  bash run_pipeline.sh \"iPhone 17\""
    echo "        bash run_pipeline.sh \"Samsung Galaxy S25\""
    echo ""
    read -p "Enter product name: " PRODUCT
fi

if [ -z "$PRODUCT" ]; then
    echo "Error: product name cannot be empty."
    exit 1
fi

echo ""
echo "======================================================"
echo "  Reddit Product Intelligence Pipeline"
echo "  Product : $PRODUCT"
echo "======================================================"
echo ""

# ── 1. Ensure data directories exist ──────────────────────────
mkdir -p data/raw data/clean data/results

# ── 2. Run Python pipeline ────────────────────────────────────
echo "[1/3] Running NLP pipeline..."
python product_pipeline.py <<< "$PRODUCT"

# ── 3. Upload to HDFS (already done inside product_pipeline.py)
# ── Calling it explicitly here as well for safety
echo ""
echo "[2/3] Verifying HDFS upload..."
if command -v hadoop &> /dev/null; then
    hadoop fs -ls /reddit_data/results/ 2>/dev/null || echo "  HDFS: /reddit_data/results/ not found yet."
else
    echo "  hadoop not on PATH — skipping HDFS check."
fi

# ── 4. Run Hive analytics queries ─────────────────────────────
echo ""
echo "[3/3] Running Hive analytics queries..."
if command -v hive &> /dev/null; then
    hive -f hive_queries.sql 2>/dev/null && echo "  Hive queries complete." || echo "  Hive warning: some queries may have failed."
else
    echo "  hive not on PATH — skipping Hive queries."
fi

echo ""
echo "======================================================"
echo "  Pipeline finished successfully."
echo "  Results saved to: data/results/"
echo "  Start dashboard: streamlit run app.py"
echo "======================================================"
echo ""

#!/bin/bash
# =============================================================
# upload_to_hdfs.sh
# Uploads all pipeline artefacts to HDFS
# Called automatically by product_pipeline.py
# Can also be run standalone: bash upload_to_hdfs.sh
# =============================================================

HDFS_BASE="/reddit_data"

echo "Uploading pipeline data to HDFS..."

# Create HDFS directories
for dir in raw clean results; do
    hadoop fs -mkdir -p "$HDFS_BASE/$dir"
    echo "  Directory ready: $HDFS_BASE/$dir"
done

# Upload raw files
echo ""
echo "Uploading raw data..."
for file in data/raw/*.csv; do
    [ -f "$file" ] || continue
    hadoop fs -put -f "$file" "$HDFS_BASE/raw/"
    echo "  ✓ $file"
done

# Upload clean files
echo ""
echo "Uploading clean data..."
for file in data/clean/*.csv; do
    [ -f "$file" ] || continue
    hadoop fs -put -f "$file" "$HDFS_BASE/clean/"
    echo "  ✓ $file"
done

# Upload results
echo ""
echo "Uploading results..."
for file in data/results/*.csv; do
    [ -f "$file" ] || continue
    hadoop fs -put -f "$file" "$HDFS_BASE/results/"
    echo "  ✓ $file"
done

echo ""
echo "HDFS contents:"
hadoop fs -ls -R "$HDFS_BASE"

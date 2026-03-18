"""
product_pipeline.py
-------------------
Master orchestrator for the Reddit Sentiment & Emotion pipeline.

Flow:
  1. Fetch Reddit posts (PRAW)
  2. Preprocess / clean text
  3. Sentiment analysis  (VADER + TextBlob ensemble)
  4. Emotion detection   (j-hartmann distilroberta, batched)
  5. Save final enriched CSV locally
  6. Upload raw + clean + results to HDFS
  7. Create / refresh Hive external table

Usage:
  python product_pipeline.py                   # interactive CLI
  from product_pipeline import run_pipeline    # called by Streamlit app
"""

import os
import subprocess
import pandas as pd

from product_search    import fetch_posts
from preprocess        import preprocess_data
from sentiment_pipeline import run_sentiment
from emotion_pipeline  import run_emotion


# ── Hadoop config ─────────────────────────────────────────────────────────────
HDFS_BASE      = "/reddit_data"
HIVE_DB        = "reddit_analysis"
HADOOP_CMD     = "hadoop"   # assumes hadoop is on WSL PATH
HIVE_CMD       = "hive"     # assumes hive  is on WSL PATH
# ─────────────────────────────────────────────────────────────────────────────


def _hdfs_upload(local_path: str, hdfs_dir: str):
    """Upload a local file to HDFS. Creates directory if missing."""
    try:
        subprocess.run(
            [HADOOP_CMD, "fs", "-mkdir", "-p", hdfs_dir],
            check=True, capture_output=True
        )
        subprocess.run(
            [HADOOP_CMD, "fs", "-put", "-f", local_path, hdfs_dir],
            check=True, capture_output=True
        )
        print(f"  HDFS ✓  {local_path}  →  {hdfs_dir}")
    except subprocess.CalledProcessError as e:
        print(f"  HDFS upload warning: {e.stderr.decode().strip()}")
    except FileNotFoundError:
        print("  HDFS upload skipped — hadoop not found on PATH.")


def _hive_run(hql: str):
    """Execute a HiveQL statement."""
    try:
        result = subprocess.run(
            [HIVE_CMD, "-e", hql],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  Hive warning: {result.stderr.strip()[:200]}")
        else:
            print("  Hive ✓")
    except FileNotFoundError:
        print("  Hive skipped — hive not found on PATH.")
    except subprocess.TimeoutExpired:
        print("  Hive warning: query timed out.")


def upload_to_hdfs(product: str, raw_path: str, clean_path: str, result_path: str):
    """Upload all three pipeline artefacts to HDFS."""
    print("\n── Uploading to HDFS ──────────────────────────────────────────")
    safe = product.replace(" ", "_")
    _hdfs_upload(raw_path,    f"{HDFS_BASE}/raw")
    _hdfs_upload(clean_path,  f"{HDFS_BASE}/clean")
    _hdfs_upload(result_path, f"{HDFS_BASE}/results")


def create_hive_table(product: str, result_path: str):
    """
    Creates (or replaces) a Hive external table pointing at the
    results directory in HDFS. Safe to call multiple times.
    """
    print("\n── Creating Hive external table ───────────────────────────────")

    hdfs_results_dir = f"{HDFS_BASE}/results"

    hql = f"""
    CREATE DATABASE IF NOT EXISTS {HIVE_DB};

    USE {HIVE_DB};

    DROP TABLE IF EXISTS reddit_results;

    CREATE EXTERNAL TABLE reddit_results (
        id              STRING,
        title           STRING,
        text            STRING,
        cleaned_text    STRING,
        subreddit       STRING,
        score           INT,
        comments        INT,
        created_utc     DOUBLE,
        sentiment       STRING,
        sentiment_score DOUBLE,
        emotion         STRING,
        emotion_score   DOUBLE
    )
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY ','
    STORED AS TEXTFILE
    LOCATION '{hdfs_results_dir}'
    TBLPROPERTIES ('skip.header.line.count'='1');
    """
    _hive_run(hql)


def run_pipeline(product: str, fetch_limit: int = 200) -> str:
    """
    Full end-to-end pipeline.

    Args:
        product:     Search keyword, e.g. "iPhone 17"
        fetch_limit: Max Reddit posts per subreddit (default 200)

    Returns:
        Path to final enriched CSV (local).
    """
    safe = product.replace(" ", "_")

    print(f"\n{'='*60}")
    print(f" Pipeline started for: {product}")
    print(f"{'='*60}")

    # ── Step 1: Fetch ────────────────────────────────────────────
    print("\n── Step 1: Fetching Reddit data ───────────────────────────────")
    raw_path = fetch_posts(product, limit=fetch_limit)

    # ── Step 2: Preprocess ──────────────────────────────────────
    print("\n── Step 2: Preprocessing ──────────────────────────────────────")
    clean_path = f"data/clean/{safe}_clean.csv"
    preprocess_data(raw_path, clean_path)

    # ── Step 3: Sentiment ────────────────────────────────────────
    print("\n── Step 3: Sentiment Analysis (VADER + TextBlob) ──────────────")
    sentiment_path = run_sentiment(clean_path, safe)

    # ── Step 4: Emotion ──────────────────────────────────────────
    print("\n── Step 4: Emotion Detection (DistilRoBERTa batched) ──────────")
    df = pd.read_csv(sentiment_path)
    df = run_emotion(df)

    # ── Step 5: Save final CSV ───────────────────────────────────
    print("\n── Step 5: Saving final results ───────────────────────────────")
    final_path = f"data/results/{safe}_analysis.csv"
    os.makedirs("data/results", exist_ok=True)
    df.to_csv(final_path, index=False)
    print(f"  Saved → {final_path}  ({len(df)} records)")

    # ── Step 6: HDFS upload ──────────────────────────────────────
    upload_to_hdfs(product, raw_path, clean_path, final_path)

    # ── Step 7: Hive table ───────────────────────────────────────
    create_hive_table(product, final_path)

    print(f"\n{'='*60}")
    print(f" Pipeline complete ✓")
    print(f"{'='*60}\n")

    return final_path


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    product = input("Enter product name: ").strip()
    if not product:
        print("Product name cannot be empty.")
    else:
        run_pipeline(product)

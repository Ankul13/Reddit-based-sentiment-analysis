"""
tasks.py
--------
Background task that runs the full NLP pipeline.
Called by Django-Q — runs in a separate worker process.
Updates AnalysisJob progress in real time so the frontend
can poll and show a live progress bar.

Steps and their progress weights:
  fetching       0  → 15%
  preprocessing  15 → 30%
  sentiment      30 → 55%
  emotion        55 → 80%
  hdfs           80 → 90%
  hive           90 → 100%
"""

import os
import sys
import django
import pandas as pd
from django.utils import timezone

# Ensure Django is set up when this module runs in the worker
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reddit_intelligence.settings')


def _update(job_id: int, status: str, progress: int, message: str = ""):
    """Helper — saves job status to DB so the frontend AJAX can read it."""
    from core.models import AnalysisJob
    AnalysisJob.objects.filter(pk=job_id).update(
        status=status,
        progress=progress,
        status_message=message,
    )


def run_analysis_task(job_id: int):
    """
    Full pipeline task. Receives a job_id, loads the AnalysisJob,
    runs each pipeline step with live progress updates.
    """
    from core.models import AnalysisJob, AnalysisResult

    try:
        job = AnalysisJob.objects.get(pk=job_id)
    except AnalysisJob.DoesNotExist:
        return

    # Guard: if already complete or failed, do NOT re-run
    # This prevents Django-Q retry loop from executing the task multiple times
    if job.status in ('complete', 'failed'):
        print(f"  Task guard: job {job_id} already {job.status}, skipping.")
        return

    # Mark as running immediately to block any concurrent re-execution
    from django.db import transaction
    with transaction.atomic():
        fresh = AnalysisJob.objects.select_for_update().get(pk=job_id)
        if fresh.status not in ('pending', 'fetching', 'preprocessing',
                                'sentiment', 'emotion', 'hdfs', 'hive'):
            print(f"  Task guard: job {job_id} status={fresh.status}, skipping.")
            return

    product     = job.product
    fetch_limit = job.fetch_limit
    safe        = product.replace(" ", "_")

    try:
        # ── Step 1 — Fetch Reddit data ────────────────────────────────────
        _update(job_id, 'fetching', 5, f'Connecting to Reddit API for "{product}"…')

        from product_search import fetch_posts
        raw_path = fetch_posts(product, limit=fetch_limit)

        _update(job_id, 'fetching', 15, f'Fetched Reddit posts → {raw_path}')

        # ── Step 2 — Preprocess ───────────────────────────────────────────
        _update(job_id, 'preprocessing', 18, 'Cleaning text — removing URLs, noise, stopwords…')

        from preprocess import preprocess_data
        clean_path = f"data/clean/{safe}_clean.csv"
        os.makedirs("data/clean", exist_ok=True)
        preprocess_data(raw_path, clean_path)

        df = pd.read_csv(clean_path)
        total = len(df)

        _update(job_id, 'preprocessing', 30,
                f'Preprocessed {total:,} posts — ready for analysis')

        # ── Step 3 — Sentiment ────────────────────────────────────────────
        _update(job_id, 'sentiment', 33, 'Running VADER + TextBlob sentiment ensemble…')

        from sentiment_pipeline import run_sentiment
        sentiment_path = run_sentiment(clean_path, safe)

        _update(job_id, 'sentiment', 55,
                'Sentiment complete — positive / negative / neutral labels assigned')

        # ── Step 4 — Emotion ──────────────────────────────────────────────
        _update(job_id, 'emotion', 58,
                'Loading DistilRoBERTa emotion model (batched inference)…')

        from emotion_pipeline import run_emotion
        df = pd.read_csv(sentiment_path)
        df = run_emotion(df)

        _update(job_id, 'emotion', 78, 'Emotion detection complete')

        # ── Step 5 — Save final CSV ───────────────────────────────────────
        final_path = f"data/results/{safe}_analysis.csv"
        os.makedirs("data/results", exist_ok=True)
        df.to_csv(final_path, index=False)

        _update(job_id, 'emotion', 80, f'Results saved locally → {final_path}')

        # Step 6 - HDFS upload
        _update(job_id, 'hdfs', 82, 'Uploading raw, clean, and results to HDFS...')

        import shutil
        hadoop_ok = False

        if shutil.which('hadoop'):
            try:
                for local, hdfs_dir in [
                    (raw_path,    '/reddit_data/raw'),
                    (clean_path,  '/reddit_data/clean'),
                    (final_path,  '/reddit_data/results'),
                ]:
                    subprocess.run(['hadoop', 'fs', '-mkdir', '-p', hdfs_dir],
                                   capture_output=True, timeout=30)
                    r = subprocess.run(['hadoop', 'fs', '-put', '-f', local, hdfs_dir],
                                       capture_output=True, timeout=60)
                hadoop_ok = True
                _update(job_id, 'hdfs', 90, 'HDFS upload complete')
            except Exception as hdfs_err:
                _update(job_id, 'hdfs', 90, f'HDFS error: {str(hdfs_err)[:120]}')
        else:
            _update(job_id, 'hdfs', 90,
                    'Hadoop not on PATH. Start Hadoop first, then run: bash upload_to_hdfs.sh')

        # Step 7 - Hive table
        _update(job_id, 'hive', 92, 'Creating Hive external table...')

        if shutil.which('hive') and hadoop_ok:
            try:
                hql = (
                    "CREATE DATABASE IF NOT EXISTS reddit_analysis; "
                    "USE reddit_analysis; "
                    "DROP TABLE IF EXISTS reddit_results; "
                    "CREATE EXTERNAL TABLE reddit_results ("
                    "id STRING, title STRING, text STRING, cleaned_text STRING, "
                    "subreddit STRING, score INT, comments INT, created_utc DOUBLE, "
                    "sentiment STRING, sentiment_score DOUBLE, "
                    "emotion STRING, emotion_score DOUBLE"
                    ") ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' "
                    "STORED AS TEXTFILE "
                    "LOCATION '/reddit_data/results' "
                    "TBLPROPERTIES ('skip.header.line.count'='1');"
                )
                result = subprocess.run(['hive', '-e', hql],
                                        capture_output=True, text=True, timeout=180)
                if result.returncode == 0:
                    _update(job_id, 'hive', 97, 'Hive table created successfully')
                else:
                    NOISE = ('SLF4J', 'log4j', 'WARN', 'INFO', 'Hive Session', 'OK', 'Time taken')
                    real_err = '\n'.join(
                        l for l in result.stderr.split('\n')
                        if l.strip() and not any(n in l for n in NOISE)
                    )
                    _update(job_id, 'hive', 97,
                            f'Hive warning: {real_err[:200]}' if real_err else 'Hive step done')
            except Exception as hive_err:
                _update(job_id, 'hive', 97, f'Hive error: {str(hive_err)[:120]}')
        else:
            _update(job_id, 'hive', 97,
                    'Hive skipped - start Hive metastore, then run: hive -f hive_queries.sql')

        # ── Step 8 — Save results to Django DB ───────────────────────────
        _update(job_id, 'complete', 99, 'Saving results to database…')

        df = pd.read_csv(final_path)

        bulk_results = []
        for _, row in df.iterrows():
            bulk_results.append(AnalysisResult(
                job             = job,
                post_id         = str(row.get('id', '')),
                title           = str(row.get('title', ''))[:500],
                text            = str(row.get('text', ''))[:2000],
                cleaned_text    = str(row.get('cleaned_text', ''))[:2000],
                subreddit       = str(row.get('subreddit', '')),
                score           = int(row.get('score', 0) or 0),
                comments        = int(row.get('comments', 0) or 0),
                created_utc     = float(row.get('created_utc', 0) or 0),
                sentiment       = str(row.get('sentiment', 'neutral')),
                sentiment_score = float(row.get('sentiment_score', 0) or 0),
                emotion         = str(row.get('emotion', 'neutral')),
                emotion_score   = float(row.get('emotion_score', 0) or 0),
            ))

        AnalysisResult.objects.bulk_create(bulk_results, batch_size=500)

        # ── Mark complete ─────────────────────────────────────────────────
        AnalysisJob.objects.filter(pk=job_id).update(
            status        = 'complete',
            progress      = 100,
            status_message= f'Analysis complete — {total:,} posts processed.',
            total_posts   = total,
            result_path   = final_path,
            completed_at  = timezone.now(),
        )

    except Exception as e:
        import traceback
        AnalysisJob.objects.filter(pk=job_id).update(
            status        = 'failed',
            progress      = 0,
            error_message = traceback.format_exc()[:2000],
            status_message= f'Error: {str(e)[:200]}',
        )


def task_complete_hook(task):
    """
    Django-Q hook called after task finishes (success or failure).
    Ensures the task is acknowledged and never re-queued.
    """
    if not task.success:
        print(f"  Task hook: task {task.id} failed — marking job as failed.")
        # Try to find the job_id from task args and mark it failed
        try:
            if task.args:
                job_id = task.args[0]
                from core.models import AnalysisJob
                AnalysisJob.objects.filter(pk=job_id, status__in=(
                    'pending','fetching','preprocessing','sentiment','emotion','hdfs','hive'
                )).update(status='failed', error_message=str(task.result)[:500])
        except Exception:
            pass
    else:
        print(f"  Task hook: task {task.id} completed successfully.")
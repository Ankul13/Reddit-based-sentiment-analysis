"""
views.py
--------
All Django views for the Reddit Product Intelligence platform.

Pages:
  home        GET  /                  Landing page
  analyze     GET  /analyze/          Analysis setup form
  run_analysis POST /analyze/run/     Starts background job, returns job_id
  job_status  GET  /analyze/status/<job_id>/  AJAX polling endpoint
  dashboard   GET  /dashboard/<job_id>/       Results dashboard
  history     GET  /history/          All past analyses
  hive        GET  /hive/             Hive query results
  about       GET  /about/            How it works
"""

import json
import subprocess
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from collections import Counter
import re

from core.models import AnalysisJob, AnalysisResult


# ── Home ──────────────────────────────────────────────────────────────────────

def home(request):
    recent_jobs    = AnalysisJob.objects.filter(status='complete').order_by('-created_at')[:4]
    total_analyses = AnalysisJob.objects.filter(status='complete').count()
    total_posts    = sum(j.total_posts for j in AnalysisJob.objects.filter(status='complete'))

    pipeline_steps = [
        'Reddit API (PRAW)', 'Text Preprocessing', 'VADER + TextBlob Sentiment',
        'DistilRoBERTa Emotion (batched)', 'HDFS Upload', 'Hive External Table', 'Django Dashboard',
    ]
    tech_stack = [
        'Python 3.12', 'PRAW API', 'VADER Sentiment', 'TextBlob', 'DistilRoBERTa',
        'Hadoop HDFS', 'Apache Hive', 'Django 4.2', 'Plotly.js', 'SQLite',
    ]
    analyze_steps = [
        'Fetch Reddit via PRAW API', 'Preprocess & clean text',
        'VADER + TextBlob sentiment', 'DistilRoBERTa emotion (batched)',
        'Upload to HDFS', 'Create Hive table',
    ]

    context = {
        'recent_jobs':    recent_jobs,
        'total_analyses': total_analyses,
        'total_posts':    total_posts,
        'pipeline_steps': pipeline_steps,
        'tech_stack':     tech_stack,
    }
    return render(request, 'core/home.html', context)


# ── Analyze ───────────────────────────────────────────────────────────────────

def analyze(request):
    analyze_steps = [
        'Fetch Reddit via PRAW API',
        'Preprocess & clean text',
        'VADER + TextBlob sentiment',
        'DistilRoBERTa emotion (batched)',
        'Upload to HDFS',
        'Create Hive table',
    ]
    step_checklist = [
        {'label': 'Fetch Reddit Data',   'key': 'fetching'},
        {'label': 'Preprocess Text',     'key': 'preprocessing'},
        {'label': 'Sentiment Analysis',  'key': 'sentiment'},
        {'label': 'Emotion Detection',   'key': 'emotion'},
        {'label': 'HDFS Upload',         'key': 'hdfs'},
        {'label': 'Hive Table',          'key': 'hive'},
    ]
    return render(request, 'core/analyze.html', {
        'analyze_steps':  analyze_steps,
        'step_checklist': step_checklist,
    })


@require_POST
def run_analysis(request):
    """
    Creates an AnalysisJob and queues the background task.
    Returns JSON with job_id so frontend can start polling.
    """
    product     = request.POST.get('product', '').strip()
    fetch_limit = int(request.POST.get('fetch_limit', 200))

    if not product:
        return JsonResponse({'error': 'Product name is required.'}, status=400)

    # Prevent duplicate: if a job for this product is already running, return it
    RUNNING_STATUSES = ('pending','fetching','preprocessing','sentiment','emotion','hdfs','hive')
    existing = AnalysisJob.objects.filter(
        product=product, status__in=RUNNING_STATUSES
    ).order_by('-created_at').first()
    if existing:
        return JsonResponse({'job_id': existing.id, 'product': product, 'resumed': True})

    job = AnalysisJob.objects.create(
        product     = product,
        fetch_limit = fetch_limit,
        status      = 'pending',
        progress    = 0,
    )

    # Queue the background task via Django-Q (max_attempts=1 set in Q_CLUSTER)
    from django_q.tasks import async_task
    async_task('core.tasks.run_analysis_task', job.id,
               hook='core.tasks.task_complete_hook')

    return JsonResponse({'job_id': job.id, 'product': product})


def job_status(request, job_id):
    """AJAX endpoint — returns current job progress as JSON."""
    job = get_object_or_404(AnalysisJob, pk=job_id)

    STEP_LABELS = {
        'pending':        'Initialising pipeline…',
        'fetching':       'Fetching Reddit posts via PRAW API…',
        'preprocessing':  'Cleaning and preprocessing text…',
        'sentiment':      'Running VADER + TextBlob sentiment ensemble…',
        'emotion':        'Running DistilRoBERTa emotion detection (batched)…',
        'hdfs':           'Uploading data to HDFS…',
        'hive':           'Creating Hive external table…',
        'complete':       'Analysis complete.',
        'failed':         'Pipeline failed.',
    }

    return JsonResponse({
        'status':   job.status,
        'progress': job.progress,
        'label':    STEP_LABELS.get(job.status, job.status),
        'message':  job.status_message,
        'error':    job.error_message,
        'complete': job.status == 'complete',
        'failed':   job.status == 'failed',
    })


# ── Dashboard ─────────────────────────────────────────────────────────────────

def dashboard(request, job_id):
    job     = get_object_or_404(AnalysisJob, pk=job_id, status='complete')
    results = AnalysisResult.objects.filter(job=job)

    total = results.count()
    if total == 0:
        return render(request, 'core/dashboard.html', {'job': job, 'empty': True})

    # ── Sentiment counts ──────────────────────────────────────────────────────
    from django.db.models import Count, Avg, Sum

    sent_qs = results.values('sentiment').annotate(count=Count('id'))
    sent_map = {r['sentiment']: r['count'] for r in sent_qs}
    pos = sent_map.get('positive', 0)
    neg = sent_map.get('negative', 0)
    neu = sent_map.get('neutral',  0)

    # ── Emotion counts ────────────────────────────────────────────────────────
    emo_qs = results.values('emotion').annotate(count=Count('id')).order_by('-count')
    emotion_data = [{'label': r['emotion'].capitalize(), 'value': r['count']} for r in emo_qs]

    # ── Subreddit engagement ──────────────────────────────────────────────────
    sub_qs = (results.values('subreddit')
              .annotate(posts=Count('id'), total_comments=Sum('comments'), avg_score=Avg('score'))
              .order_by('-total_comments')[:10])
    subreddit_data = list(sub_qs)

    # ── Sentiment × Emotion cross ─────────────────────────────────────────────
    cross_qs = results.values('sentiment','emotion').annotate(count=Count('id'))
    cross_data = list(cross_qs)

    # ── Trending topics ───────────────────────────────────────────────────────
    all_text = " ".join(results.values_list('cleaned_text', flat=True)[:500])
    words    = re.findall(r'\b[a-z]{4,}\b', all_text.lower())
    skip     = {'this','that','with','from','have','will','been','they','them',
                'just','like','more','also','some','than','were','there','their',
                'about','would','could','should','when','your','what','which',
                'dont','cant','wont','isnt','doesnt','didnt'}
    words    = [w for w in words if w not in skip]
    topics   = Counter(words).most_common(15)

    # ── Top posts ─────────────────────────────────────────────────────────────
    top_posts = results.order_by('-score')[:8]

    # ── KPIs ──────────────────────────────────────────────────────────────────
    avg_score = results.aggregate(v=Avg('sentiment_score'))['v'] or 0
    top_emo   = emo_qs.first()['emotion'].capitalize() if emo_qs else '—'
    duration  = job.duration_seconds()

    context = {
        'job':            job,
        'total':          total,
        'pos':            pos,
        'neg':            neg,
        'neu':            neu,
        'pos_pct':        round(pos / total * 100, 1),
        'neg_pct':        round(neg / total * 100, 1),
        'neu_pct':        round(neu / total * 100, 1),
        'avg_score':      round(avg_score, 3),
        'top_emotion':    top_emo,
        'duration':       duration,
        'emotion_data':   json.dumps(emotion_data),
        'subreddit_data': json.dumps(subreddit_data),
        'cross_data':     json.dumps(cross_data),
        'topics':         topics,
        'top_posts':      top_posts,
        'sent_json':      json.dumps([
            {'label': 'Positive', 'value': pos},
            {'label': 'Negative', 'value': neg},
            {'label': 'Neutral',  'value': neu},
        ]),
    }
    return render(request, 'core/dashboard.html', context)


# ── History ───────────────────────────────────────────────────────────────────

def history(request):
    jobs = AnalysisJob.objects.all().order_by('-created_at')
    return render(request, 'core/history.html', {'jobs': jobs})


def delete_job(request, job_id):
    job = get_object_or_404(AnalysisJob, pk=job_id)
    job.delete()
    return redirect('history')


# ── Hive ──────────────────────────────────────────────────────────────────────

HIVE_QUERIES = {
    'sentiment_dist': {
        'title':       'Sentiment Distribution',
        'description': 'Overall positive / negative / neutral counts across all posts.',
        'hql': """USE reddit_analysis;
SELECT sentiment, COUNT(*) AS post_count,
ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentage
FROM reddit_results GROUP BY sentiment ORDER BY post_count DESC;""",
    },
    'emotion_freq': {
        'title':       'Emotion Frequency',
        'description': 'Which emotions appear most in Reddit discussions.',
        'hql': """USE reddit_analysis;
SELECT emotion, COUNT(*) AS count,
ROUND(AVG(emotion_score),4) AS avg_confidence
FROM reddit_results GROUP BY emotion ORDER BY count DESC;""",
    },
    'subreddit_sentiment': {
        'title':       'Sentiment by Subreddit',
        'description': 'Community-level sentiment breakdown.',
        'hql': """USE reddit_analysis;
SELECT subreddit, sentiment, COUNT(*) AS posts
FROM reddit_results GROUP BY subreddit, sentiment ORDER BY subreddit, posts DESC;""",
    },
    'top_engagement': {
        'title':       'Top Subreddits by Engagement',
        'description': 'Communities ranked by total score + comment volume.',
        'hql': """USE reddit_analysis;
SELECT subreddit, COUNT(*) AS total_posts,
SUM(score) AS total_score, SUM(comments) AS total_comments,
ROUND(AVG(score),1) AS avg_score
FROM reddit_results GROUP BY subreddit ORDER BY total_score DESC LIMIT 10;""",
    },
    'negative_critical': {
        'title':       'High-Engagement Negative Posts',
        'description': 'Most upvoted negative posts — highest priority for product teams.',
        'hql': """USE reddit_analysis;
SELECT title, subreddit, score, comments, emotion, sentiment_score
FROM reddit_results WHERE sentiment = 'negative'
ORDER BY score DESC LIMIT 10;""",
    },
    'emotion_sentiment_cross': {
        'title':       'Emotion × Sentiment Cross-Analysis',
        'description': 'Which emotions correlate with each sentiment category.',
        'hql': """USE reddit_analysis;
SELECT sentiment, emotion, COUNT(*) AS count
FROM reddit_results GROUP BY sentiment, emotion ORDER BY sentiment, count DESC;""",
    },
}


def hive(request):
    """
    Hive query explorer page.
    Runs the selected query if Hive is available, otherwise shows the HQL.
    """
    selected_key = request.GET.get('query', 'sentiment_dist')
    query_info   = HIVE_QUERIES.get(selected_key, HIVE_QUERIES['sentiment_dist'])

    columns, rows, hive_error, hive_available = [], [], None, False

    try:
        result = subprocess.run(
            ['hive', '-e', query_info['hql']],
            capture_output=True, text=True, timeout=120
        )
        hive_available = True

        # Aggressively filter ALL known Hive/Hadoop noise from output
        NOISE_PATTERNS = (
            'SLF4J', 'log4j', 'WARN ', 'INFO ', 'DEBUG ',
            'Hive Session ID', 'OK', 'Time taken', 'MapReduce Jobs',
            'Launching Job', 'Number of reduce', 'Hadoop job information',
            'Starting Job', 'Stage-', 'STAGE PLANS', 'STAGE DEPENDENCIES',
            'Connecting to', 'Connected to', 'Transaction isolation',
            'WARNING:', 'HiveConf', 'MetaStore', 'metastore',
            'org.apache', 'org.slf4j', 'com.google', 'java.',
        )

        def clean_hive_output(text):
            lines = []
            for line in text.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                if any(pattern in line for pattern in NOISE_PATTERNS):
                    continue
                lines.append(line)
            return '\n'.join(lines)

        stdout_clean = clean_hive_output(result.stdout)
        stderr_clean = clean_hive_output(result.stderr)

        if result.returncode == 0:
            lines = [l for l in stdout_clean.strip().split('\n') if l.strip()]
            if lines:
                columns = [c.split('.')[-1] for c in lines[0].split('\t')]
                rows    = [line.split('\t') for line in lines[1:] if line.strip()]
            # If no lines, table exists but is empty — show empty state (no error)
        else:
            # Only show as error if there is real non-noise error content
            real_error = stderr_clean.strip()
            if real_error:
                hive_error = real_error[:400]
            else:
                hive_error = 'no_data'
    except FileNotFoundError:
        hive_error     = "not_found"
        hive_available = False
    except subprocess.TimeoutExpired:
        hive_error     = "timeout"

    context = {
        'queries':        HIVE_QUERIES,
        'selected_key':   selected_key,
        'query_info':     query_info,
        'columns':        columns,
        'rows':           rows,
        'hive_error':     hive_error,
        'hive_available': hive_available,
    }
    return render(request, 'core/hive.html', context)


# ── About ─────────────────────────────────────────────────────────────────────

# ── About (override) ──────────────────────────────────────────────────────────
# Redefine about with steps context
def about(request):
    vader_points = [
        'VADER: rule-based, optimised for social media slang and abbreviations',
        'TextBlob: grammar-aware polarity scoring for structured sentences',
        'Weighted ensemble: 60% VADER + 40% TextBlob compound score',
        'Output labels: Positive / Negative / Neutral + confidence score',
        'Performance: 10,000 records processed in under 60 seconds',
        'No GPU required — pure CPU inference, safe on 8GB WSL RAM',
    ]
    distil_points = [
        'Architecture: DistilRoBERTa — distilled transformer, ~250MB model size',
        '7 emotion classes: joy, anger, sadness, fear, surprise, disgust, neutral',
        'Batched inference: batch_size=32 — 20x faster than single-pass loop',
        'Max token length: 256 — sufficient for Reddit posts and comments',
        'RAM usage: ~1.2GB peak — safe for 8GB WSL RAM allocation',
        'Performance: 10,000 records in approximately 3-5 minutes on CPU',
    ]
    team_members = [
        'Sanket Borhade',
        'Snigdha Bhoir',
        'Ankul Tumsare',
        'Harshada Harkulkar',
    ]
    pipeline_steps = [
        {
            'title': 'Reddit Data Collection via PRAW API',
            'desc':  'Searches relevant subreddits for the product keyword. Fetches post titles, '
                     'body text, scores, and comment counts. Deduplicates by post ID.',
            'tech':  'praw · product_search.py',
        },
        {
            'title': 'Text Preprocessing & Cleaning',
            'desc':  'Removes URLs, Reddit mentions, HTML entities, emojis, elongated words, '
                     'and stopwords while preserving negations. Combines title + body.',
            'tech':  'nltk · preprocess.py',
        },
        {
            'title': 'Sentiment Analysis — VADER + TextBlob Ensemble',
            'desc':  'VADER handles social media slang. TextBlob handles grammatically structured '
                     'sentences. Weighted 60/40 ensemble assigns sentiment labels + confidence score.',
            'tech':  'vaderSentiment · textblob · sentiment_pipeline.py',
        },
        {
            'title': 'Emotion Detection — DistilRoBERTa (Batched)',
            'desc':  'j-hartmann/emotion-english-distilroberta-base detects 7 emotions. '
                     'Runs in batches of 32 for performance — handles 10,000 records in ~3-5 minutes on CPU.',
            'tech':  'transformers · emotion_pipeline.py',
        },
        {
            'title': 'HDFS Upload',
            'desc':  'Raw, cleaned, and enriched result CSVs uploaded to Hadoop Distributed '
                     'File System under /reddit_data/raw/, /clean/, and /results/.',
            'tech':  'hadoop fs -put · upload_to_hdfs.sh',
        },
        {
            'title': 'Hive External Table Creation',
            'desc':  'External Hive table created over results directory in HDFS. '
                     'Enables SQL-style aggregation without moving data out of HDFS.',
            'tech':  'Apache Hive · hive_queries.sql',
        },
        {
            'title': 'Django Dashboard & Reporting',
            'desc':  'Results saved to SQLite via Django ORM. Interactive BI dashboard with '
                     'Plotly charts, KPI cards, heatmaps, trending topics, and post table.',
            'tech':  'Django 4.2 · Plotly.js · SQLite',
        },
    ]
    return render(request, 'core/about.html', {
        'steps':         pipeline_steps,
        'vader_points':  vader_points,
        'distil_points': distil_points,
        'team_members':  team_members,
    })
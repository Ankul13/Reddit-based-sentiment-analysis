"""
models.py
---------
Two models:
  AnalysisJob    — one row per pipeline run (product, status, progress, timestamps)
  AnalysisResult — one row per Reddit post (linked to a job)
"""

from django.db import models
from django.utils import timezone


class AnalysisJob(models.Model):

    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('fetching',   'Fetching Reddit Data'),
        ('preprocessing', 'Preprocessing'),
        ('sentiment',  'Sentiment Analysis'),
        ('emotion',    'Emotion Detection'),
        ('hdfs',       'Uploading to HDFS'),
        ('hive',       'Creating Hive Table'),
        ('complete',   'Complete'),
        ('failed',     'Failed'),
    ]

    product         = models.CharField(max_length=200)
    fetch_limit     = models.IntegerField(default=200)
    status          = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    progress        = models.IntegerField(default=0)          # 0–100
    status_message  = models.TextField(blank=True, default='')
    total_posts     = models.IntegerField(default=0)
    result_path     = models.CharField(max_length=500, blank=True, default='')
    error_message   = models.TextField(blank=True, default='')
    created_at      = models.DateTimeField(default=timezone.now)
    completed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product} [{self.status}] — {self.created_at.strftime('%d %b %Y %H:%M')}"

    def duration_seconds(self):
        if self.completed_at:
            return int((self.completed_at - self.created_at).total_seconds())
        return None


class AnalysisResult(models.Model):

    SENTIMENT_CHOICES = [
        ('positive', 'Positive'),
        ('negative', 'Negative'),
        ('neutral',  'Neutral'),
    ]

    job             = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE,
                                        related_name='results')
    post_id         = models.CharField(max_length=100, blank=True)
    title           = models.TextField(blank=True)
    text            = models.TextField(blank=True)
    cleaned_text    = models.TextField(blank=True)
    subreddit       = models.CharField(max_length=100, blank=True)
    score           = models.IntegerField(default=0)
    comments        = models.IntegerField(default=0)
    created_utc     = models.FloatField(null=True, blank=True)
    sentiment       = models.CharField(max_length=20, choices=SENTIMENT_CHOICES,
                                       blank=True)
    sentiment_score = models.FloatField(default=0.0)
    emotion         = models.CharField(max_length=50, blank=True)
    emotion_score   = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-score']

    def __str__(self):
        return f"{self.subreddit} | {self.sentiment} | {self.emotion}"

"""
emotion_pipeline.py
-------------------
Emotion detection using j-hartmann/emotion-english-distilroberta-base.
Model detects 7 emotions: anger, disgust, fear, joy, neutral, sadness, surprise.

Key performance fix over previous version:
  - Processes texts in BATCHES of 32 (not one-by-one)
  - Truncates to 256 tokens (sufficient for Reddit, saves memory vs 512)
  - Model loaded once at module level (not reloaded per call)
  - On 8GB WSL RAM: handles 10,000 records in ~3-5 minutes
"""

import pandas as pd
import os
from transformers import pipeline
from tqdm import tqdm

# ── Model config ──────────────────────────────────────────────────────────────
MODEL_NAME  = "j-hartmann/emotion-english-distilroberta-base"
BATCH_SIZE  = 32      # safe for 8GB WSL RAM
MAX_TOKENS  = 256     # Reddit posts rarely need more; saves memory

# Load once at import time — avoids reloading on every run_emotion() call
print("Loading emotion model (first run may download ~250MB)...")
_emotion_model = pipeline(
    "text-classification",
    model=MODEL_NAME,
    top_k=1,
    truncation=True,
    max_length=MAX_TOKENS,
    device=-1           # CPU; set to 0 if you have CUDA
)
print("Emotion model ready.")
# ─────────────────────────────────────────────────────────────────────────────


def _batch(iterable, size: int):
    """Yield successive chunks of `size` from iterable."""
    lst = list(iterable)
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def run_emotion(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds 'emotion' and 'emotion_score' columns to df.
    Processes in batches for performance.

    Args:
        df: DataFrame that must contain a 'cleaned_text' column.

    Returns:
        df with two new columns: emotion (str), emotion_score (float)
    """
    texts = df["cleaned_text"].fillna("").tolist()

    emotions       = []
    emotion_scores = []

    batches = list(_batch(texts, BATCH_SIZE))
    print(f"  Running emotion detection on {len(texts)} records "
          f"({len(batches)} batches of {BATCH_SIZE})...")

    for batch_texts in tqdm(batches, desc="  Emotion batches", unit="batch"):
        try:
            results = _emotion_model(batch_texts)
            for result in results:
                top = result[0]
                emotions.append(top["label"].lower())
                emotion_scores.append(round(top["score"], 4))
        except Exception as e:
            # Fallback for any bad batch — mark as neutral
            print(f"  Warning: batch failed ({e}), marking as neutral.")
            for _ in batch_texts:
                emotions.append("neutral")
                emotion_scores.append(0.0)

    df["emotion"]       = emotions
    df["emotion_score"] = emotion_scores

    # Summary log
    counts = df["emotion"].value_counts()
    print("  Emotion distribution:")
    for emo, cnt in counts.items():
        print(f"    {emo:<12} {cnt}")

    return df

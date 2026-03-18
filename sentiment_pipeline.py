"""
sentiment_pipeline.py
---------------------
Ensemble sentiment analysis using VADER + TextBlob.
No GPU required. Handles 10,000+ records in under 60 seconds.

Ensemble Logic:
  - VADER compound score  (weight: 0.6) — strong on social media slang/emojis
  - TextBlob polarity     (weight: 0.4) — strong on grammatical sentences
  - Final label: positive / negative / neutral based on combined score
"""

import pandas as pd
import os
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from textblob import TextBlob

# Initialise VADER once — thread-safe, reusable
_vader = SentimentIntensityAnalyzer()


def _textblob_score(text: str) -> float:
    """
    Returns TextBlob polarity in [-1, +1].
    """
    try:
        return TextBlob(text).sentiment.polarity
    except Exception:
        return 0.0


def ensemble_sentiment(text: str) -> str:
    """
    Combines VADER and TextBlob into a single sentiment label.

    Returns:
        'positive' | 'negative' | 'neutral'
    """
    if not isinstance(text, str) or len(text.strip()) == 0:
        return "neutral"

    vader_score  = _vader.polarity_scores(text)["compound"]   # [-1, +1]
    textblob_score = _textblob_score(text)                     # [-1, +1]

    # Weighted ensemble
    combined = 0.6 * vader_score + 0.4 * textblob_score

    if combined >= 0.05:
        return "positive"
    elif combined <= -0.05:
        return "negative"
    else:
        return "neutral"


def run_sentiment(input_path: str, product: str) -> str:
    """
    Reads cleaned CSV, applies ensemble sentiment to every row,
    saves enriched CSV to data/results/{product}_sentiment.csv.

    Returns output path.
    """
    df = pd.read_csv(input_path)
    print(f"  Running sentiment on {len(df)} records...")

    df["sentiment"] = df["cleaned_text"].fillna("").apply(ensemble_sentiment)

    # Sentiment confidence score (VADER compound — useful for Hive queries)
    df["sentiment_score"] = df["cleaned_text"].fillna("").apply(
        lambda t: round(_vader.polarity_scores(t)["compound"], 4)
    )

    output_path = f"data/results/{product}_sentiment.csv"
    os.makedirs("data/results", exist_ok=True)
    df.to_csv(output_path, index=False)

    # Quick summary log
    counts = df["sentiment"].value_counts()
    print(f"  Sentiment done → Positive: {counts.get('positive',0)} | "
          f"Negative: {counts.get('negative',0)} | "
          f"Neutral: {counts.get('neutral',0)}")

    return output_path

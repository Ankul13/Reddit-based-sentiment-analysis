"""
preprocess.py
-------------
Cleans raw Reddit CSV data before NLP analysis.
Handles URLs, emojis, HTML, mentions, subreddit tags,
repeated characters, and stopwords.
"""

import pandas as pd
import re
import os
import nltk
from nltk.corpus import stopwords

# Download stopwords if not already present
nltk.download("stopwords", quiet=True)
nltk.download("punkt", quiet=True)

STOP_WORDS = set(stopwords.words("english"))

# Keep negations — important for sentiment
NEGATIONS = {"no", "not", "nor", "never", "neither", "nobody", "nothing",
             "nowhere", "without", "hardly", "barely", "scarcely"}
STOP_WORDS -= NEGATIONS


def clean_text(text: str) -> str:
    """
    Full social-media text cleaning pipeline.
    Steps match the paper's Fig.1 preprocessing flow.
    """
    if pd.isna(text) or not isinstance(text, str):
        return ""

    # 1. Lowercase
    text = text.lower()

    # 2. Remove URLs
    text = re.sub(r"http\S+|www\.\S+", "", text)

    # 3. Remove Reddit mentions (u/user, r/subreddit)
    text = re.sub(r"u/\w+|r/\w+", "", text)

    # 4. Remove HTML entities
    text = re.sub(r"&[a-z]+;", " ", text)

    # 5. Remove emojis and special unicode
    text = re.sub(r"[^\x00-\x7F]+", " ", text)

    # 6. Normalize elongated words (e.g. "sooooo" -> "so")
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)

    # 7. Remove punctuation and numbers, keep letters + spaces
    text = re.sub(r"[^a-z\s]", " ", text)

    # 8. Tokenize and remove stopwords
    tokens = text.split()
    tokens = [w for w in tokens if w not in STOP_WORDS and len(w) > 1]

    return " ".join(tokens)


def preprocess_data(input_path: str, output_path: str) -> str:
    """
    Load raw CSV, combine title+text, clean, save to output path.
    Returns output path.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = pd.read_csv(input_path)

    print(f"  Loaded {len(df)} records from {input_path}")

    # Combine title and body text
    if "title" in df.columns and "text" in df.columns:
        df["text"] = df["title"].fillna("") + " " + df["text"].fillna("")
    elif "title" in df.columns:
        df["text"] = df["title"].fillna("")
    elif "text" not in df.columns:
        raise ValueError("CSV must have a 'text' or 'title' column.")

    # Apply cleaning
    df["cleaned_text"] = df["text"].apply(clean_text)

    # Drop rows where cleaned text is empty
    before = len(df)
    df = df[df["cleaned_text"].str.strip().str.len() > 0].reset_index(drop=True)
    dropped = before - len(df)
    if dropped > 0:
        print(f"  Dropped {dropped} empty rows after cleaning.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"  Saved {len(df)} clean records to {output_path}")
    return output_path

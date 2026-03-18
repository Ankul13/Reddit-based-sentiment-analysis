"""
product_search.py
-----------------
Fetches Reddit posts using PRAW API.
Searches relevant subreddits for the product keyword.
Deduplicates by post ID to avoid repeated entries.
"""

import praw
import pandas as pd
import json
import os

BASE_DIR =  os.path.dirname(os.path.abspath(__file__))
# base_dir = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(BASE_DIR, "config.json")
# Load credentials
with open(config_path) as f:
    cfg = json.load(f)

reddit = praw.Reddit(
    client_id=cfg["client_id"],
    client_secret=cfg["client_secret"],
    user_agent=cfg["user_agent"]
)


def find_relevant_subreddits(product: str, limit: int = 5) -> list:
    """
    Finds subreddits most relevant to the product keyword.
    Falls back to r/all if none found.
    """
    subreddits = []
    try:
        for sub in reddit.subreddits.search(product, limit=limit):
            subreddits.append(sub.display_name)
    except Exception as e:
        print(f"  Subreddit search failed: {e}. Falling back to r/all.")

    if not subreddits:
        subreddits = ["all"]

    print(f"  Searching subreddits: {subreddits}")
    return subreddits


def fetch_posts(product: str, limit: int = 200) -> str:
    """
    Fetches posts + top-level comments for a product keyword.
    Deduplicates by post ID.
    Saves raw CSV to data/raw/{product}.csv.

    Args:
        product: search keyword (e.g. "iPhone 17")
        limit:   max posts per subreddit (default 200)

    Returns:
        Path to saved raw CSV.
    """
    subreddits = find_relevant_subreddits(product)

    posts = []
    seen_ids = set()

    for sub in subreddits:
        print(f"  Fetching from r/{sub}...")
        try:
            for submission in reddit.subreddit(sub).search(product, limit=limit):

                if submission.id in seen_ids:
                    continue
                seen_ids.add(submission.id)

                # Combine title + selftext as the main text body
                body = submission.selftext.strip()
                text = (submission.title + " " + body).strip()

                posts.append({
                    "id":         submission.id,
                    "title":      submission.title,
                    "text":       text,
                    "subreddit":  sub,
                    "score":      submission.score,
                    "comments":   submission.num_comments,
                    "created_utc": submission.created_utc,
                    "url":        submission.url,
                })

        except Exception as e:
            print(f"  Warning: failed fetching from r/{sub}: {e}")
            continue

    if not posts:
        raise RuntimeError(f"No posts fetched for '{product}'. "
                           "Check Reddit credentials or try a different keyword.")

    df = pd.DataFrame(posts).drop_duplicates(subset="id")

    os.makedirs("data/raw", exist_ok=True)
    safe_name = product.replace(" ", "_")
    path = f"data/raw/{safe_name}.csv"
    df.to_csv(path, index=False)

    print(f"  Fetched {len(df)} unique posts → {path}")
    return path

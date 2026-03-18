-- =============================================================
-- hive_queries.sql
-- Reddit Sentiment & Emotion Analysis — Hive Analytics Layer
-- Run via: hive -f hive_queries.sql
--          or paste individual queries in Hive CLI
-- =============================================================

USE reddit_analysis;

-- ─────────────────────────────────────────────────────────────
-- Q1. Overall Sentiment Distribution
--     How many posts are positive / negative / neutral?
-- ─────────────────────────────────────────────────────────────
SELECT
    sentiment,
    COUNT(*)                                          AS post_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentage
FROM reddit_results
GROUP BY sentiment
ORDER BY post_count DESC;


-- ─────────────────────────────────────────────────────────────
-- Q2. Emotion Frequency Breakdown
--     Which emotions appear most in user discussions?
-- ─────────────────────────────────────────────────────────────
SELECT
    emotion,
    COUNT(*)                                          AS emotion_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentage,
    ROUND(AVG(emotion_score), 4)                      AS avg_confidence
FROM reddit_results
GROUP BY emotion
ORDER BY emotion_count DESC;


-- ─────────────────────────────────────────────────────────────
-- Q3. Sentiment by Subreddit
--     Which communities are most positive or negative?
-- ─────────────────────────────────────────────────────────────
SELECT
    subreddit,
    sentiment,
    COUNT(*) AS post_count
FROM reddit_results
GROUP BY subreddit, sentiment
ORDER BY subreddit, post_count DESC;


-- ─────────────────────────────────────────────────────────────
-- Q4. Top Trending Subreddits by Engagement
--     Ranked by total score + comment count
-- ─────────────────────────────────────────────────────────────
SELECT
    subreddit,
    COUNT(*)          AS total_posts,
    SUM(score)        AS total_score,
    SUM(comments)     AS total_comments,
    ROUND(AVG(score), 1) AS avg_score
FROM reddit_results
GROUP BY subreddit
ORDER BY total_score DESC
LIMIT 10;


-- ─────────────────────────────────────────────────────────────
-- Q5. Emotion × Sentiment Cross-Analysis
--     What emotions drive positive vs negative sentiment?
-- ─────────────────────────────────────────────────────────────
SELECT
    sentiment,
    emotion,
    COUNT(*) AS count
FROM reddit_results
GROUP BY sentiment, emotion
ORDER BY sentiment, count DESC;


-- ─────────────────────────────────────────────────────────────
-- Q6. Most Engaging Posts (for dashboard sample table)
--     Top 20 posts by score with their labels
-- ─────────────────────────────────────────────────────────────
SELECT
    title,
    subreddit,
    score,
    comments,
    sentiment,
    emotion,
    sentiment_score
FROM reddit_results
ORDER BY score DESC
LIMIT 20;


-- ─────────────────────────────────────────────────────────────
-- Q7. Negative High-Engagement Posts
--     Critical feedback that got the most attention
--     (most actionable for product teams)
-- ─────────────────────────────────────────────────────────────
SELECT
    title,
    subreddit,
    score,
    comments,
    emotion,
    sentiment_score
FROM reddit_results
WHERE sentiment = 'negative'
ORDER BY score DESC
LIMIT 10;


-- ─────────────────────────────────────────────────────────────
-- Q8. Average Sentiment Score by Subreddit
--     Continuous measure of community tone
-- ─────────────────────────────────────────────────────────────
SELECT
    subreddit,
    ROUND(AVG(sentiment_score), 4) AS avg_sentiment_score,
    COUNT(*) AS posts
FROM reddit_results
GROUP BY subreddit
HAVING COUNT(*) >= 5
ORDER BY avg_sentiment_score DESC;

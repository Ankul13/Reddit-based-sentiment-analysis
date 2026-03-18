"""
app.py
------
Industry-level Streamlit dashboard for Reddit Sentiment & Emotion Analysis.
Visualises results from the product_pipeline output CSV.

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import sys
import os
from collections import Counter
import re

sys.path.append(os.path.dirname(__file__))
from product_pipeline import run_pipeline

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reddit Product Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* General */
[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stHeader"]           { background: transparent; }

/* Metric cards */
.metric-card {
    background: #1a1d27;
    border: 1px solid #2d3147;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    margin-bottom: 12px;
}
.metric-value { font-size: 2.2rem; font-weight: 700; color: #ffffff; }
.metric-label { font-size: 0.85rem; color: #8b8fa8; margin-top: 4px; }

/* Section headers */
.section-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #c9cde0;
    margin: 24px 0 12px 0;
    border-left: 3px solid #6c63ff;
    padding-left: 10px;
}

/* Sentiment badges */
.badge-positive { background:#1a3a2a; color:#4caf78; border:1px solid #2d6647;
                  padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
.badge-negative { background:#3a1a1a; color:#ef5350; border:1px solid #6b2d2d;
                  padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
.badge-neutral  { background:#2a2a1a; color:#ffc107; border:1px solid #5a4d1a;
                  padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }

/* Post card */
.post-card {
    background: #1a1d27;
    border: 1px solid #2d3147;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    line-height: 1.55;
    font-size: 0.9rem;
    color: #c9cde0;
}
.post-meta { font-size:0.78rem; color:#555b7a; margin-top:8px; }

/* Trending topic chips */
.topic-chip {
    display:inline-block;
    background:#1e2235;
    border:1px solid #3a4060;
    border-radius:20px;
    padding:6px 14px;
    margin:4px;
    font-size:0.82rem;
    color:#9ba3c8;
}
.topic-chip-hot  { border-color:#ef5350; color:#ef7070; }
.topic-chip-warm { border-color:#ffc107; color:#ffd54f; }
.topic-chip-cool { border-color:#4caf78; color:#66bb6a; }
</style>
""", unsafe_allow_html=True)


# ── Helper functions ──────────────────────────────────────────────────────────

EMOTION_COLORS = {
    "joy":      "#ffd54f",
    "anger":    "#ef5350",
    "sadness":  "#42a5f5",
    "fear":     "#ab47bc",
    "surprise": "#26c6da",
    "disgust":  "#8bc34a",
    "neutral":  "#78909c",
}

SENTIMENT_COLORS = {
    "positive": "#4caf78",
    "negative": "#ef5350",
    "neutral":  "#ffc107",
}


def sentiment_badge(s: str) -> str:
    s = str(s).lower()
    label = s.capitalize()
    icon  = "🟢" if s == "positive" else ("🔴" if s == "negative" else "🟡")
    cls   = f"badge-{s}" if s in ("positive","negative","neutral") else "badge-neutral"
    return f'<span class="{cls}">{icon} {label}</span>'


def extract_trending_topics(df: pd.DataFrame, top_n: int = 12) -> list:
    """Extract most frequent meaningful words from cleaned_text."""
    text = " ".join(df["cleaned_text"].fillna("").tolist())
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    # Remove generic filler words
    skip = {"this","that","with","from","have","will","been","they","them",
            "just","like","more","also","some","than","were","there","their",
            "about","would","could","should","when","your","what","which"}
    words = [w for w in words if w not in skip]
    return Counter(words).most_common(top_n)


def make_wordcloud(df: pd.DataFrame):
    text = " ".join(df["cleaned_text"].fillna("").tolist())
    if not text.strip():
        return None
    wc = WordCloud(
        width=800, height=350,
        background_color="#0f1117",
        colormap="cool",
        max_words=120,
        collocations=False
    ).generate(text)
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#0f1117")
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    return fig


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:24px 0 8px 0">
    <h1 style="color:#ffffff; font-size:1.9rem; font-weight:700; margin:0">
        📊 Reddit Product Intelligence
    </h1>
    <p style="color:#6b7194; font-size:0.95rem; margin-top:6px">
        Sentiment & Emotion Analysis · Powered by VADER + TextBlob + DistilRoBERTa · Hadoop/Hive Backend
    </p>
</div>
<hr style="border-color:#2d3147; margin-bottom:24px">
""", unsafe_allow_html=True)

# ── Input ─────────────────────────────────────────────────────────────────────
col_input, col_btn, col_limit = st.columns([3, 1, 1])

with col_input:
    product = st.text_input(
        "Product / Keyword",
        placeholder="e.g. iPhone 17, Samsung Galaxy S25...",
        label_visibility="collapsed"
    )

with col_limit:
    fetch_limit = st.selectbox(
        "Posts per subreddit",
        options=[100, 200, 500, 1000],
        index=1,
        label_visibility="collapsed"
    )

with col_btn:
    run_btn = st.button("🚀 Run Analysis", use_container_width=True)

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_btn and product.strip():
    with st.spinner(f"Analysing Reddit discussions for **{product}**…"):
        try:
            file_path = run_pipeline(product.strip(), fetch_limit=fetch_limit)
            df = pd.read_csv(file_path)
            st.session_state["data"]    = df
            st.session_state["product"] = product.strip()
            st.success(f"✅ Analysis complete — {len(df):,} posts processed.")
        except Exception as e:
            st.error(f"Pipeline error: {e}")

elif run_btn and not product.strip():
    st.warning("Please enter a product name.")

# ── Guard: nothing loaded yet ─────────────────────────────────────────────────
if "data" not in st.session_state:
    st.markdown("""
    <div style="text-align:center; padding:80px 0; color:#3d4260">
        <div style="font-size:3rem">🔍</div>
        <div style="font-size:1rem; margin-top:12px">Enter a product name above and click Run Analysis</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

df      = st.session_state["data"]
product = st.session_state.get("product", "Product")

# ── KPI Metrics row ───────────────────────────────────────────────────────────
st.markdown(f'<div class="section-title">Overview · {product}</div>', unsafe_allow_html=True)

total   = len(df)
pos_pct = round((df["sentiment"] == "positive").mean() * 100, 1)
neg_pct = round((df["sentiment"] == "negative").mean() * 100, 1)
neu_pct = round((df["sentiment"] == "neutral").mean() * 100, 1)
top_emo = df["emotion"].value_counts().idxmax() if "emotion" in df.columns else "—"
avg_score = round(df["sentiment_score"].mean(), 3) if "sentiment_score" in df.columns else 0.0
avg_comments = int(df["comments"].mean()) if "comments" in df.columns else 0

m1, m2, m3, m4, m5, m6 = st.columns(6)

metrics = [
    (m1, str(f"{total:,}"),          "Total Posts"),
    (m2, f"{pos_pct}%",              "Positive"),
    (m3, f"{neg_pct}%",              "Negative"),
    (m4, f"{neu_pct}%",              "Neutral"),
    (m5, top_emo.capitalize(),       "Top Emotion"),
    (m6, str(avg_comments),          "Avg Comments"),
]

for col, val, label in metrics:
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{val}</div>
            <div class="metric-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

# ── Charts row ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Sentiment & Emotion Distribution</div>',
            unsafe_allow_html=True)

chart_col1, chart_col2 = st.columns(2)

# Sentiment donut
with chart_col1:
    sent_counts = df["sentiment"].value_counts().reset_index()
    sent_counts.columns = ["Sentiment", "Count"]
    fig_sent = px.pie(
        sent_counts, names="Sentiment", values="Count",
        hole=0.55,
        color="Sentiment",
        color_discrete_map=SENTIMENT_COLORS,
        title="Sentiment Distribution"
    )
    fig_sent.update_layout(
        paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
        font_color="#c9cde0",
        title_font_size=14,
        legend=dict(bgcolor="#1a1d27"),
        margin=dict(t=40, b=10)
    )
    fig_sent.update_traces(textinfo="percent+label", textfont_size=12)
    st.plotly_chart(fig_sent, use_container_width=True)

# Emotion bar
with chart_col2:
    if "emotion" in df.columns:
        emo_counts = df["emotion"].value_counts().reset_index()
        emo_counts.columns = ["Emotion", "Count"]
        emo_counts["Emotion"] = emo_counts["Emotion"].str.capitalize()
        emo_counts["Color"] = emo_counts["Emotion"].str.lower().map(EMOTION_COLORS).fillna("#78909c")

        fig_emo = px.bar(
            emo_counts, x="Count", y="Emotion",
            orientation="h",
            color="Emotion",
            color_discrete_map={k.capitalize(): v for k, v in EMOTION_COLORS.items()},
            title="Emotion Breakdown"
        )
        fig_emo.update_layout(
            paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
            font_color="#c9cde0",
            title_font_size=14,
            showlegend=False,
            margin=dict(t=40, b=10),
            xaxis=dict(gridcolor="#2d3147"),
            yaxis=dict(gridcolor="#2d3147"),
        )
        st.plotly_chart(fig_emo, use_container_width=True)

# ── Sentiment × Emotion heatmap ───────────────────────────────────────────────
st.markdown('<div class="section-title">Emotion × Sentiment Cross-Analysis</div>',
            unsafe_allow_html=True)

if "emotion" in df.columns:
    cross = df.groupby(["sentiment", "emotion"]).size().reset_index(name="count")
    pivot = cross.pivot(index="emotion", columns="sentiment", values="count").fillna(0)

    fig_heat = px.imshow(
        pivot,
        color_continuous_scale="Viridis",
        title="Which emotions drive each sentiment?",
        text_auto=True,
        aspect="auto"
    )
    fig_heat.update_layout(
        paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
        font_color="#c9cde0",
        title_font_size=14,
        margin=dict(t=40, b=10),
        coloraxis_colorbar=dict(bgcolor="#1a1d27", tickcolor="#c9cde0")
    )
    st.plotly_chart(fig_heat, use_container_width=True)

# ── Trending Topics ───────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Trending Topics</div>', unsafe_allow_html=True)

topics = extract_trending_topics(df)
if topics:
    max_count = topics[0][1]
    chips_html = ""
    for word, count in topics:
        ratio = count / max_count
        cls = "topic-chip-hot" if ratio > 0.66 else ("topic-chip-warm" if ratio > 0.33 else "topic-chip-cool")
        chips_html += f'<span class="topic-chip {cls}">{word} <b>{count}</b></span>'
    st.markdown(f'<div style="padding:8px 0">{chips_html}</div>', unsafe_allow_html=True)

# ── Word Cloud ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Word Cloud</div>', unsafe_allow_html=True)

wc_fig = make_wordcloud(df)
if wc_fig:
    st.pyplot(wc_fig)

# ── Subreddit Engagement ──────────────────────────────────────────────────────
if "subreddit" in df.columns:
    st.markdown('<div class="section-title">Subreddit Engagement</div>',
                unsafe_allow_html=True)

    sub_stats = (
        df.groupby("subreddit")
        .agg(
            Posts    =("id",       "count"),
            AvgScore =("score",    "mean"),
            TotalComments=("comments","sum")
        )
        .reset_index()
        .sort_values("TotalComments", ascending=False)
        .head(10)
    )
    sub_stats["AvgScore"] = sub_stats["AvgScore"].round(1)

    fig_sub = px.bar(
        sub_stats, x="subreddit", y="TotalComments",
        color="AvgScore",
        color_continuous_scale="Plasma",
        title="Top Subreddits by Total Comments",
        labels={"subreddit": "Subreddit", "TotalComments": "Total Comments"}
    )
    fig_sub.update_layout(
        paper_bgcolor="#1a1d27", plot_bgcolor="#1a1d27",
        font_color="#c9cde0",
        title_font_size=14,
        xaxis=dict(gridcolor="#2d3147"),
        yaxis=dict(gridcolor="#2d3147"),
        margin=dict(t=40, b=10)
    )
    st.plotly_chart(fig_sub, use_container_width=True)

# ── Sample Posts Table ────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Sample Analysed Posts</div>', unsafe_allow_html=True)

sample = (
    df[["title", "subreddit", "score", "comments", "sentiment", "emotion"]]
    .dropna()
    .sort_values("score", ascending=False)
    .head(8)
)

for _, row in sample.iterrows():
    title    = str(row.get("title", ""))[:160]
    sub      = str(row.get("subreddit", ""))
    score    = int(row.get("score", 0))
    comments = int(row.get("comments", 0))
    sent     = str(row.get("sentiment", "neutral")).lower()
    emo      = str(row.get("emotion", "neutral")).capitalize()
    badge    = sentiment_badge(sent)
    emo_col  = EMOTION_COLORS.get(emo.lower(), "#78909c")

    st.markdown(f"""
    <div class="post-card">
        {title}
        <div class="post-meta">
            r/{sub} &nbsp;·&nbsp; ⬆ {score:,} &nbsp;·&nbsp; 💬 {comments:,}
            &nbsp;&nbsp;{badge}&nbsp;&nbsp;
            <span style="color:{emo_col}; font-size:0.78rem; font-weight:600">
                ● {emo}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<hr style="border-color:#2d3147; margin-top:40px">
<div style="text-align:center; color:#3d4260; font-size:0.8rem; padding-bottom:20px">
    Reddit Product Intelligence · VADER + TextBlob + DistilRoBERTa · Hadoop HDFS + Hive
</div>
""", unsafe_allow_html=True)

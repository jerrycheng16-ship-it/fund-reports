import os
import urllib.parse
import feedparser
import streamlit as st
from openai import OpenAI

# =====================================================
# 頁面設定
# =====================================================

st.set_page_config(
    page_title="AI基金投資分析平台",
    page_icon="📊",
    layout="wide"
)

# =====================================================
# API KEY
# =====================================================

try:
    API_KEY = st.secrets["DASHSCOPE_API_KEY"]
except Exception:
    API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# =====================================================
# QWEN
# =====================================================

def generate_report(prompt):

    client = OpenAI(
        api_key=API_KEY,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )

    response = client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.4
    )

    return response.choices[0].message.content

# =====================================================
# RSS新聞
# =====================================================

def fetch_realtime_news(query):

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        f"https://news.google.com/rss/search?q={encoded_query}"
        "&hl=zh-TW"
        "&gl=TW"
        "&ceid=TW:zh-Hant"
    )

    feed = feedparser.parse(rss_url)

    news_items = []

    for entry 

import os
import time
import urllib.parse
import feedparser
import streamlit as st
from openai import OpenAI

# =====================================================
# 頁面設定
# =====================================================

st.set_page_config(
    page_title="AI 基金投資分析與金融市場情報平台",
    page_icon="📊",
    layout="wide"
)

# =====================================================
# API KEY
# =====================================================

try:
    api_key = st.secrets["DASHSCOPE_API_KEY"]
except Exception:
    api_key = os.getenv("DASHSCOPE_API_KEY", "")

# =====================================================
# Session State
# =====================================================

if "fund_report" not in st.session_state:
    st.session_state.fund_report = ""

if "daily_news" not in st.session_state:
    st.session_state.daily_news = ""

# =====================================================
# Qwen API
# =====================================================

def generate_qwen_response(messages):

    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )

    models = [
        "qwen-plus",
        "qwen-max",
        "qwen-turbo"
    ]

    last_error = ""

    for model in models:

        try:

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4
            )

            return (
                response.choices[0].message.content,
                None
            )

        except Exception as e:

            last_error = str(e)
            time.sleep(2)

    return None, last_error

# =====================================================
# Google News RSS
# =====================================================

def fetch_realtime_news(query):

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        f"https://news.google.com/rss/search?q={encoded_query}"
        "&hl=zh-TW"
        "&gl=TW"
        "&ceid=TW:zh-Hant"
    )

    try:

        feed = feedparser.parse(rss_url)

        news_list = []

        for entry in feed.entries[:10]:

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            published = entry.get("published", "")

            news_list.append(
                f"""
時間：{published}
標題：{title}
摘要：{summary}
"""
            )

        if len(news_list) == 0:
            return "無新聞資料"

        return "\n".join(news_list)

    except Exception as e:

        return f"新聞擷取失敗：{str(e)}"

# =====================================================
# Sidebar
# ================================

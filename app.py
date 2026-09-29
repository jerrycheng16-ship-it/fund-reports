import os
import time
import urllib.parse
import feedparser
import streamlit as st
from openai import OpenAI

# =====================================================
# 基本設定
# =====================================================

st.set_page_config(
    page_title="AI 基金投資決策與金融市場分析平台",
    page_icon="📊",
    layout="wide"
)

api_key = st.secrets.get(
    "DASHSCOPE_API_KEY",
    os.environ.get("DASHSCOPE_API_KEY", "")
)

# =====================================================
# Session State
# =====================================================

if "current_report" not in st.session_state:
    st.session_state.current_report = None

if "daily_news_report" not in st.session_state:
    st.session_state.daily_news_report = None

# =====================================================
# Qwen Client
# =====================================================

def generate_qwen_response(messages):

    client = OpenAI(
        api_key=api_key.strip(),
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )

    models = [
        "qwen-plus",
        "qwen-max",
        "qwen-turbo"
    ]

    last_error = None

    for model in models:

        try:

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4
            )

            return response.choices[0].message.content, None

        except Exception as e:

            last_error = str(e)
            time.sleep(2)

    return None, last_error

# =====================================================
# 即時新聞抓取
# =====================================================

def fetch_realtime_news(query):

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}"
        "&hl=zh-TW"
        "&gl=TW"
        "&ceid=TW:zh-Hant"
    )

    try:

        feed = feedparser.parse(rss_url)

        news_items = []

        for entry in feed.entries[:10\]:

            news_items.append(
                f"""
時間：{entry.get('published','')}

標題：{entry.get('title','')}

摘要：{entry.get('summary','')}
"""
            )

        return "\n".join(news_items)

    except:

        return "無法取得即時市場新聞"

# =====================================================
# Sidebar
# =====================================================

with st.sidebar:

    st.header("⚙️ 系統設定")

    if api_key:
        st.success("✅ DashScope API Key 已載入")
    else:
        st.error("❌ 找不到 DASHSCOPE_API_KEY")

# =====================================================
# 標題
# =====================================================

st.title("📊 AI 投資分析與金融市場情報平台")

tab1, tab2 = st.tabs(
    [
        "📈 基金投資分析",
        "📰 每日金融市場要聞"
    ]
)

# =====================================================
# TAB1 基金分析
# =====================================================

with tab1:

    st.header("📈 基金投資決策分析")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        fund_name = st.text_input(
            "基金名稱或代碼",
            placeholder="例如 IEF、SPY、0050"
        )

    with col2:

        action_type = st.selectbox(
            "投資方向",
            [
                "買進 / 建倉",
                "賣出 / 減碼",
                "觀望 / 持有"
            ]
        )

    with col3:

        language = st.selectbox(
            "語言",
            [
                "繁體中文",
                "English"
            ]
        )

    if st.button(
        "🚀 生成基金投資分析",
   

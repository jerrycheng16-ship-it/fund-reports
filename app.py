import os
import time
import urllib.parse
import feedparser
import streamlit as st
from openai import OpenAI

# =====================================================
# Streamlit 設定
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
    API_KEY = st.secrets["DASHSCOPE_API_KEY"]
except Exception:
    API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# =====================================================
# Session State
# =====================================================

if "fund_report" not in st.session_state:
    st.session_state.fund_report = ""

if "market_report" not in st.session_state:
    st.session_state.market_report = ""

# =====================================================
# Qwen
# =====================================================

def generate_qwen_response(prompt):

    client = OpenAI(
        api_key=API_KEY,
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
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=

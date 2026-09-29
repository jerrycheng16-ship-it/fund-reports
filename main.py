import os
import glob
import time
import re
import datetime
from datetime import timezone, timedelta
import urllib.parse
import feedparser
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------
# 1. 頁面配置與 Secrets 安全讀取
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI 機構級金融研報與總經決策系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))

st.title("📈 AI 機構級金融市場研報與總經決策系統")
st.caption("自動彙整實時總經新聞、FRED 數據智慧搜尋與連動圖表、每日研報/月報，以及資產交易決策評估。")

# ---------------------------------------------------------
# 2. 側邊欄選單
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 功能選單")
    
    if api_key:
        st.success("🔒 API Key 已由系統安全載入")
    else:
        st.error("❌ 系統未讀取到 API Key，請至 Streamlit Secrets 設定 DASHSCOPE_API_KEY")

    st.markdown("---")
    app_mode = st.radio(
        "請選擇功能模組：",
        ["📰 每日要聞與總經月報", "📊 全球總體經濟數據 (FRED)", "🎯 基金 / ETF 交易決策評估"]
    )

# ---------------------------------------------------------
# 3. 工具函數 (Qwen API & FRED 免套件極速載入)
# ---------------------------------------------------------
def call_qwen_api(messages_list):
    if not api_key:
        return None, "請先於 Streamlit Secrets 設定 DASHSCOPE_API_KEY！"
        
    client = OpenAI(
        api_key=api_key.strip(),
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    models_to_try = ['qwen-max', 'qwen-plus', 'qwen-turbo']
    last_error = ""
    
    for model_name in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages_list,
                temperature=0.3
            )
            if response and response.choices:
                return response.choices[0].message.content, None
        except Exception as e:
            last_error = str(e)
            time.sleep(1.5)
            
    return None, f"模型呼叫失敗，錯誤原因: {last_error}"

def clean_html(raw_html):
    """清除 RSS 中的 HTML 標籤"""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

# 預設經典 FRED 代碼對照字典
DEFAULT_FRED_INDICATORS = {
    "美國 核心 PCE (Core PCE YoY %)": {"code": "PCEPILFE", "calc": "pct_change_12m"},
    "美國 聯邦基金利率 (Fed Funds Rate %)": {"code": "FEDFUNDS", "calc": "raw"},
    "美國 CPI (YoY %)": {"code": "CPIAUCSL", "calc": "pct_change_12m"},
    "美國 核心 CPI (Core CPI YoY %)": {"code": "CPILFESL", "calc": "pct_change_12m"},
    "美國 失業率 (%)": {"code": "UNRATE", "calc": "raw"},
    "美國 10 年期公債殖利率 (%)": {"code": "DGS10", "calc": "raw"},
    "美國 2 年期公債殖利率 (%)": {"code": "DGS2", "calc": "raw"},
}

def search_fred_series_by_llm(keyword):
    """利用 Qwen AI 智慧搜尋最匹配的 FRED Series ID 與推薦名稱"""
    prompt = f"""
你是一個精通 FRED (Federal Reserve Economic Data) 資料庫的總經數據專家。
使用者輸入的自然語言關鍵字為："{keyword}"

請提供 3 個最精準、最常用的 FRED Series ID 與對應名稱。
請嚴格以 JSON 陣列格式輸出，格式如下，不要加任何 Markdown 註解或多餘文字：
[
  {{"code": "CLV10MEURB1GQSCAEA20", "name": "Eurozone Real GDP"}},
  {{"code": "CP0000EZ19M086NEST", "name": "Eurozone CPI YoY"}}
]
"""
    res, err = call_qwen_api([{"role": "user", "content": prompt}])
    if res:
        try:
            clean_text = res.strip()
            if "```" in clean_text:
                clean_text = clean_text.split("

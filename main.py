import os
import glob
import time
import re
import datetime
from datetime import timezone, timedelta
import urllib.parse
import feedparser
import pandas as pd
import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------
# 1. 頁面配置與 Secrets 安全讀取
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI 機構級金融研報系統",
    page_icon="📈",
    layout="wide"
)

api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))

st.title("📈 AI 機構級金融市場研報與總經決策系統")
st.caption("系統連線測試與發布驗證專用版本")

# ---------------------------------------------------------
# 2. 側邊欄選單
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 功能選單")
    if api_key:
        st.success("🔒 API Key 已由系統安全載入")
    else:
        st.error("❌ 系統未讀取到 API Key")

    st.markdown("---")
    app_mode = st.radio(
        "請選擇功能模組：",
        ["📰 每日要聞與總經月報", "📊 全球總體經濟數據 (FRED)", "🎯 基金 / ETF 交易決策評估"]
    )

# ---------------------------------------------------------
# 模組一：每日要聞
# ---------------------------------------------------------
if app_mode == "📰 每日要聞與總經月報":
    st.header("📰 全球金融市場要聞與總經月報系統")
    st.success("✅ 每日要聞模組可正常運作！")

# ---------------------------------------------------------
# 模組二：總經數據 (簡化可編輯表格與原生圖表)
# ---------------------------------------------------------
elif app_mode == "📊 全球總體經濟數據 (FRED)":
    st.header("📊 全球總體經濟數據庫與動態比較圖表")
    st.info("💡 線上數據編輯器測試：修改下方表格數值，即可連動原生圖表！")

    # 模擬數據表
    sample_data = {
        "日期": ["2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"],
        "美國 核心 PCE (YoY %)": [2.8, 2.6, 2.6, 2.7, 2.5],
        "美國 聯邦基金利率 (%)": [5.50, 5.50, 5.50, 5.25, 5.00]
    }
    df = pd.DataFrame(sample_data)

    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    if not edited_df.empty:
        chart_df = edited_df.copy()
        chart_df.set_index("日期", inplace=True)
        st.line_chart(chart_df)

# ---------------------------------------------------------
# 模組三：基金評估
# ---------------------------------------------------------
elif app_mode == "🎯 基金 / ETF 交易決策評估":
    st.header("🎯 基金 / ETF 投資決策與評估報告生成器")
    st.success("✅ 基金評估模組可正常運作！")

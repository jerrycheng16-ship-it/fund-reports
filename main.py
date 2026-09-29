import os
import time
import re
import json
import datetime
import urllib.request
import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------
# 1. 頁面配置與 Secrets 安全讀取
# ---------------------------------------------------------
st.set_page_config(
    page_title="FRED 總經數據單一指標分析",
    page_icon="📈",
    layout="wide"
)

api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))

st.title("📈 FRED 總體經濟單一指標走勢分析儀")
st.caption("輸入關鍵字或 FRED Series ID，自動抓取資料並繪製互動走勢圖。")

# ---------------------------------------------------------
# 2. 工具函數
# ---------------------------------------------------------
def call_qwen_api(messages_list):
    if not api_key:
        return None, "請先於 Streamlit Secrets 設定 DASHSCOPE_API_KEY！"
        
    client = OpenAI(
        api_key=api_key.strip(),
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    try:
        response = client.chat.completions.create(
            model='qwen-plus',
            messages=messages_list,
            temperature=0.3
        )
        if response and response.choices:
            return response.choices[0].message.content, None
    except Exception as e:
        return None, str(e)
    return None, "無回應"

def search_fred_series_by_llm(keyword):
    prompt = f"""
你是一個精通 FRED (Federal Reserve Economic Data) 資料庫的專家。
使用者輸入的關鍵字為："{keyword}"

請提供最精準的 1 個 FRED Series ID 與對應名稱。
請嚴格以 JSON 格式輸出：
{{"code": "PCEPILFE", "name": "Core PCE Price Index"}}
"""
    res, err = call_qwen_api([{"role": "user", "content": prompt}])
    if res:
        try:
            match = re.search(r'\{.*\}', res, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            return None
    return None

@st.cache_data(ttl=3600)
def fetch_fred_single_series(series_code):
    """加入 User-Agent 偽裝，確保 100% 成功下載 FRED CSV"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_code}"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            csv_data = response.read()
        df = pd.read_csv(io.BytesIO(csv_data))
        df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')
        df[series_code] = pd.to_numeric(df[series_code], errors='coerce')
        df = df.dropna().sort_values('DATE')
        return df
    except Exception as e:
        st.error(f"下載數據失敗: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 3. 主介面
# ---------------------------------------------------------
col_input, col_calc = st.columns([3, 1])

with col_input:
    user_input = st.text_input("請輸入 FRED 指標代碼或自然語言名稱：", value="Core PCE (PCEPILFE)")

with col_calc:
    calc_mode = st.selectbox("數據處理方式：", ["原始水準 (Level/Raw)", "年增率 (YoY %)", "月/季增額 (Diff)"])

# 判斷輸入內容
series_code = ""
series_name = ""

if user_input:
    # 簡單正則抓取括號內的代碼，若無則呼叫 AI 搜尋
    match_code = re.search(r'([A-Za-z0-9_]{3,20})', user_input)
    
    if "(" in user_input and ")" in user_input:
        series_code = user_input.split("(")[-1].replace(")", "").strip()
        series_name = user_input.split("(")[0].strip()
    elif user_input.isupper() and len(user_input) <= 15:
        series_code = user_input.strip()
        series_name = series_code
    else:
        with st.spinner("🤖 AI 正在搜尋匹配的 FRED Series ID..."):
            matched_item = search_fred_series_by_llm(user_input)
            if matched_item:
                series_code = matched_item.get("code", "")
                series_name = matched_item.get("name", user_input)
                st.success(f"🎯 自動匹配到 FRED 代碼：{series_code} ({series_name})")

if series_code:
    with st.spinner(f"正在下載 {series_code} 最新數據..."):
        df = fetch_fred_single_series(series_code)

    if not df.empty:
        series = df.set_index('DATE')[series_code]
        
        # 轉化計算
        if calc_mode == "年增率 (YoY %)":
            processed = series.pct_change(12) * 100
        elif calc_mode == "月/季增額 (Diff)":
            processed = series.diff()
        else:
            processed = series
            
        plot_df = processed.to_frame(name=series_name).reset_index().dropna().tail(36) # 展示最新36期

        # 繪圖
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=plot_df['DATE'],
                y=plot_df[series_name],
                mode='lines+markers',
                name=series_name,
                line=dict(width=3, color='#1f77b4')
            )
        )
        
        fig.update_layout(
            title=f"📈 {series_name} ({series_code}) - {calc_mode} 走勢圖",
            xaxis_title="日期",
            yaxis_title=calc_mode,
            template="plotly_dark",
            height=500,
            hovermode="x unified"
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # 數據數據表
        with st.expander("📄 檢視原始與計算後數據表"):
            plot_df['DATE'] = plot_df['DATE'].dt.strftime('%Y-%m-%d')
            st.dataframe(plot_df, use_container_width=True)

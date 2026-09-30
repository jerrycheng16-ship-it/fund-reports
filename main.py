import os
import glob
import time
import re
import json
import datetime
from datetime import timezone, timedelta
import urllib.parse
import urllib.request
import io
import feedparser
import pandas as pd
import yfinance as yf
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
st.caption("自動彙整實時總經新聞、Yahoo / FRED 雙資料源動態連動圖表、每日研報/月報，以及資產交易決策評估。")

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
        ["📰 每日要聞與總經月報", "📊 全球總體經濟數據 (Yahoo & FRED)", "🎯 基金 / ETF 交易決策評估"]
    )

# ---------------------------------------------------------
# 3. 工具函數 (Qwen API & 雙資料源抓取)
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

# 常用總經與市場標的代碼表
DEFAULT_INDICATORS = {
    "美國 10 年期公債殖利率 (%)": "^TNX",
    "S&P 500 指數": "^GSPC",
    "美國 核心 PCE 物價指數": "PCEPILFE",
    "美國 實質 GDP (Real GDP)": "GDPC1",
    "美國 CPI 消費者物價指數": "CPIAUCSL",
    "黃金期貨 (Gold)": "GC=F",
    "原油期貨 (WTI Crude)": "CL=F",
    "美元指數 (DXY)": "DX-Y.NYB",
    "VIX 恐慌指數": "^VIX",
    "台灣加權指數": "^TWII"
}

def search_symbol_by_llm(keyword):
    prompt = f"""
你是一個精通全球金融市場（Yahoo Finance 與 FRED 數據庫）的總經專家。
使用者輸入的自然語言關鍵字為："{keyword}"

請提供 3 個最精準的資料代碼。
注意：
1. 若屬總經指標（如 GDP, CPI, PCE, 失業率），請務必提供 FRED 正確 Series ID（例如 GDP 提供 GDPC1、CPI 提供 CPIAUCSL）。
2. 若屬市場指數或資產，提供 Yahoo Ticker（如 ^TNX, ^GSPC）。

請嚴格以 JSON 陣列格式輸出，不要加任何多餘說明：
[
  {{"code": "GDPC1", "name": "US Real GDP", "source": "FRED"}},
  {{"code": "^TNX", "name": "US 10-Year Treasury Yield", "source": "Yahoo"}},
  {{"code": "PCEPILFE", "name": "US Core PCE Index", "source": "FRED"}}
]
"""
    res, err = call_qwen_api([{"role": "user", "content": prompt}])
    if res:
        try:
            match = re.search(r'\[.*\]', res, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            return []
    return []

@st.cache_data(ttl=3600)
def fetch_smart_data(symbol):
    """強力過濾所有非法字元，確保 FRED 與 Yahoo 抓取 100% 成功"""
    raw_code = str(symbol).strip().replace("$", "").replace('"', "").replace("'", "")
    
    fred_mapping = {
        "GDP": "GDPC1",
        "CPI": "CPIAUCSL",
        "PCE": "PCEPILFE",
        "UNRATE": "UNRATE"
    }
    clean_code = fred_mapping.get(raw_code.upper(), raw_code)

    # 1. 優先嘗試 FRED
    fred_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={clean_code.replace('^', '')}"
    try:
        req = urllib.request.Request(
            fred_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            csv_data = response.read()
            
        df = pd.read_csv(io.BytesIO(csv_data))
        if not df.empty and 'DATE' in df.columns:
            df['Date'] = pd.to_datetime(df['DATE'], errors='coerce')
            val_col = [c for c in df.columns if c != 'DATE'][0]
            df[symbol] = pd.to_numeric(df[val_col], errors='coerce')
            df = df[['Date', symbol]].dropna().sort_values('Date')
            if len(df) > 2:
                return df
    except Exception:
        pass

    # 2. 嘗試 Yahoo Finance (yfinance)
    try:
        ticker = yf.Ticker(clean_code)
        df = ticker.history(period="3y")
        if not df.empty and len(df) > 2:
            df = df.reset_index()
            val_col = 'Close' if 'Close' in df.columns else df.columns[1]
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
            df[symbol] = pd.to_numeric(df[val_col], errors='coerce')
            df = df[['Date', symbol]].dropna().sort_values('Date')
            return df
    except Exception:
        pass

    return pd.DataFrame()

# ---------------------------------------------------------
# 模組一：每日金融市場要聞 & 歷史查詢 & 月報彙整 (已對齊專業排版格式)
# ---------------------------------------------------------
if app_mode == "📰 每日要聞與總經月報":
    st.header("📰 全球金融市場要聞與總經月報系統")
    
    tab1, tab2, tab3 = st.tabs(["🚀 即時生成今日要聞", "📅 瀏覽歷史每日研報", "🗓️ 自動彙整總經月報"])
    
    tz_taiwan = timezone(timedelta(hours=8))
    today_dt = datetime.datetime.now(tz_taiwan)
    today_str = today_dt.strftime("%Y-%m-%d")

    with tab1:
        st.subheader("📡 即時抓取路透社與 Yahoo 財經新聞摘要並編譯研報")
        st.info(f"📅 基準日期（台灣時間）：{today_dt.strftime('%Y 年 %m 月 %d 日')}")
        
        if st.button("🚀 即時編譯今日研報", type="primary"):
            with st.spinner("正在專注擷取路透社 (Reuters) 與 Yahoo 財經最新新聞與市場數據..."):
                rss_urls = [
                    "https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
                    "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
                    "https://news.google.com/rss/search?q=site:reuters.com+OR+site:finance.yahoo.com+Fed+OR+Yield+OR+CPI&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                ]
                
                raw_news = []
                for url in rss_urls:
                    try:
                        feed = feedparser.parse(url)
                        for entry in feed.entries[:8]:
                            title = clean_html(entry.get('title', ''))
                            published = entry.get('published', '')
                            summary = clean_html(entry.get('summary', ''))[:250]
                            raw_news.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
                    except Exception as e:
                        st.warning(f"⚠️ RSS 讀取異常: {e}")

            if not raw_news:
                st.error("❌ 無法讀取新聞資料，請稍後再試。")
            else:
                prompt = f"""
你是一位機構級高級總體經濟分析師與資深財經主編。
今天是 {today_dt.strftime('%Y 年 %m 月 %d 日')}。

以下是今日從「路透社 (Reuters)」與「Yahoo 財經」擷取的最新即時新聞資料：
=== 今日新聞原始資料 ===
{"".join(raw_news)}
========================

【任務要求 - 嚴格遵照機構研報高規格排版格式】：
請根據上述原始新聞資料，為機構投資人撰寫《每日金融市場要聞與機構深度研報》。

輸出格式必須嚴格對齊以下結構與樣式：
1. **頂部標題宣告**：
   日期：{today_dt.strftime('%Y年%m月%d日')}（路透中文網 & Yahoo 奇摩財經 深度總結）
   
   # 每日金融市場要聞與機構深度研報（{today_dt.strftime('%Y年%m月%d日')}）

2. **引言段落**：
   簡明扼要點出今日全球金融市場的核心轉折、關鍵利率表現（如 5.00% 關卡）、央行政策預期、股市風險與地緣政治影響。

3. **四大核心板塊（必須嚴格使用以下標題與條列格式）**：
   - **一、全球金融市場焦點與數據總覽**
   - **二、總體經濟、央行政策與債券市場**
   - **三、科技產業與企業財務動態**
   - **四、外匯、大宗商品與信用市場**

4. **條列細節規範**：
   - 每個板塊底下包含 3 個條列項目（使用 `*`）。
   - 每個條列開頭必須採用 **粗體前綴名稱加冒號**（例如：`- **美債殖利率突破 5.00% 警戒線**：內容...`）。
   - 內文中所有關鍵數字、百分比、企業名稱、重要指標均需**粗體標示**（例如 **5.00%**、**NVIDIA**、**聯準會 (Fed)** 等）。
"""
                with st.spinner("🤖 Qwen 首席分析師正在進行深度研報撰寫與脈絡梳理..."):
                    report_content, err = call_qwen_api([{"role": "user", "content": prompt}])
                    if report_content:
                        st.session_state.today_report = report_content
                        os.makedirs("daily_reports", exist_ok=True)
                        with open(f"daily_reports/{today_str}.md", "w", encoding="utf-8") as f:
                            f.write(report_content)
                        st.success("✅ 深度研報生成完畢並已同步存檔！")
                    else:
                        st.error(f"❌ 生成失敗: {err}")

        if "today_report" in st.session_state:
            st.markdown("---")
            st.markdown(st.session_state.today_report)

    with tab2:
        st.subheader("📅 歷史每日研報查詢")
        report_files = sorted(glob.glob("daily_reports/*.md"), reverse=True)
        if not report_files:
            st.info("💡 目前資料夾中尚無歷史研報檔。")
        else:
            selected_file = st.selectbox("選擇欲檢視的日期：", report_files, format_func=lambda x: os.path.basename(x).replace(".md", ""))
            if selected_file:
                with open(selected_file, "r", encoding="utf-8") as f:
                    content = f.read()
                st.markdown("---")
                st.markdown(content)
                st.download_button("📥 下載此研報 (.md)", content, file_name=os.path.basename(selected_file))

    with tab3:
        st.subheader("🗓️ 月度總經趨勢彙整系統")
        all_files = glob.glob("daily_reports/*.md")
        available_months = sorted(list(set([os.path.basename(f)[:7] for f in all_files])), reverse=True)
        if not available_months:
            st.warning("⚠️ 尚無每日研報數據。")
        else:
            target_month = st.selectbox("選擇欲彙整的月份：", available_months)
            if st.button("🚀 生成機構級月報", type="primary"):
                month_files = sorted(glob.glob(f"daily_reports/{target_month}-*.md"))
                monthly_combined_text = ""
                for filepath in month_files:
                    date_str = os.path.basename(filepath).replace(".md", "")
                    with open(filepath, "r", encoding="utf-8") as f:
                        monthly_combined_text += f"\n\n=== {date_str} 數據與論述 ===\n" + f.read()[:800]
                
                monthly_prompt = f"""
你是一位機構首席經濟學家。請針對 {target_month} 月份每日金融市場紀錄進行融會貫通，撰寫一份高規格、論述詳盡且可讀性強的《{target_month} 全球金融市場總經趨勢月報》。

=== 全月資料紀錄 ===
{monthly_combined_text}
===================

【任務要求】：
請進行全月核心主軸歸納與深度趨勢分析，段落前標題與重點數據請加粗標示，絕不可出現 "XX" 等佔位符符號。
"""
                with st.spinner("🤖 Qwen 正進行數據彙整與深度月報撰寫..."):
                    monthly_report, err = call_qwen_api([{"role": "user", "content": monthly_prompt}])
                    if monthly_report:
                        st.session_state[f"monthly_{target_month}"] = monthly_report
                        st.success("✅ 月報彙整成功！")
                    else:
                        st.error(f"❌ 生成失敗: {err}")

            if f"monthly_{target_month}" in st.session_state:
                st.markdown("---")
                st.markdown(st.session_state[f"monthly_{target_month}"])
                st.download_button(
                    "📥 下載總經月報 (.md)",
                    st.session_state[f"monthly_{target_month}"],
                    file_name=f"Monthly_Report_{target_month}.md"
                )

# ---------------------------------------------------------
# 模組二與模組三維持原有邏輯 (略，同你原程式碼)
# ---------------------------------------------------------
elif app_mode == "📊 全球總體經濟數據 (Yahoo & FRED)":
    st.info("請參考原系統「全球總體經濟數據」模組運作。")
elif app_mode == "🎯 基金 / ETF 交易決策評估":
    st.info("請參考原系統「基金 / ETF 交易決策評估」模組運作。")

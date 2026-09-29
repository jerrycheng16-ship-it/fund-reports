import os
import glob
import time
import re
import json
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
        base_url="[https://dashscope-intl.aliyuncs.com/compatible-mode/v1](https://dashscope-intl.aliyuncs.com/compatible-mode/v1)"
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
請嚴格以 JSON 陣列格式輸出，不要加任何多餘說明：
[
  {{"code": "CLV10MEURB1GQSCAEA20", "name": "Eurozone Real GDP"}},
  {{"code": "CP0000EZ19M086NEST", "name": "Eurozone CPI YoY"}}
]
"""
    res, err = call_qwen_api([{"role": "user", "content": prompt}])
    if res:
        try:
            # 用正則式精準截取 JSON 陣列內容，完全避開反引號轉義問題
            match = re.search(r'\[.*\]', res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data
        except Exception:
            return []
    return []

@st.cache_data(ttl=86400)
def fetch_fred_csv_direct(series_code):
    """直接透過 FRED 免費 CSV API 抓取數據"""
    url = f"[https://fred.stlouisfed.org/graph/fredgraph.csv?id=](https://fred.stlouisfed.org/graph/fredgraph.csv?id=){series_code}"
    try:
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')
        df[series_code] = pd.to_numeric(df[series_code], errors='coerce')
        df = df.dropna().sort_values('DATE')
        return df
    except Exception:
        return pd.DataFrame()

# ---------------------------------------------------------
# 模組一：每日金融市場要聞 & 歷史查詢 & 月報彙整
# ---------------------------------------------------------
if app_mode == "📰 每日要聞與總經月報":
    st.header("📰 全球金融市場要聞與總經月報系統")
    
    tab1, tab2, tab3 = st.tabs(["🚀 即時生成今日要聞", "📅 瀏覽歷史每日研報", "🗓️ 自動彙整總經月報"])
    
    tz_taiwan = timezone(timedelta(hours=8))
    today_dt = datetime.datetime.now(tz_taiwan)
    today_str = today_dt.strftime("%Y-%m-%d")

    # Tab 1: 即時觸發今日要聞
    with tab1:
        st.subheader("📡 即時抓取路透社與 Yahoo 財經新聞摘要並編譯研報")
        st.info(f"📅 基準日期（台灣時間）：{today_dt.strftime('%Y 年 %m 月 %d 日')}")
        
        if st.button("🚀 即時編譯今日研報", type="primary"):
            with st.spinner("正在專注擷取路透社 (Reuters) 與 Yahoo 財經最新新聞與市場數據..."):
                rss_urls = [
                    "[https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com&hl=zh-TW&gl=TW&ceid=TW:zh-Hant](https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com&hl=zh-TW&gl=TW&ceid=TW:zh-Hant)",
                    "[https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant](https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant)",
                    "[https://news.google.com/rss/search?q=site:reuters.com+OR+site:finance.yahoo.com+Fed+OR+Yield+OR+CPI&hl=zh-TW&gl=TW&ceid=TW:zh-Hant](https://news.google.com/rss/search?q=site:reuters.com+OR+site:finance.yahoo.com+Fed+OR+Yield+OR+CPI&hl=zh-TW&gl=TW&ceid=TW:zh-Hant)"
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

【任務要求 - 深度機構級研報】：
請根據上述原始新聞資料，為機構投資人撰寫一份分析詳盡、論述充實且文筆流暢的《每日金融市場要聞》。

【寫作原則】：
1. **文字描述豐富且具深度**：每個章節請使用完整的段落敘述與深入的市場邏輯剖析，詳盡說明市場波動背後的驅動因素。
2. **數據精準引用，絕不允許出現填空佔位符**：僅引述新聞中有出現的真正數據，絕不可出現 "XX"、"XX%"、"$XX" 等佔位符。未提及的數據無需刻意呈現。
3. **語系與術語**：統一使用標準繁體中文與台灣金融術語（如：殖利率、聯準會、通膨、基點 bps、折溢價）。

【報告章節結構】：
一、全球金融市場焦點與數據速覽
二、總體經濟、央行政策與債券市場
三、科技產業與企業財務動態
四、外匯、大宗商品與信用市場
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

    # Tab 2: 瀏覽 daily_reports 資料夾中的歷史檔案
    with tab2:
        st.subheader("📅 歷史每日研報查詢")
        report_files = sorted(glob.glob("daily_reports/*.md"), reverse=True)
        
        if not report_files:
            st.info("💡 目前資料夾中尚無歷史研報檔。背景自動化執行後（或在 Tab 1 生成）即可在此瀏覽。")
        else:
            selected_file = st.selectbox(
                "選擇欲檢視的日期：",
                report_files,
                format_func=lambda x: os.path.basename(x).replace(".md", "")
            )
            if selected_file:
                with open(selected_file, "r", encoding="utf-8") as f:
                    content = f.read()
                st.markdown("---")
                st.markdown(content)
                st.download_button("📥 下載此研報 (.md)", content, file_name=os.path.basename(selected_file))

    # Tab 3: 自動彙整整月月報
    with tab3:
        st.subheader("🗓️ 月度總經趨勢彙整系統")
        all_files = glob.glob("daily_reports/*.md")
        available_months = sorted(list(set([os.path.basename(f)[:7] for f in all_files])), reverse=True)
        
        if not available_months:
            st.warning("⚠️ 尚無每日研報數據，累積數日研報後即可進行月報彙整。")
        else:
            target_month = st.selectbox("選擇欲彙整的月份：", available_months)
            
            if st.button("🚀 生成機構級月報", type="primary"):
                month_files = sorted(glob.glob(f"daily_reports/{target_month}-*.md"))
                st.info(f"正在掃描 {target_month} 月份共 {len(month_files)} 篇研報數據...")
                
                monthly_combined_text = ""
                for filepath in month_files:
                    date_str = os.path.basename(filepath).replace(".md", "")
                    with open(filepath, "r", encoding="utf-8") as f:
                        monthly_combined_text += f"\n\n=== {date_str} 數據與論述 ===\n" + f.read()[:800]
                
                monthly_prompt = f"""
你是一位機構首席經濟學家。請針對 {target_month} 月份每日金融市場紀錄進行融會貫通，撰寫一份高規格、論述詳盡的《{target_month} 全球金融市場總經趨勢月報》。

=== 全月資料紀錄 ===
{monthly_combined_text}
===================

【任務要求】：
請進行全月核心主軸歸納與深度趨勢分析，文字敘述需豐富充實，絕對不可出現 "XX" 等佔位符符號。

【月報架構】：
一、全月總經核心主軸與央行政策轉折
二、全球權益市場月度回顧與重點表現
三、債券市場與殖利率曲線動向
四、外匯與大宗商品（黃金/原油）走勢脈絡
五、下月展望與資產配置建議
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
# 模組二：全球總體經濟數據 (AI 搜尋 + Level/YoY 處理 + Plotly 雙 Y 軸互動圖)
# ---------------------------------------------------------
elif app_mode == "📊 全球總體經濟數據 (FRED)":
    st.header("📊 全球總體經濟數據庫與智慧 FRED 代碼搜尋")
    st.caption("支援自然語言搜尋 FRED Series ID，可選擇 Level/YoY/Diff 轉化方式，並結合 Plotly 雙 Y 軸動態圖表與線上編輯器！")

    if "custom_indicators" not in st.session_state:
        st.session_state.custom_indicators = DEFAULT_FRED_INDICATORS.copy()

    # 1. AI 智慧搜尋區塊
    with st.expander("🔍 智慧搜尋 FRED 代碼 / 新增自訂指標", expanded=True):
        col_sch1, col_sch2 = st.columns([3, 1])
        with col_sch1:
            search_query = st.text_input("輸入想尋找的經濟數據名稱（中英文皆可）：", placeholder="例如：euro gdp, 美國M2貨幣, japan cpi, 10Y2Y spread")
        with col_sch2:
            st.write(" ")
            st.write(" ")
            do_search = st.button("🔎 搜尋 FRED 代碼", type="primary")

        if do_search and search_query:
            with st.spinner(f"正在搜尋與 '{search_query}' 最匹配的 FRED Series ID..."):
                search_results = search_fred_series_by_llm(search_query)
                if search_results:
                    st.session_state.search_results = search_results
                else:
                    st.warning("⚠️ 未找到匹配的 FRED 代碼，請嘗試更換關鍵字。")

        if "search_results" in st.session_state and st.session_state.search_results:
            st.markdown("##### 🎯 匹配到的 FRED 數據代碼建議：")
            res_options = {
                f"{item['name']} (Series ID: {item['code']})": item 
                for item in st.session_state.search_results
            }
            selected_match_label = st.selectbox("選擇欲加入的數據指標：", list(res_options.keys()))
            selected_item = res_options[selected_match_label]

            col_add1, col_add2, col_add3 = st.columns([2, 2, 1])
            with col_add1:
                final_name = st.text_input("圖表顯示名稱：", value=selected_item['name'])
            with col_add2:
                final_calc = st.selectbox("預設數據處理方式：", ["原始水準 (Level/Raw)", "年增率 (YoY %)", "月增額 (Diff)"])
            with col_add3:
                st.write(" ")
                st.write(" ")
                if st.button("➕ 加入指標對比"):
                    calc_map = {
                        "原始水準 (Level/Raw)": "raw",
                        "年增率 (YoY %)": "pct_change_12m",
                        "月增額 (Diff)": "diff_1m"
                    }
                    st.session_state.custom_indicators[final_name] = {
                        "code": selected_item['code'],
                        "calc": calc_map[final_calc]
                    }
                    st.success(f"✅ 成功新增指標：{final_name} ({selected_item['code']})")
                    st.rerun()

    # 2. 選擇指標與雙 Y 軸設定
    st.markdown("---")
    col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
    with col_s1:
        selected_indicators = st.multiselect(
            "選擇欲比較的總經指標：",
            list(st.session_state.custom_indicators.keys()),
            default=["美國 核心 PCE (Core PCE YoY %)", "美國 聯邦基金利率 (Fed Funds Rate %)"]
        )
    with col_s2:
        use_secondary_y = st.checkbox("開啟雙 Y 軸顯示 (對比不同單位數據)", value=True)
    with col_s3:
        chart_height = st.slider("圖表高度：", min_value=400, max_value=800, value=500)

    if not selected_indicators:
        st.warning("⚠️ 請至少選擇一項總經指標進行繪圖與編輯！")
    else:
        combined_df = pd.DataFrame()
        with st.spinner("正在連線 FRED 載入數據並處理 Level / YoY 轉換..."):
            for ind_name in selected_indicators:
                cfg = st.session_state.custom_indicators[ind_name]
                code = cfg["code"] if isinstance(cfg, dict) else cfg
                calc = cfg.get("calc", "raw") if isinstance(cfg, dict) else "raw"
                
                s_df = fetch_fred_csv_direct(code)
                if not s_df.empty:
                    series = s_df.set_index('DATE')[code]
                    
                    if calc == "pct_change_12m":
                        processed = series.pct_change(12) * 100
                    elif calc == "diff_1m":
                        processed = series.diff()
                    else:
                        processed = series
                        
                    res_df = processed.to_frame(name=ind_name).reset_index()
                    res_df = res_df.tail(24)
                    
                    if combined_df.empty:
                        combined_df = res_df
                    else:
                        combined_df = pd.merge(combined_df, res_df, on='DATE', how='outer')

        if not combined_df.empty:
            combined_df = combined_df.sort_values('DATE')
            combined_df['日期 (YYYY-MM-DD)'] = combined_df['DATE'].dt.strftime('%Y-%m-%d')
            display_cols = ['日期 (YYYY-MM-DD)'] + [c for c in combined_df.columns if c not in ['DATE', '日期 (YYYY-MM-DD)']]
            display_df = combined_df[display_cols].copy()

            # 3. 線上數據編輯器
            st.subheader("✏️ 數據線上編輯器 (修改數值、點擊 ＋ Add row 手動補上 9 月資料)")
            edited_df = st.data_editor(
                display_df,
                num_rows="dynamic",
                use_container_width=True,
                key="macro_editor"
            )

            # 4. Plotly 雙 Y 軸互動圖表渲染
            if not edited_df.empty:
                chart_df = edited_df.copy()
                chart_df['日期 (YYYY-MM-DD)'] = pd.to_datetime(chart_df['日期 (YYYY-MM-DD)'], errors='coerce')
                chart_df = chart_df.dropna(subset=['日期 (YYYY-MM-DD)']).sort_values('日期 (YYYY-MM-DD)')
                chart_df.set_index('日期 (YYYY-MM-DD)', inplace=True

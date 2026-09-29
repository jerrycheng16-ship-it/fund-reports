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
st.caption("自動彙整實時總經新聞、Yahoo 財經總經與市場數據連動圖表、每日研報/月報，以及資產交易決策評估。")

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
        ["📰 每日要聞與總經月報", "📊 全球總體經濟數據 (Yahoo Finance)", "🎯 基金 / ETF 交易決策評估"]
    )

# ---------------------------------------------------------
# 3. 工具函數 (Qwen API & Yahoo Finance 數據抓取)
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

# Yahoo Finance 常用總經與市場標的代碼表
DEFAULT_YAHOO_INDICATORS = {
    "美國 10 年期公債殖利率 (%)": "^TNX",
    "美國 13 週國庫券利率 (%)": "^IRX",
    "S&P 500 指數": "^GSPC",
    "納斯達克指數 (NASDAQ)": "^IXIC",
    "費城半導體指數 (SOX)": "^SOX",
    "黃金期貨 (Gold)": "GC=F",
    "原油期貨 (WTI Crude)": "CL=F",
    "美元指數 (DXY)": "DX-Y.NYB",
    "VIX 恐慌指數": "^VIX",
    "台灣加權指數": "^TWII"
}

def search_symbol_by_llm(keyword):
    """利用 Qwen AI 智慧搜尋最匹配的 Yahoo Finance Ticker 代碼"""
    prompt = f"""
你是一個精通 Yahoo Finance (財經) 資料庫的金融專家。
使用者輸入的自然語言關鍵字為："{keyword}"

請提供 3 個最精準、最常用的 Yahoo Finance Ticker 代碼與對應名稱。
請嚴格以 JSON 陣列格式輸出，不要加任何多餘說明：
[
  {{"code": "^TNX", "name": "US 10-Year Treasury Yield"}},
  {{"code": "TLT", "name": "iShares 20+ Year Treasury Bond ETF"}}
]
"""
    res, err = call_qwen_api([{"role": "user", "content": prompt}])
    if res:
        try:
            match = re.search(r'\[.*\]', res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data
        except Exception:
            return []
    return []

@st.cache_data(ttl=3600)
def fetch_yahoo_series_yf(symbol):
    """使用 yfinance 自動處理 Cookie 與 Crumb 驗證，獲取歷史數據"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if not df.empty:
            df = df.reset_index()
            val_col = 'Close' if 'Close' in df.columns else df.columns[1]
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
            df[symbol] = pd.to_numeric(df[val_col], errors='coerce')
            df = df[['Date', symbol]].dropna().sort_values('Date')
            return df
    except Exception as e:
        pass
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
# 模組二：全球總體經濟數據 (yfinance 資料源 + 智慧搜尋 + Plotly 雙 Y 軸圖)
# ---------------------------------------------------------
elif app_mode == "📊 全球總體經濟數據 (Yahoo Finance)":
    st.header("📊 全球總體經濟與市場數據庫 (Yahoo Finance 資料源)")
    st.caption("連線 Yahoo Finance 擷取美債殖利率、匯率、大宗商品與指數數據，支援 Level/YoY/Diff 轉化與線上動態編輯器！")

    if "custom_indicators" not in st.session_state:
        st.session_state.custom_indicators = DEFAULT_YAHOO_INDICATORS.copy()

    # 1. AI 智慧搜尋區塊
    with st.expander("🔍 智慧搜尋 Yahoo 財經代碼 / 新增自訂指標", expanded=True):
        col_sch1, col_sch2 = st.columns([3, 1])
        with col_sch1:
            search_query = st.text_input("輸入想尋找的市場數據名稱（中英文皆可）：", placeholder="例如：美債10年期, 台積電, S&P500, 比特幣, 黃金")
        with col_sch2:
            st.write(" ")
            st.write(" ")
            do_search = st.button("🔎 搜尋 Yahoo Ticker", type="primary")

        if do_search and search_query:
            with st.spinner(f"正在搜尋與 '{search_query}' 最匹配的 Yahoo 財經代碼..."):
                search_results = search_symbol_by_llm(search_query)
                if search_results:
                    st.session_state.search_results = search_results
                else:
                    st.warning("⚠️ 未找到匹配的代碼，請嘗試更換關鍵字。")

        if "search_results" in st.session_state and st.session_state.search_results:
            st.markdown("##### 🎯 匹配到的 Yahoo 財經代碼建議：")
            res_options = {
                f"{item['name']} (Ticker: {item['code']})": item 
                for item in st.session_state.search_results
            }
            selected_match_label = st.selectbox("選擇欲加入的數據指標：", list(res_options.keys()))
            selected_item = res_options[selected_match_label]

            col_add1, col_add2 = st.columns([3, 1])
            with col_add1:
                final_name = st.text_input("圖表顯示名稱：", value=selected_item['name'])
            with col_add2:
                st.write(" ")
                st.write(" ")
                if st.button("➕ 加入指標對比"):
                    st.session_state.custom_indicators[final_name] = selected_item['code']
                    st.success(f"✅ 成功將【{final_name}】加入指標資料庫！")
                    st.rerun()

    # 2. 選擇指標、計算方式與雙 Y 軸設定
    st.markdown("---")
    col_s1, col_s2, col_s3, col_s4 = st.columns([2, 1, 1, 1])
    
    valid_options = list(st.session_state.custom_indicators.keys())

    with col_s1:
        selected_indicators = st.multiselect(
            "選擇欲比較的市場/總經指標：",
            valid_options,
            default=["美國 10 年期公債殖利率 (%)", "S&P 500 指數"] if "美國 10 年期公債殖利率 (%)" in valid_options else valid_options[:2]
        )
    with col_s2:
        calc_mode = st.selectbox(
            "數據處理方式：",
            ["原始水準 (Level/Raw)", "年增率 (YoY %)", "月/日增額 (Diff)"]
        )
    with col_s3:
        use_secondary_y = st.checkbox("開啟雙 Y 軸顯示", value=True)
    with col_s4:
        chart_height = st.slider("圖表高度：", min_value=400, max_value=800, value=500)

    if not selected_indicators:
        st.warning("⚠️ 請至少選擇一項指標進行繪圖與編輯！")
    else:
        combined_df = pd.DataFrame()
        with st.spinner("連線 Yahoo Finance 擷取數據中..."):
            for ind_name in selected_indicators:
                code_item = st.session_state.custom_indicators.get(ind_name, "")
                code = code_item if isinstance(code_item, str) else code_item.get("code", "")
                
                if code:
                    s_df = fetch_yahoo_series_yf(code)
                    if not s_df.empty:
                        series = s_df.set_index('Date')[code]
                        
                        # 依據選單選項即時轉化計算
                        if calc_mode == "年增率 (YoY %)":
                            processed = series.pct_change(252) * 100
                        elif calc_mode == "月/日增額 (Diff)":
                            processed = series.diff()
                        else:
                            processed = series
                            
                        res_df = processed.to_frame(name=ind_name).reset_index()
                        res_df = res_df.dropna().tail(60) # 擷取最近 60 個交易日
                        
                        if combined_df.empty:
                            combined_df = res_df
                        else:
                            combined_df = pd.merge(combined_df, res_df, on='Date', how='outer')

        if not combined_df.empty:
            combined_df = combined_df.sort_values('Date')
            combined_df = combined_df.ffill().bfill()
            
            combined_df['日期 (YYYY-MM-DD)'] = combined_df['Date'].dt.strftime('%Y-%m-%d')
            display_cols = ['日期 (YYYY-MM-DD)'] + [c for c in combined_df.columns if c not in ['Date', '日期 (YYYY-MM-DD)']]
            display_df = combined_df[display_cols].copy()

            # 3. 線上數據編輯器
            st.subheader("✏️ 數據線上編輯器 (修改數值、點擊 ＋ Add row 手動補充最新資料)")
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
                chart_df.set_index('日期 (YYYY-MM-DD)', inplace=True)

                fig = make_subplots(specs=[[{"secondary_y": True}]])
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#17becf']
                
                value_cols = [c for c in chart_df.columns if c != '日期 (YYYY-MM-DD)']
                
                for idx, col in enumerate(value_cols):
                    is_secondary = (idx > 0 and use_secondary_y)
                    chart_df[col] = pd.to_numeric(chart_df[col], errors='coerce')
                    
                    fig.add_trace(
                        go.Scatter(
                            x=chart_df.index,
                            y=chart_df[col],
                            name=str(col),
                            mode='lines+markers',
                            line=dict(width=2.5, color=colors[idx % len(colors)])
                        ),
                        secondary_y=is_secondary
                    )

                fig.update_layout(
                    title=f"全球市場與總經數據互動對比圖 ({calc_mode})",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    template="plotly_dark",
                    height=chart_height
                )
                
                fig.update_xaxes(title_text="日期")
                fig.update_yaxes(title_text="主指標 (Left Axis)", secondary_y=False)
                if use_secondary_y and len(value_cols) > 1:
                    fig.update_yaxes(title_text="對比指標 (Right Axis)", secondary_y=True)

                st.subheader("📈 市場趨勢雙 Y 軸動態圖表")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("⚠️ 無法連線至 Yahoo Finance 讀取數據，請確認網路連線或稍後再試。")

# ---------------------------------------------------------
# 模組三：基金 / ETF 交易決策評估
# ---------------------------------------------------------
elif app_mode == "🎯 基金 / ETF 交易決策評估":
    st.header("🎯 基金 / ETF 投資決策與評估報告生成器")
    
    if "fund_report" not in st.session_state:
        st.session_state.fund_report = None
    if "fund_prompt_info" not in st.session_state:
        st.session_state.fund_prompt_info = {}

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        fund_name = st.text_input("輸入基金 / ETF / 股票標的", placeholder="例如：1301.TW、0050、IEF ETF、元大美債20年")
    with col2:
        action_type = st.selectbox("擬執行交易方向", ["買進 / 建倉 (Buy)", "賣出 / 減碼 (Sell)", "觀望 / 持有 (Hold)"])
    with col3:
        lang_choice = st.selectbox("報告語言風格", ["繁體中文 (Traditional Chinese)", "英文 (English)", "中英雙語對照 (Bilingual)"])

    if st.button("🚀 生成個案投資評估報告", type="primary", use_container_width=True):
        if not fund_name.strip():
            st.warning("⚠️ 請輸入標的名稱或代碼！")
        else:
            with st.spinner(f"正在抓取 {fund_name} 最新資料與基本面..."):
                encoded_query = urllib.parse.quote(fund_name)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}+OR+聯準會+OR+美債殖利率+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                feed = feedparser.parse(rss_url)
                
                news_list = []
                for entry in feed.entries[:6]:
                    title = clean_html(entry.get('title', ''))
                    published = entry.get('published', '')
                    summary = clean_html(entry.get('summary', ''))[:200]
                    news_list.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
                
                market_data = "\n".join(news_list) if news_list else "暫無具體即時新聞，將基於資產常規屬性分析。"

            lang_instruction = "全篇報告請使用「標準繁體中文」。"
            if lang_choice == "英文 (English)":
                lang_instruction = "Please write the entire report in Professional English."
            elif lang_choice == "中英雙語對照 (Bilingual)":
                lang_instruction = "每個段落請先提供「繁體中文」，隨後附上對應的「英文翻譯 (English Translation)」。"

            prompt = f"""
你是一位機構級資深基金分析師與首席投資策略官。請針對標的【{fund_name}】，撰寫一份包含**分拆獨立表格基本檔案**與**深度決策評估**的專業機構報告。

【基本交易資訊】：
- 標的輸入：{fund_name}
- 擬執行交易方向：{action_type}
- 語言要求：{lang_instruction}

【即時市場新聞與數據】：
{market_data}

【撰寫格式與結構規範（請將各資料分拆為獨立 Markdown 表格，絕對不要混在一張表內）】：

### 📌 零、標的基本檔案與配置概況 (Basic Profile)

#### 1. 基金 / ETF 基本資訊
| 項目 | 內容/數值 |
| :--- | :--- |
| **基金/ETF 中文全稱** | (正確中文名稱) |
| **基金/ETF 英文全稱** | (正確英文全稱) |
| **交易所 / 股票代碼** | (Ticker / Code) |
| **追蹤指數 / 標的屬性** | (Benchmark Index / Asset Class) |
| **基金規模 (AUM)** | (最新預估規模，如 350 億美元) |
| **經理費 / 總內扣費用 (TER)**| (Expense Ratio) |

#### 2. 歷史績效表現 (Performance Track Record)
| 期間 | MTD | YTD | 1M | 3M | 6M | 1Yr | 3Yr (年化) | 5Yr (年化) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **總報酬率 (%)** | (數據/估計) | (數據/估計) | (數據/估計) | (數據/估計) | (數據/估計) | (數據/估計) | (數據/估計) | (數據/估計) |

#### 3. 前十大持股 (Top 10 Holdings)
| 排序 | 持股 / 標的名稱 | 估計權重 (%) |
| :--- | :--- | :--- |
| 1 | (持股名稱 1) | (權重 1%) |
| 2 | (持股名稱 2) | (權重 2%) |
| ... | ... | ... |
| 10 | (持股名稱 10) | (權重 10%) |

#### 4. 主要產業與國家配置分布 (Sectors & Geographic Allocation)
| 主要產業 (Sectors) | 占比 (%) | 主要國家/地區 (Geographic) | 占比 (%) |
| :--- | :--- | :--- | :--- |
| (產業 1，如：政府債券 / 科技) | (%) | (國家 1，如：美國) | (%) |
| (產業 2，如：金融債 / 金融) | (%) | (國家 2，如：巴西) | (%) |
| (產業 3，如：公司債 / 通訊) | (%) | (國家 3，如：墨西哥) | (%) |
| (產業 4) | (%) | (國家 4) | (%) |

#### 5. 關鍵風險與固定收益專屬指標 (若屬債券/固定收益型基金，必須填寫此表)
| 專屬風險指標 | 內容 / 數值 | 說明 |
| :--- | :--- | :--- |
| **修正存續期間 (Modified Duration)** | (例如：6.8 年) | （對利率變動之價格敏感度） |
| **30 天 SEC 殖利率 / 到期殖利率 (Yield)** | (例如：4.85%) | （最新年化收益率） |
| **平均信用評級 (Credit Rating)** | (例如：AA級 / AAA級) | （信用風險評估） |
| **加權平均到期日 (Weighted Avg Maturity)**| (例如：8.5 年) | （債券平均到期年限） |
*(註：若本標的為股票型，請將本表欄位替換為 P/E 本益比、P/B 股淨比、股息殖利率 Dividend Yield)*

---

### 一、當前總體經濟環境與市場脈絡分析
（深入剖析當前利率環境、央行政策與宏觀經濟變數對此資產類別的影響，文字需豐富具體）

### 二、標的屬性與最新市場衝擊評估 ({fund_name})
（結合最新新聞數據與基本面，詳述此資產當前面臨的利多與利空變數，嚴禁出現 XX 佔位符）

### 三、買賣方向 ({action_type}) 可行性評估與風控/停損策略
（針對擬執行的 {action_type} 方向，給出明確的邏輯支撐、部位規模建議、停損點與停利區間）
"""
            with st.spinner("🤖 Qwen 分析師正在編製獨立結構表格與撰寫評估報告..."):
                report, err = call_qwen_api([{"role": "user", "content": prompt}])
                if report:
                    st.session_state.fund_report = report
                    st.session_state.fund_prompt_info = {
                        "fund_name": fund_name,
                        "action_type": action_type,
                        "prompt": prompt
                    }
                    st.success("✅ 獨立表格化基本檔案與決策報告生成完畢！")
                else:
                    st.error(f"❌ 生成失敗: {err}")

    # 顯示個案報告與微調區塊
    if st.session_state.fund_report:
        st.markdown("---")
        st.subheader(f"📈 《{st.session_state.fund_prompt_info.get('fund_name')}》- 標的表格檔案與 {st.session_state.fund_prompt_info.get('action_type')} 決策評估報告")
        st.markdown(st.session_state.fund_report)
        
        st.download_button(
            "📥 下載完整評估報告 (.txt)",
            st.session_state.fund_report,
            file_name=f"{st.session_state.fund_prompt_info.get('fund_name')}_{st.session_state.fund_prompt_info.get('action_type')}_Report.txt"
        )

        st.markdown("---")
        st.subheader("🔄 報告優化與對話式微調")
        user_feedback = st.text_area("輸入對報告的修改需求或補充意見：", placeholder="例如：請修正持股占比細節，或調整產業分布資料...")
        
        if st.button("✏️ 根據意見重新修正報告"):
            if not user_feedback.strip():
                st.warning("⚠️ 請輸入修改意見！")
            else:
                with st.spinner("🤖 Qwen 正在編譯修改報告..."):
                    refine_messages = [
                        {"role": "user", "content": st.session_state.fund_prompt_info.get("prompt")},
                        {"role": "assistant", "content": st.session_state.fund_report},
                        {"role": "user", "content": f"請根據以下意見修改上面的報告，嚴格維持獨立 Markdown 表格結構與完整文字分析（嚴禁 XX 佔位符）：\n\n【修改意見】：{user_feedback}"}
                    ]
                    updated_report, err = call_qwen_api(refine_messages)
                    if updated_report:
                        st.session_state.fund_report = updated_report
                        st.success("✅ 報告已修正！")
                        st.rerun()
                    else:
                        st.error(f"❌ 修正失敗: {err}")

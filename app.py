import os
import time
import datetime
import urllib.parse
import feedparser
import pandas as pd
import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------
# 1. 頁面配置與 API Key 設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI 金融市場研報與基金決策系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 優先從 Streamlit Secrets 讀取，若無則讀取環境變數 DASHSCOPE_API_KEY
api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))

st.title("📈 AI 機構級金融市場研報與基金投資決策系統")
st.caption("整合實時新聞數據與阿里 DashScope (Qwen) LLM，提供每日總經市場掃描與單一資產交易決策研報。")

# ---------------------------------------------------------
# 2. 側邊欄：API Key 輸入與功能切換
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 系統設定與選單")
    
    # 支援動態輸入或從 Secrets 讀取
    user_api_key = st.text_input("DashScope API Key", value=api_key, type="password", help="可在阿里雲 DashScope 後台申請")
    
    if user_api_key:
        st.success("✅ API Key 已載入")
    else:
        st.error("❌ 請輸入 DASHSCOPE_API_KEY 以啟用服務")
    
    st.markdown("---")
    app_mode = st.radio(
        "請選擇功能模組：",
        ["📰 每日金融市場要聞彙整", "🎯 基金 / ETF 交易決策評估"]
    )
    
    st.markdown("---")
    st.markdown("### 📌 預設模型順序")
    st.markdown("1. `qwen-max` (主力深度分析)\n2. `qwen-plus` (備用)\n3. `qwen-turbo` (高速備用)")

# ---------------------------------------------------------
# 3. 通用 API 呼叫函數 (阿里 DashScope OpenAI 相容模式)
# ---------------------------------------------------------
def call_qwen_api(messages_list, current_api_key):
    if not current_api_key.strip():
        return None, "請先設定 DashScope API Key！"
        
    client = OpenAI(
        api_key=current_api_key.strip(),
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )
    models_to_try = ['qwen-max', 'qwen-plus', 'qwen-turbo']
    last_error = ""
    
    for model_name in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages_list,
                temperature=0.7
            )
            if response and response.choices:
                return response.choices[0].message.content, None
        except Exception as e:
            last_error = str(e)
            time.sleep(1.5) # 重試等待
            
    return None, f"模型呼叫失敗，最後錯誤訊息: {last_error}"

# ---------------------------------------------------------
# 模組一：每日金融市場要聞彙整
# ---------------------------------------------------------
if app_mode == "📰 每日金融市場要聞彙整":
    st.header("📰 全球每日總體經濟與金融市場要聞掃描")
    st.caption("自動抓取路透社中文網與 Yahoo 奇摩財經 RSS 實時數據，自動翻譯編譯為機構級每日簡報。")

    col_btn, col_date = st.columns([2, 3])
    with col_date:
        today_dt = datetime.datetime.now()
        st.info(f"📅 基準日期：{today_dt.strftime('%Y 年 %m 月 %d 日')}")
        
    with col_btn:
        fetch_news_btn = st.button("🚀 即時抓取最新新聞並生成日報", type="primary", use_container_width=True)

    if fetch_news_btn:
        if not user_api_key:
            st.error("❌ 請先設定 DashScope API Key！")
        else:
            with st.spinner("正在爬取路透社與 Yahoo 財經最新新聞..."):
                rss_urls = [
                    "https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com+hl:zh-TW&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
                    "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
                    "https://news.google.com/rss/search?q=聯準會+OR+美債殖利率+OR+美股三大指數&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                ]
                
                raw_news_items = []
                for url in rss_urls:
                    try:
                        feed = feedparser.parse(url)
                        for entry in feed.entries[:5]:
                            title = entry.get('title', '')
                            published = entry.get('published', '')
                            summary = entry.get('summary', '')[:120]
                            raw_news_items.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
                    except Exception as e:
                        st.warning(f"⚠️ RSS 讀取異常 ({url}): {e}")

            if not raw_news_items:
                st.error("❌ 未能成功抓取到金融新聞資料！")
            else:
                news_context = "\n".join(raw_news_items)
                
                prompt = f"""
你是一位機構級的高級總體經濟分析師與資深財經主編。
今天確切的日期是：{today_dt.strftime('%Y 年 %m 月 %d 日')}。

以下是今天從「路透社中文網」與「Yahoo 奇摩財經」擷取的最新即時新聞與市場資料：

=== 今日中文財經新聞原始資料 ===
{news_context}
================================

【任務要求 - 深度機構級金融研報】：
請根據上述原始新聞，編譯並整理為一份內容詳實、論述完整且富含數據的《每日金融市場要聞》。

【寫作指南】：
1. **內容充實度**：對每個新聞主題進行完整的段落寫作與分析，包含指數漲跌幅 %、美債殖利率 bp 變化、央行政策與資產價格衝擊。
2. **語系與金融術語**：請統一使用**標準繁體中文**及台灣金融市場用語（如：殖利率、聯準會、通膨、晶片、基點 bps）。
3. **嚴格防幻覺**：分析必須嚴格基於提供的新聞資料。

【報告章節結構】：
一、全球金融市場焦點與數據速覽
二、總體經濟、央行政策與債券市場
三、科技產業與企業財務動態
四、外匯、大宗商品與信用市場
"""
                with st.spinner("🤖 Qwen 正進行深度內容編譯與總經研報撰寫..."):
                    messages = [{"role": "user", "content": prompt}]
                    report_content, err = call_qwen_api(messages, user_api_key)
                    
                    if report_content:
                        st.session_state.daily_news_report = report_content
                        st.success("✅ 每日金融市場要聞生成完畢！")
                    else:
                        st.error(f"❌ 生成失敗：{err}")

    # 顯示當前生成的每日新聞研報
    if "daily_news_report" in st.session_state:
        st.markdown("---")
        st.subheader("📑 今日金融市場要聞摘要研報")
        st.markdown(st.session_state.daily_news_report)
        
        st.download_button(
            label="📥 下載今日研報 (Markdown 格式)",
            data=st.session_state.daily_news_report,
            file_name=f"Daily_Financial_Report_{today_dt.strftime('%Y%m%d')}.md",
            mime="text/markdown"
        )

# ---------------------------------------------------------
# 模組二：基金 / ETF 交易決策評估
# ---------------------------------------------------------
elif app_mode == "🎯 基金 / ETF 交易決策評估":
    st.header("🎯 基金 / ETF 投資決策與評估報告生成器")
    st.caption("輸入單一資產標的與買賣意向，系統將結合當前實時脈絡生成 900 字的三段式機構投資評估報告。")

    # Session State 初始化
    if "fund_report" not in st.session_state:
        st.session_state.fund_report = None
    if "fund_last_prompt_info" not in st.session_state:
        st.session_state.fund_last_prompt_info = {}

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        fund_name = st.text_input("基金 / ETF 名稱或代碼", placeholder="例如：IEF ETF、0050、元大美債20年")
    with col2:
        action_type = st.selectbox("擬執行交易方向", ["買進 / 建倉 (Buy)", "賣出 / 減碼 (Sell)", "觀望 / 持有 (Hold)"])
    with col3:
        lang_choice = st.selectbox("報告語言風格", ["繁體中文 (Traditional Chinese)", "英文 (English)", "中英雙語對照 (Bilingual)"])

    if st.button("🚀 生成個案投資決策報告", type="primary", use_container_width=True):
        if not user_api_key:
            st.error("❌ 請先設定 DashScope API Key！")
        elif not fund_name:
            st.warning("⚠️ 請先輸入基金或 ETF 名稱/代碼！")
        else:
            with st.spinner("正在爬取標的相關即時新聞資訊..."):
                encoded_query = urllib.parse.quote(fund_name)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}+OR+聯準會+OR+美債殖利率+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                feed = feedparser.parse(rss_url)
                
                news_list = []
                for entry in feed.entries[:5]:
                    title = entry.get('title', '')
                    published = entry.get('published', '')
                    summary = entry.get('summary', '')[:100]
                    news_list.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
                
                market_data = "\n".join(news_list) if news_list else "暫無具體即時新聞，將基於市場常規邏輯分析。"

            lang_instruction = "全篇報告請使用「標準繁體中文」。"
            if lang_choice == "英文 (English)":
                lang_instruction = "Please write the entire report in Professional English."
            elif lang_choice == "中英雙語對照 (Bilingual)":
                lang_instruction = "每個段落請先提供「繁體中文」，隨後附上對應的「英文翻譯 (English Translation)」。"

            prompt = f"""
你是一位機構級的首席投資策略官與資深資產配置分析師。

請針對使用者欲進行的交易規劃，結合最新的實時金融市場與總經數據，撰寫一份機構級的《基金投資分析與決策評估報告》。

【基本交易資訊】：
- 標的基金名稱/代碼：{fund_name}
- 擬執行的買賣方向：{action_type}
- 語言要求：{lang_instruction}

【最新實時市場數據與新聞脈絡】：
{market_data}

【報告撰寫嚴格規範】：
1. **文章總長度**：請控制在 900 字左右（約 850 - 950 字）。
2. **報告結構**（嚴格分為三大段，每段約 300 字）：
   - **第一段：當前總體經濟環境與市場脈絡分析**
     解析最新通膨（CPI/PCE）、聯準會與主要央行利率政策、美債殖利率曲線動向及市場整體風險偏好。
   - **第二段：基金標的屬性與最新衝擊評估**
     剖析該基金（{fund_name}）的主要持股/持債屬性，評估當前市場訊息對該資產類別產生的正面與負面衝擊。
   - **第三段：買賣方向（{action_type}）可行性評估與風控建議**
     針對使用者選擇的「{action_type}」方向進行客觀可行性評估，給出具體的投資進場/出場時機建議、評價點位考量及避險與停損/停利策略。
3. **專業度要求**：使用標準金融機構用語（如：殖利率、基點 bps、折溢價、久期 Duration、風險報酬比）。
"""
            with st.spinner("🤖 Qwen 分析師正在撰寫個案評估報告..."):
                messages = [{"role": "user", "content": prompt}]
                report, err = call_qwen_api(messages, user_api_key)
                
                if report:
                    st.session_state.fund_report = report
                    st.session_state.fund_last_prompt_info = {
                        "fund_name": fund_name,
                        "action_type": action_type,
                        "prompt": prompt
                    }
                    st.success("✅ 決策評估報告生成完畢！")
                else:
                    st.error(f"❌ 報告生成失敗：{err}")

    # 顯示報告與對話微調功能
    if st.session_state.fund_report:
        st.markdown("---")
        st.subheader(f"📈 《{st.session_state.fund_last_prompt_info.get('fund_name')}》- {st.session_state.fund_last_prompt_info.get('action_type')} 決策分析報告")
        st.markdown(st.session_state.fund_report)
        
        st.download_button(
            label="📥 下載個案報告 (TXT 格式)",
            data=st.session_state.fund_report,
            file_name=f"{st.session_state.fund_last_prompt_info.get('fund_name')}_{st.session_state.fund_last_prompt_info.get('action_type')}_Report.txt",
            mime="text/plain"
        )

        # 反饋與微調區塊
        st.markdown("---")
        st.subheader("🔄 報告優化與微調 (Feedback & Regenerate)")
        user_feedback = st.text_area(
            "輸入您的修改需求或補充意見：",
            placeholder="例如：請增加關於信用評級變化的討論，或是將停損策略調整得更保守一點..."
        )
        
        if st.button("✏️ 根據意見重新修正報告"):
            if not user_feedback.strip():
                st.warning("⚠️ 請先輸入修改意見！")
            else:
                with st.spinner("🤖 Qwen 正在根據您的意見調校與編譯報告..."):
                    refine_messages = [
                        {"role": "user", "content": st.session_state.fund_last_prompt_info.get("prompt")},
                        {"role": "assistant", "content": st.session_state.fund_report},
                        {"role": "user", "content": f"請根據以下意見修改上面的報告，並保持約 900 字的三段式機構研報結構：\n\n【修改意見】：{user_feedback}"}
                    ]
                    
                    updated_report, err = call_qwen_api(refine_messages, user_api_key)
                    if updated_report:
                        st.session_state.fund_report = updated_report
                        st.success("✅ 報告已更新！")
                        st.rerun()
                    else:
                        st.error(f"❌ 修正失敗：{err}")

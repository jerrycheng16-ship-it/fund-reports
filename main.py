import os
import glob
import time
import re
import datetime
from datetime import timezone, timedelta
import urllib.parse
import feedparser
import streamlit as st
from openai import OpenAI

# ---------------------------------------------------------
# 1. 頁面配置與 Secrets 安全讀取
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI 機構級金融研報與基金決策系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))

st.title("📈 AI 機構級金融市場研報與基金投資決策系統")
st.caption("自動彙整實時總經新聞、歷史每日研報，並支援一鍵生成月報與單一資產交易決策評估。")

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
        ["📰 每日要聞與總經月報", "🎯 基金 / ETF 交易決策評估"]
    )

# ---------------------------------------------------------
# 3. 工具函數 (Qwen API 呼叫與 HTML 標籤過濾)
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
                temperature=0.6 # 調低溫度以確保數據精準度與事實遵循
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

# ---------------------------------------------------------
# 模組一：每日金融市場要聞 & 歷史查詢 & 月報彙整
# ---------------------------------------------------------
if app_mode == "📰 每日要聞與總經月報":
    st.header("📰 全球金融市場要聞與總經月報系統")
    
    tab1, tab2, tab3 = st.tabs(["🚀 即時生成今日要聞", "📅 瀏覽歷史每日研報", "🗓️ 自動彙整總經月報"])
    
    tz_taiwan = timezone(timedelta(hours=8))
    today_dt = datetime.datetime.now(tz_taiwan)
    today_str = today_dt.strftime("%Y-%m-%d")

    # Tab 1: 手動或即時觸發今日要聞
    with tab1:
        st.subheader("📡 即時抓取最新焦點新聞並編譯日報")
        st.info(f"📅 基準日期（台灣時間）：{today_dt.strftime('%Y 年 %m 月 %d 日')}")
        
        if st.button("🚀 即時編譯今日研報 (數據強化版)", type="primary"):
            with st.spinner("正在專注抓取路透社 (Reuters) 與 Yahoo 財經最新新聞與市場數據..."):
                # 專注抓取路透社與 Yahoo 財經 RSS 來源
                rss_urls = [
                    "https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
                    "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
                    "https://news.google.com/rss/search?q=site:reuters.com+OR+site:finance.yahoo.com+Fed+OR+Yield+OR+CPI&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                ]
                
                raw_news = []
                for url in rss_urls:
                    try:
                        feed = feedparser.parse(url)
                        # 擴大抓取條數至 8 條，確保包含足夠數據點
                        for entry in feed.entries[:8]:
                            title = clean_html(entry.get('title', ''))
                            published = entry.get('published', '')
                            summary = clean_html(entry.get('summary', ''))[:180]
                            raw_news.append(f"【時間: {published}】\n標題: {title}\n內容摘要: {summary}\n")
                    except Exception as e:
                        st.warning(f"⚠️ RSS 讀取異常: {e}")

            if not raw_news:
                st.error("❌ 無法讀取新聞資料，請稍後再試。")
            else:
                # 強化數據與專注路透/Yahoo 的 Prompt
                prompt = f"""
你是一位機構級高級總體經濟分析師與資深財經主編。
今天確切的日期是：{today_dt.strftime('%Y 年 %m 月 %d 日')}。

以下是今日從「路透社 (Reuters)」與「Yahoo 財經 (Yahoo Finance)」擷取的最新即時新聞與數據：
=== 今日新聞原始資料 ===
{"".join(raw_news)}
========================

【任務要求 - 數據驅動機構研報】：
請根據上述原始資料，編譯一份內容嚴謹、富含「具體數據點」的《每日金融市場要聞》。

【寫作指南與數據強化標準】：
1. **必須包含具體數據與數字**：
   - 描述市場走勢時，**嚴禁僅使用「大幅下跌」、「小幅成長」、「創下新高」等模糊描述**。
   - 必須明確寫出具體數字，如：指數漲跌幅 **%**、美債殖利率點位與 **bp** 變化、匯率點位、油價/金價每盎司 **美元** 價格、通膨率 **%** 等。
2. **來源專注**：論述需完全基於路透社與 Yahoo 財經所提及的機構觀點與報導內容。
3. **語系與術語**：請統一使用**標準繁體中文**及台灣金融市場用語（如：殖利率、聯準會、通膨、基點 bps、折溢價）。

【報告章節結構】：
一、全球金融市場焦點與數據速覽（必須表列主要數據點變化）
二、總體經濟、央行政策與債券市場（分析美債殖利率 bps 與央行態度）
三、科技產業與企業財務動態（列出關鍵個股/ADR 個別漲跌幅 %）
四、外匯、大宗商品與信用市場（列出黃金、原油、美元指數具體報價與增減）
"""
                with st.spinner("🤖 Qwen 正進行數據提取與機構研報編譯..."):
                    report_content, err = call_qwen_api([{"role": "user", "content": prompt}])
                    if report_content:
                        st.session_state.today_report = report_content
                        # 備份寫入 daily_reports 資料夾
                        os.makedirs("daily_reports", exist_ok=True)
                        with open(f"daily_reports/{today_str}.md", "w", encoding="utf-8") as f:
                            f.write(report_content)
                        st.success("✅ 數據強化版研報生成完畢並已同步存檔！")
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
                        monthly_combined_text += f"\n\n=== {date_str} 數據紀錄 ===\n" + f.read()[:600]
                
                monthly_prompt = f"""
你是一位機構首席經濟學家。請針對 {target_month} 月份每日金融市場數據進行融會貫通，撰寫一份《{target_month} 全球金融市場總經趨勢月報》。

=== 全月資料紀錄 ===
{monthly_combined_text}
===================

【任務要求】：
請多提及全月關鍵數據（如高低點位、累積漲跌幅 %、殖利率區間 bps），避免抽象描述。

【月報架構】：
一、全月總經核心主軸與央行政策轉折
二、全球權益市場月度回顧與表現（含具體漲跌幅數據）
三、債券市場與殖利率曲線動向（含具體 bps 變動）
四、外匯與大宗商品（黃金/原油）走勢與報價
五、下月展望與資產配置建議
"""
                with st.spinner("🤖 Qwen 正進行跨日數據彙整與月報撰寫..."):
                    monthly_report, err = call_qwen_api([{"role": "user", "content": monthly_prompt}])
                    if monthly_report:
                        st.session_state[f"monthly_{target_month}"] = monthly_report
                        st.success("✅ 月報彙整成功！")
                    else:
                        st.error(f"❌ 月報生成失敗: {err}")

            if f"monthly_{target_month}" in st.session_state:
                st.markdown("---")
                st.markdown(st.session_state[f"monthly_{target_month}"])
                st.download_button(
                    "📥 下載總經月報 (.md)",
                    st.session_state[f"monthly_{target_month}"],
                    file_name=f"Monthly_Report_{target_month}.md"
                )

# ---------------------------------------------------------
# 模組二：基金 / ETF 交易決策評估 (支援二次對話微調)
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
            with st.spinner(f"正在爬取 {fund_name} 相關實時新聞與路透/Yahoo數據..."):
                encoded_query = urllib.parse.quote(fund_name)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}+OR+聯準會+OR+美債殖利率+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                feed = feedparser.parse(rss_url)
                
                news_list = []
                for entry in feed.entries[:6]:
                    title = clean_html(entry.get('title', ''))
                    published = entry.get('published', '')
                    summary = clean_html(entry.get('summary', ''))[:120]
                    news_list.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
                
                market_data = "\n".join(news_list) if news_list else "暫無具體即時新聞，將基於資產常規屬性分析。"

            lang_instruction = "全篇報告請使用「標準繁體中文」。"
            if lang_choice == "英文 (English)":
                lang_instruction = "Please write the entire report in Professional English."
            elif lang_choice == "中英雙語對照 (Bilingual)":
                lang_instruction = "每個段落請先提供「繁體中文」，隨後附上對應的「英文翻譯 (English Translation)」。"

            prompt = f"""
你是一位機構級首席投資策略官。請針對交易規劃與實時市場脈絡，撰寫一份約 900 字的三段式《基金投資分析與決策評估報告》。

【基本交易資訊】：
- 標的名稱/代碼：{fund_name}
- 擬執行交易方向：{action_type}
- 語言要求：{lang_instruction}

【即時市場數據與新聞】：
{market_data}

【撰寫要求】：請盡可能包含具體數據點（如價格、評價點位、殖利率 bps、目標價範圍），避免過度簡略。

【報告結構】（分為三大段，每段約 300 字）：
第一段：當前總體經濟環境與市場脈絡分析
第二段：標的屬性與最新衝擊評估 ({fund_name})
第三段：買賣方向 ({action_type}) 可行性評估與風控/停損策略
"""
            with st.spinner("🤖 Qwen 分析師正在撰寫評估報告..."):
                report, err = call_qwen_api([{"role": "user", "content": prompt}])
                if report:
                    st.session_state.fund_report = report
                    st.session_state.fund_prompt_info = {
                        "fund_name": fund_name,
                        "action_type": action_type,
                        "prompt": prompt
                    }
                    st.success("✅ 決策報告生成完畢！")
                else:
                    st.error(f"❌ 生成失敗: {err}")

    # 顯示個案報告與微調區塊
    if st.session_state.fund_report:
        st.markdown("---")
        st.subheader(f"📈 《{st.session_state.fund_prompt_info.get('fund_name')}》- {st.session_state.fund_prompt_info.get('action_type')} 決策評估報告")
        st.markdown(st.session_state.fund_report)
        
        st.download_button(
            "📥 下載此個案報告 (.txt)",
            st.session_state.fund_report,
            file_name=f"{st.session_state.fund_prompt_info.get('fund_name')}_{st.session_state.fund_prompt_info.get('action_type')}_Report.txt"
        )

        st.markdown("---")
        st.subheader("🔄 報告優化與對話式微調")
        user_feedback = st.text_area("輸入對報告的修改需求或補充意見：", placeholder="例如：請增加關於具體進場價格與停損點位的討論...")
        
        if st.button("✏️ 根據意見重新修正報告"):
            if not user_feedback.strip():
                st.warning("⚠️ 請輸入修改意見！")
            else:
                with st.spinner("🤖 Qwen 正在編譯修改報告..."):
                    refine_messages = [
                        {"role": "user", "content": st.session_state.fund_prompt_info.get("prompt")},
                        {"role": "assistant", "content": st.session_state.fund_report},
                        {"role": "user", "content": f"請根據以下意見修改上面的報告，並保持約 900 字的三段式結構與具體數據點：\n\n【修改意見】：{user_feedback}"}
                    ]
                    updated_report, err = call_qwen_api(refine_messages)
                    if updated_report:
                        st.session_state.fund_report = updated_report
                        st.success("✅ 報告已修正！")
                        st.rerun()
                    else:
                        st.error(f"❌ 修正失敗: {err}")

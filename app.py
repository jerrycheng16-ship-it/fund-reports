import os
import time
import urllib.parse
import feedparser
import streamlit as st
from google import genai
from google.genai import types

# 1. 頁面基本設定
st.set_page_config(
    page_title="AI 基金投資決策與分析報告生成器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 AI 基金投資決策與即時分析報告生成器")
st.caption("根據最新實時總經數據、金融市場訊息與買賣方向，自動編譯機構級投資分析報告。")

# 側邊欄：API Key 設定
with st.sidebar:
    st.header("⚙️ 系統設定")
    api_key_input = st.text_input("輸入 Gemini API Key", type="password", help="可以從 GitHub Secrets 或是在此輸入")
    api_key = api_key_input if api_key_input else os.environ.get("GEMINI_API_KEY", "")
    
    st.markdown("---")
    st.markdown("### 📌 報告規格")
    st.markdown("- **總字數**：約 900 字")
    st.markdown("- **架構**：三大核心章節")
    st.markdown("- **語系**：中英雙語/單語可選")

# 主介面輸入表單
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    fund_name = st.text_input("輸入基金名稱或代碼", placeholder="例如：安聯收益成長基金、0050、美國科技股 ETF")

with col2:
    action_type = st.selectbox("買賣方向", ["買進 / 建倉 (Buy)", "賣出 / 減碼 (Sell)", "觀望 / 持有 (Hold)"])

with col3:
    lang_choice = st.selectbox("報告語言", ["繁體中文 (Traditional Chinese)", "英文 (English)", "中英雙語對照 (Bilingual)"])

# 2. RSS 即時財經資料抓取函數
def fetch_realtime_context(query):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}+OR+聯準會+OR+美債殖利率+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    
    news_list = []
    for entry in feed.entries[:8]:
        title = entry.get('title', '')
        published = entry.get('published', '')
        summary = entry.get('summary', '')[:120]
        news_list.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
    return "\n".join(news_list)

# 3. 生成報告按鈕邏輯
if st.button("🚀 生成分析報告", type="primary", use_container_width=True):
    if not api_key:
        st.error("❌ 請先提供 Gemini API Key！")
    elif not fund_name:
        st.warning("⚠️ 請輸入基金名稱或代碼！")
    else:
        with st.spinner("正在爬取全球實時金融數據與市場新聞..."):
            market_data = fetch_realtime_context(fund_name)
        
        st.success("✅ 已取得最新市場訊息！正在進行總經歸因與策略推理...")
        
        # 建立 Gemini Client
        client = genai.Client(api_key=api_key.strip())
        
        # 語言指示
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

【報告撰写嚴格規範】：
1. **文章總長度**：請控制在 900 字左右（約 850 - 950 字）。
2. **報告結構**（必須明確分為三大段，每段約 300 字）：
   - **第一段：當前總體經濟環境與市場脈絡分析**
     解析最新通膨（CPI/PCE）、聯準會與主要央行利率政策、美債殖利率曲線動向及市場整體風險偏好（Risk-on / Risk-off）。
   - **第二段：基金標的屬性與最新衝擊評估**
     剖析該基金（{fund_name}）的主要持股/持債屬性，評估當前市場訊息對該資產類別產生的正面與負面衝擊。
   - **第三段：買賣方向（{action_type}）可行性評估與風控建議**
     針對使用者選擇的「{action_type}」方向進行客觀可行性評估，給出具體的投資進場/出場時機建議、評價點位考量及避險與停損/停利策略。
3. **專業度要求**：使用標準金融機構用語（如：殖利率、基點 bps、折溢價、流動性溢價、久期 Duration、風險報酬比）。
"""

        report_place = st.empty()
        
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )
            )
            report_text = response.text
            
            # 呈現報告
            st.markdown("---")
            st.subheader(f"📈 《{fund_name}》- {action_type} 決策分析報告")
            st.markdown(report_text)
            
            # 提供下載功能
            st.download_button(
                label="📥 下載投資報告 (TXT)",
                data=report_text,
                file_name=f"{fund_name}_{action_type}_Report.txt",
                mime="text/plain"
            )
            
        except Exception as e:
            st.error(f"❌ 報告生成失敗：{e}")

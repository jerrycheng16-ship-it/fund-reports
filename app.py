import os
import time
import urllib.parse
import feedparser
import streamlit as st
from openai import OpenAI

# 從 Streamlit Secrets 或環境變數讀取 DashScope (Qwen) API Key
api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))

st.set_page_config(
    page_title="AI 基金投資決策與分析報告生成器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 AI 基金投資決策與即時分析報告生成器")
st.caption("根據最新實時總經數據、金融市場訊息與買賣方向，自動編譯機構級投資分析報告。")

# 初始化 Session State（用來儲存生成好的報告與歷史資料）
if "current_report" not in st.session_state:
    st.session_state.current_report = None
if "last_prompt_info" not in st.session_state:
    st.session_state.last_prompt_info = {}

with st.sidebar:
    st.header("⚙️ 系統設定")
    if api_key:
        st.success("✅ 已自動載入 DashScope API Key")
    else:
        st.error("❌ 未偵測到 API Key，請至 Streamlit Secrets 設定 DASHSCOPE_API_KEY")
    
    st.markdown("---")
    st.markdown("### 📌 報告規格")
    st.markdown("- **總字數**：約 900 字")
    st.markdown("- **架構**：三大核心章節")
    st.markdown("- **語系**：中英雙語/單語可選")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    fund_name = st.text_input("輸入基金名稱或代碼", placeholder="例如：IEF ETF、0050、安聯收益成長基金")

with col2:
    action_type = st.selectbox("買賣方向", ["買進 / 建倉 (Buy)", "賣出 / 減碼 (Sell)", "觀望 / 持有 (Hold)"])

with col3:
    lang_choice = st.selectbox("報告語言", ["繁體中文 (Traditional Chinese)", "英文 (English)", "中英雙語對照 (Bilingual)"])

def fetch_realtime_context(query):
    try:
        encoded_query = urllib.parse.quote(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}+OR+聯準會+OR+美債殖利率+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        
        news_list = []
        for entry in feed.entries[:5]:
            title = entry.get('title', '')
            published = entry.get('published', '')
            summary = entry.get('summary', '')[:100]
            news_list.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
        return "\n".join(news_list)
    except Exception as e:
        return "無法取得即時新聞資料，將依據一般市場知識生成分析。"

# 核心 API 呼叫函數
def generate_qwen_response(messages_list):
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
                temperature=0.7
            )
            if response and response.choices:
                return response.choices[0].message.content, None
        except Exception as e:
            last_error = str(e)
            time.sleep(2)
    return None, last_error

# 1. 首次生成報告按鈕
if st.button("🚀 生成初始分析報告", type="primary", use_container_width=True):
    if not api_key:
        st.error("❌ 請先在 Streamlit Secrets 中設定 DASHSCOPE_API_KEY！")
    elif not fund_name:
        st.warning("⚠️ 請輸入基金名稱或代碼！")
    else:
        with st.spinner("正在爬取實時金融數據並撰寫研報..."):
            market_data = fetch_realtime_context(fund_name)
            
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
     解析最新通膨（CPI/PCE）、聯準會與主要央行利率政策、美債殖利率曲線動向及市場整體風險偏好（Risk-on / Risk-off）。
   - **第二段：基金標的屬性與最新衝擊評估**
     剖析該基金（{fund_name}）的主要持股/持債屬性，評估當前市場訊息對該資產類別產生的正面與負面衝擊。
   - **第三段：買賣方向（{action_type}）可行性評估與風控建議**
     針對使用者選擇的「{action_type}」方向進行客觀可行性評估，給出具體的投資進場/出場時機建議、評價點位考量及避險與停損/停利策略。
3. **專業度要求**：使用標準金融機構用語（如：殖利率、基點 bps、折溢價、流動性溢價、久期 Duration、風險報酬比）。
"""
            messages = [{"role": "user", "content": prompt}]
            report, err = generate_qwen_response(messages)
            
            if report:
                st.session_state.current_report = report
                st.session_state.last_prompt_info = {
                    "fund_name": fund_name,
                    "action_type": action_type,
                    "prompt": prompt
                }
            else:
                st.error(f"❌ 報告生成失敗：{err}")

# 2. 顯示現有報告與二次微調區塊
if st.session_state.current_report:
    st.markdown("---")
    st.subheader(f"📈 《{st.session_state.last_prompt_info.get('fund_name')}》- {st.session_state.last_prompt_info.get('action_type')} 決策分析報告")
    st.markdown(st.session_state.current_report)
    
    st.download_button(
        label="📥 下載當前投資報告 (TXT)",
        data=st.session_state.current_report,
        file_name=f"{st.session_state.last_prompt_info.get('fund_name')}_{st.session_state.last_prompt_info.get('action_type')}_Report.txt",
        mime="text/plain"
    )

    # -------------------------------------------------------------
    # 💡 關鍵功能：針對回應進行調整並重新生成
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("🔄 報告優化與微調 (Feedback & Regenerate)")
    st.caption("您可以輸入對這份報告的修改建議，AI 將根據您的意見重新編譯報告。")
    
    user_feedback = st.text_area(
        "輸入您的修改需求或補充意見：",
        placeholder="例如：請增加關於信評變化的討論、將第三段的停損策略調整得更保守一點、或補充說明殖利率倒掛對久期的影響..."
    )
    
    if st.button("✏️ 根據意見重新修正報告", type="secondary"):
        if not user_feedback.strip():
            st.warning("⚠️ 請先輸入修改意見！")
        else:
            with st.spinner("🤖 AI 正在根據您的意見重新調校與編譯報告..."):
                # 將「歷史報告」與「使用者修改意見」包裝進 Prompt 重新傳給 AI
                refine_messages = [
                    {"role": "user", "content": st.session_state.last_prompt_info.get("prompt")},
                    {"role": "assistant", "content": st.session_state.current_report},
                    {"role": "user", "content": f"請根據以下意見修改上面的報告，並保持整體約 900 字的三段式機構研報結構：\n\n【修改意見】：{user_feedback}"}
                ]
                
                updated_report, err = generate_qwen_response(refine_messages)
                if updated_report:
                    st.session_state.current_report = updated_report
                    st.success("✅ 報告已更新！")
                    st.rerun() # 重新整理頁面顯示最新報告
                else:
                    st.error(f"❌ 修正失敗：{err}")

import os
import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="基金分析測試",
    page_icon="📊"
)

st.title("📊 Qwen API 測試")

try:
    api_key = st.secrets["DASHSCOPE_API_KEY"]
except Exception:
    api_key = os.getenv("DASHSCOPE_API_KEY", "")

if not api_key:
    st.error("找不到 DASHSCOPE_API_KEY")
    st.stop()

st.success("✅ API Key 已載入")

fund_name = st.text_input(
    "基金名稱",
    value="SPY"
)

if st.button("測試 Qwen"):

    try:

        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )

        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {
                    "role": "user",
                    "content": f"請用繁體中文介紹 {fund_name} ETF"
                }
            ]
        )

        st.write(response.choices[0].message.content)

    except Exception as e:

        st.exception(e)

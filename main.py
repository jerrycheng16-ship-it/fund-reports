import streamlit as st

st.set_page_config(page_title="系統測試頁面", page_icon="🧪", layout="wide")

st.title("🧪 Streamlit 部署測試成功！")
st.success("如果您看到這個畫面，代表 Python 環境、Streamlit 伺服器與入口檔設定完全正常。")

# 測試基礎元件
st.write("---")
st.subheader("⚙️ 基礎元件渲染測試")
user_input = st.text_input("請輸入測試文字：", placeholder="輸入任意內容...")
if user_input:
    st.write(f"您輸入的內容是：**{user_input}**")

st.button("點擊測試按鈕")

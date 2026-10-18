import base64
import datetime
from datetime import timezone, timedelta
import glob
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from openai import OpenAI
import pandas as pd
import feedparser
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------
# 1. 頁面配置與 Secrets 安全讀取
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI 機構級金融研報與總經決策系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 讀取 API Keys
dashscope_key = st.secrets.get(
    "DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "")
)
fred_api_key = st.secrets.get(
    "FRED_API_KEY", os.environ.get("FRED_API_KEY", "")
)
github_token = st.secrets.get(
    "GITHUB_TOKEN", os.environ.get("GITHUB_TOKEN", "")
)
github_repo = st.secrets.get(
    "GITHUB_REPO",
    os.environ.get("GITHUB_REPO", "your-username/ai-financial-macro-system"),
)

st.title("📈 AI 機構級金融市場研報與總經決策系統")
st.caption(
    "自動彙整實時總經新聞、Yahoo / FRED 雙資料源動態連動圖表、每日研報/月報，以及資產交易決策評估（支援 GitHub 自動備份）。"
)

# ---------------------------------------------------------
# 2. 側邊欄選單
# ---------------------------------------------------------
with st.sidebar:
  st.header("⚙️ 功能選單")

  if dashscope_key:
    st.success("🔒 DashScope API Key 已載入")
  else:
    st.error("❌ 未讀取到 DASHSCOPE_API_KEY")

  if fred_api_key:
    st.success("🔒 FRED API Key 已載入")
  else:
    st.warning("⚠️ 未讀取到 FRED_API_KEY")

  if github_token:
    st.success("🔒 GitHub Token 已載入 (研報自動備份)")
  else:
    st.warning("⚠️ 未設定 GITHUB_TOKEN (研報將僅存本地)")

  st.markdown("---")
  app_mode = st.radio(
      "請選擇功能模組：",
      [
          "📰 每日要聞與總經月報",
          "📊 全球總體經濟數據 (Yahoo & FRED)",
          "🎯 基金 / ETF 交易決策評估",
      ],
  )


# ---------------------------------------------------------
# 3. 工具函數 (Qwen API, GitHub Sync & 完整歷史檔案遞迴同步)
# ---------------------------------------------------------
def call_qwen_api(messages_list):
  if not dashscope_key:
    return None, "請先於 Streamlit Secrets 設定 DASHSCOPE_API_KEY！"

  client = OpenAI(
      api_key=dashscope_key.strip(),
      base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
  )
  models_to_try = ["qwen-max", "qwen-plus", "qwen-turbo"]
  last_error = ""

  for model_name in models_to_try:
    try:
      response = client.chat.completions.create(
          model=model_name, messages=messages_list, temperature=0.1
      )
      if response and response.choices:
        return response.choices[0].message.content, None
    except Exception as e:
      last_error = str(e)
      time.sleep(1.5)

  return None, f"模型呼叫失敗，錯誤原因: {last_error}"


def save_report_to_github(file_path, content, commit_message):
  """將生成的研報自動上傳/更新至 GitHub 倉庫"""
  if not github_token or not github_repo:
    return False, "未設定 GITHUB_TOKEN 或 GITHUB_REPO"

  url = f"https://api.github.com/repos/{github_repo}/contents/{file_path}"
  headers = {
      "Authorization": f"Bearer {github_token}",
      "Accept": "application/vnd.github+json",
  }

  response = requests.get(url, headers=headers)
  sha = None
  if response.status_code == 200:
    sha = response.json().get("sha")

  encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

  payload = {"message": commit_message, "content": encoded_content, "branch": "main"}
  if sha:
    payload["sha"] = sha

  put_res = requests.put(url, headers=headers, json=payload)
  if put_res.status_code in [201, 200]:
    return True, "成功同步至 GitHub！"
  else:
    return False, put_res.json().get("message", "未知錯誤")


def get_available_reports():
  """透過 GitHub Git Trees API 遞迴抓取 daily_reports 底下的所有歷史研報檔案"""
  os.makedirs("daily_reports", exist_ok=True)

  if github_token and github_repo:
    try:
      branch_url = f"https://api.github.com/repos/{github_repo}/branches/main"
      headers = {
          "Authorization": f"Bearer {github_token}",
          "Accept": "application/vnd.github+json",
      }
      res = requests.get(branch_url, headers=headers)
      if res.status_code == 200:
        tree_sha = (
            res.json().get("commit", {}).get("commit", {}).get("tree", {}).get("sha")
        )
        if tree_sha:
          tree_url = f"https://api.github.com/repos/{github_repo}/git/trees/{tree_sha}?recursive=1"
          tree_res = requests.get(tree_url, headers=headers)
          if tree_res.status_code == 200:
            for item in tree_res.json().get("tree", []):
              path = item.get("path", "")
              if path.startswith("daily_reports/") and path.endswith(".md"):
                file_path = os.path.join(
                    "daily_reports", os.path.basename(path)
                )
                if not os.path.exists(file_path):
                  raw_url = f"https://raw.githubusercontent.com/{github_repo}/main/{path}"
                  file_res = requests.get(raw_url)
                  if file_res.status_code == 200:
                    with open(file_path, "w", encoding="utf-8") as f:
                      f.write(file_res.text)
    except Exception:
      pass

  return sorted(glob.glob("daily_reports/*.md"), reverse=True)


def clean_html(raw_html):
  cleanr = re.compile("<.*?>")
  return re.sub(cleanr, "", raw_html)


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
    "台灣加權指數": "^TWII",
}


def search_symbol_by_llm(keyword):
  prompt = f"""
你是一個精通全球金融市場（Yahoo Finance 與 FRED 數據庫）的總經專家。
使用者輸入的自然語言關鍵字為："{keyword}"

請提供 3 個最精準的資料代碼。嚴格以 JSON 陣列格式輸出：
[
  {{"code": "GDPC1", "name": "US Real GDP", "source": "FRED"}},
  {{"code": "^TNX", "name": "US 10-Year Treasury Yield", "source": "Yahoo"}},
  {{"code": "PCEPILFE", "name": "US Core PCE Index", "source": "FRED"}}
]
"""
  res, err = call_qwen_api([{"role": "user", "content": prompt}])
  if res:
    try:
      match = re.search(r"\[.*\]", res, re.DOTALL)
      if match:
        return json.loads(match.group(0))
    except Exception:
      return []
  return []


@st.cache_data(ttl=3600)
def fetch_smart_data(symbol):
  raw_code = (
      str(symbol).strip().replace("$", "").replace('"', "").replace("'", "")
  )
  fred_mapping = {
      "GDP": "GDPC1",
      "CPI": "CPIAUCSL",
      "PCE": "PCEPILFE",
      "UNRATE": "UNRATE",
  }
  clean_code = fred_mapping.get(raw_code.upper(), raw_code)

  if fred_api_key and not clean_code.startswith("^") and len(clean_code) <= 10:
    fred_url = f"https://api.stlouisfed.org/fred/series/observations?series_id={clean_code}&api_key={fred_api_key}&file_type=json"
    try:
      req = urllib.request.Request(
          fred_url, headers={"User-Agent": "Mozilla/5.0"}
      )
      with urllib.request.urlopen(req, timeout=8) as response:
        data = json.loads(response.read().decode("utf-8"))
      observations = data.get("observations", [])
      if observations:
        dates = [obs["date"] for obs in observations if obs["value"] != "."]
        values = [
            float(obs["value"]) for obs in observations if obs["value"] != "."
        ]
        df = pd.DataFrame({"Date": pd.to_datetime(dates), symbol: values})
        df = df.dropna().sort_values("Date")
        if len(df) > 2:
          return df
    except Exception:
      pass

  fred_csv_url = (
      f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={clean_code.replace('^', '')}"
  )
  try:
    req = urllib.request.Request(
        fred_csv_url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=8) as response:
      df = pd.read_csv(io.BytesIO(response.read()))
    if not df.empty and "DATE" in df.columns:
      df["Date"] = pd.to_datetime(df["DATE"], errors="coerce")
      val_col = [c for c in df.columns if c != "DATE"][0]
      df[symbol] = pd.to_numeric(df[val_col], errors="coerce")
      df = df[["Date", symbol]].dropna().sort_values("Date")
      if len(df) > 2:
        return df
  except Exception:

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
from bs4 import BeautifulSoup
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
    "自動聯網抓取實時總經新聞重點、Yahoo / FRED 雙資料源動態連動圖表、每日研報/月報，以及資產交易決策評估（支援 GitHub 自動備份）。"
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
# 3. 工具函數 (Qwen API, 網頁內文自動抓取, GitHub Sync)
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


def fetch_article_text(url):
  try:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
      html = resp.read().decode("utf-8", errors="ignore")
      soup = BeautifulSoup(html, "html.parser")
      for script in soup(["script", "style", "nav", "footer", "header"]):
        script.extract()
      paragraphs = soup.find_all("p")
      text = " ".join([p.get_text() for p in paragraphs])
      return text[:3000]
  except Exception:
    return ""


def save_report_to_github(file_path, content, commit_message):
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
    pass

  try:
    ticker = yf.Ticker(clean_code)
    df = ticker.history(period="max", auto_adjust=True)
    if not df.empty and len(df) > 2:
      df = df.reset_index()
      val_col = "Close" if "Close" in df.columns else df.columns[1]
      df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
      df[symbol] = pd.to_numeric(df[val_col], errors="coerce")
      df = df[["Date", symbol]].dropna().sort_values("Date")
      return df
  except Exception:
    pass

  return pd.DataFrame()


# ---------------------------------------------------------
# 模組一：每日金融市場要聞 & 歷史查詢 & 月報彙整
# ---------------------------------------------------------
if app_mode == "📰 每日要聞與總經月報":
  st.header("📰 全球金融市場要聞與總經月報系統")

  tab1, tab2, tab3 = st.tabs(
      ["🚀 即時生成今日要聞", "📅 瀏覽歷史每日研報", "🗓️ 自動彙整總經月報"]
  )

  tz_taiwan = timezone(timedelta(hours=8))
  today_dt = datetime.datetime.now(tz_taiwan)
  today_str = today_dt.strftime("%Y-%m-%d")

  with tab1:
    st.subheader("📡 即時擷取財經新聞重點摘要 (含完整標題與具體指標)")
    st.info(f"📅 基準日期（台灣時間）：{today_dt.strftime('%Y 年 %m 月 %d 日')}")

    if st.button("🚀 即時產出今日新聞摘要", type="primary"):
      with st.spinner("正在聯網擷取財經新聞內容與數據..."):
        rss_urls = [
            "https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com+美股+OR+聯準會+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
            "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+美股+OR+台股+OR+債市+OR+通膨&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        ]

        raw_news = []
        for url in rss_urls:
          try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
              title = clean_html(entry.get("title", ""))
              published = entry.get("published", "")
              link = entry.get("link", "")
              article_body = fetch_article_text(link)
              if not article_body:
                article_body = clean_html(entry.get("summary", ""))

              raw_news.append(
                  f"【標題】: {title}\n【時間】: {published}\n【內容】: {article_body}\n---\n"
              )
          except Exception as e:
            st.warning(f"⚠️ 抓取異常: {e}")

        if not raw_news:
          st.error("❌ 無法讀取新聞資料，請稍後再試。")
        else:
          prompt = f"""
今天是 {today_dt.strftime('%Y 年 %m 月 %d 日')}。

以下是今日從各大財經媒體擷取的即時新聞資料：
=== 新聞資料 ===
{"".join(raw_news)}
================

【嚴格格式與內容指令】：
1. 請從上述資料中挑選出最重要、最具代表性的 **3 則核心市場訊息**。
2. **必須完整保留新聞標題**：每一則訊息開頭必須明確列出原新聞的完整標題與發布時間。
3. **必須明確點出具體指標、指數或機構名稱**：若原文提及特定技術指標、經濟數據、總經指數或機構（例如 S&P 500、納斯達克、CPI、非農就業等），**必須具體寫出其名稱**，絕對禁止使用模糊代稱（如「某指標」）。
4. **絕對禁止前後重複或分段冗述**：每一則新聞只需提供一個連續、流暢的摘要段落。
5. **絕對禁止自己發揮、揣測或添加任何投資建議**。
6. **字數要求**：扣除標題後，每一則新聞的摘要內容長度必須控制在 **500 字左右**，純粹客觀地還原新聞內的原始事實與數據。
7. 全程使用**繁體中文**輸出。
"""
          with st.spinner("🤖 正在整理附帶標題與具體指標的 500 字摘要..."):
            report_content, err = call_qwen_api(
                [{"role": "user", "content": prompt}]
            )
            if report_content:
              st.session_state.today_report = report_content

              os.makedirs("daily_reports", exist_ok=True)
              file_rel_path = f"daily_reports/{today_str}.md"
              with open(file_rel_path, "w", encoding="utf-8") as f:
                f.write(report_content)

              success, msg = save_report_to_github(
                  file_rel_path,
                  report_content,
                  f"Add 500-word concise news summary with titles for {today_str}",
              )
              if success:
                st.success("✅ 新聞摘要生成完畢，且已自動同步至 GitHub！")
                time.sleep(1)
                st.rerun()
              else:
                st.warning(f"⚠️ 本地儲存成功，但 GitHub 同步失敗: {msg}")
            else:
              st.error(f"❌ 生成失敗: {err}")

    if "today_report" in st.session_state:
      st.markdown("---")
      st.markdown(st.session_state.today_report)

  with tab2:
    st.subheader("📅 歷史每日研報查詢")
    report_files = get_available_reports()
    if not report_files:
      st.info("💡 目前資料夾中尚無歷史研報檔。")
    else:
      selected_file = st.selectbox(
          "選擇欲檢視的日期：",
          report_files,
          format_func=lambda x: os.path.basename(x).replace(".md", ""),
      )
      if selected_file:
        with open(selected_file, "r", encoding="utf-8") as f:
          content = f.read()
        st.markdown("---")
        st.markdown(content)
        st.download_button(
            "📥 下載此研報 (.md)",
            content,
            file_name=os.path.basename(selected_file),
        )

  with tab3:
    st.subheader("🗓 月度總經趨勢彙整系統")
    all_files = get_available_reports()
    available_months = sorted(
        list(set([os.path.basename(f)[:7] for f in all_files])), reverse=True
    )
    if not available_months:
      st.warning("⚠️ 尚無每日研報數據。")
    else:
      target_month = st.selectbox("選擇欲彙整的月份：", available_months)
      if st.button("🚀 生成月度新聞彙整", type="primary"):
        month_files = sorted(glob.glob(f"daily_reports/{target_month}-*.md"))
        monthly_combined_text = ""
        for filepath in month_files:
          date_str = os.path.basename(filepath).replace(".md", "")
          with open(filepath, "r", encoding="utf-8") as f:
            monthly_combined_text += (
                f"\n\n=== {date_str} 原始紀錄 ===\n" + f.read()[:2000]
            )

        monthly_prompt = f"""
請針對 {target_month} 月份每日新聞紀錄進行彙整，總字數控制在 500 字左右，忠實呈現原始新聞重點與數據，絕對禁止自行發揮與主觀判斷。全程使用繁體中文。
=== 全月資料紀錄 ===
{monthly_combined_text}
===================
"""
        with st.spinner("🤖 正進行月度新聞彙整..."):
          monthly_report, err = call_qwen_api(
              [{"role": "user", "content": monthly_prompt}]
          )
          if monthly_report:
            st.session_state[f"monthly_{target_month}"] = monthly_report
            st.success("✅ 月報彙整成功！")
          else:
            st.error(f"❌ 生成失敗: {err}")

      if f"monthly_{target_month}" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state[f"monthly_{target_month}"])
        st.download_button(
            "📥 下載月度彙整 (.md)",
            st.session_state[f"monthly_{target_month}"],
            file_name=f"Monthly_Report_{target_month}.md",
        )

# ---------------------------------------------------------
# 模組二：全球總體經濟數據 (Yahoo & FRED)
# ---------------------------------------------------------
elif app_mode == "📊 全球總體經濟數據 (Yahoo & FRED)":
  st.header("📊 全球總體經濟與市場數據庫 (Yahoo & FRED 智慧雙資料源)")

  if "custom_indicators" not in st.session_state:
    st.session_state.custom_indicators = DEFAULT_INDICATORS.copy()
  if "selected_indicators_list" not in st.session_state:
    st.session_state.selected_indicators_list = [
        "美國 10 年期公債殖利率 (%)",
        "S&P 500 指數",
    ]
  if "indicator_transforms" not in st.session_state:
    st.session_state.indicator_transforms = {}

  with st.expander("🔍 智慧搜尋數據代碼 / 新增自訂指標", expanded=True):
    col_sch1, col_sch2 = st.columns([3, 1])
    with col_sch1:
      search_query = st.text_input("輸入想尋找的數據名稱（中英文皆可）：")
    with col_sch2:
      st.write(" ")
      st.write(" ")
      do_search = st.button("🔎 搜尋數據代碼", type="primary")

    if do_search and search_query:
      with st.spinner(f"正在搜尋與 '{search_query}' 最匹配的代碼..."):
        search_results = search_symbol_by_llm(search_query)
        if search_results:
          st.session_state.search_results = search_results

    if "search_results" in st.session_state and st.session_state.search_results:
      res_options = {
          f"{item['name']} (Code: {item['code']} - Source: {item.get('source', 'Auto')})": item
          for item in st.session_state.search_results
      }
      selected_match_label = st.selectbox(
          "選擇欲加入的數據指標：", list(res_options.keys())
      )
      selected_item = res_options[selected_match_label]

      col_add1, col_add2 = st.columns([3, 1])
      with col_add1:
        final_name = st.text_input(
            "圖表顯示名稱：", value=selected_item["name"]
        )
      with col_add2:
        st.write(" ")
        st.write(" ")
        if st.button("➕ 加入指標對比"):
          st.session_state.custom_indicators[final_name] = selected_item["code"]
          if (
              final_name
              not in st.session_state.selected_indicators_list
          ):
            st.session_state.selected_indicators_list.append(final_name)
          st.success(f"✅ 成功將【{final_name}】加入圖表對比！")
          st.rerun()

  st.markdown("---")
  valid_options = list(st.session_state.custom_indicators.keys())
  st.session_state.selected_indicators_list = [
      k
      for k in st.session_state.selected_indicators_list
      if k in valid_options
  ]

  selected_indicators = st.multiselect(
      "選擇欲比較的市場/總經指標：",
      valid_options,
      default=st.session_state.selected_indicators_list,
  )
  st.session_state.selected_indicators_list = selected_indicators

  transform_options = ["原始水準 (Level/Raw)", "年增率 (YoY %)", "月/日增額 (Diff)"]
  if selected_indicators:
    st.markdown("##### ⚙️ 針對個別指標設定資料處理方式：")
    transform_cols = st.columns(min(len(selected_indicators), 3))
    for idx, ind in enumerate(selected_indicators):
      col_target = transform_cols[idx % len(transform_cols)]
      with col_target:
        current_val = st.session_state.indicator_transforms.get(
            ind, "原始水準 (Level/Raw)"
        )
        chosen_transform = st.selectbox(
            f"【{ind}】處理方式",
            transform_options,
            index=(
                transform_options.index(current_val)
                if current_val in transform_options
                else 0
            ),
            key=f"trans_{ind}",
        )
        st.session_state.indicator_transforms[ind] = chosen_transform

  st.markdown("---")
  col_opt1, col_opt2, col_opt3 = st.columns([2, 1, 1])
  with col_opt1:
    time_range = st.selectbox(
        "📅 選擇檢視的時間區間：",
        [
            "近 1 年",
            "近 3 年",
            "近 5 年",
            "近 10 年",
            "近 15 年",
            "全部歷史 (Max)",
        ],
        index=3,
    )
  with col_opt2:
    use_secondary_y = st.checkbox("開啟雙 Y 軸顯示", value=True)
  with col_opt3:
    chart_height = st.slider("圖表高度：", min_value=400, max_value=800, value=500)

  if not selected_indicators:
    st.warning("⚠️ 請至少選擇一項指標進行繪圖與編輯！")
  else:
    dfs_to_merge = []
    with st.spinner("智慧連線 Yahoo / FRED API 擷取並完整對齊歷史數據中..."):
      for ind_name in selected_indicators:
        code_item = st.session_state.custom_indicators.get(ind_name, "")
        code = (
            code_item
            if isinstance(code_item, str)
            else code_item.get("code", "")
        )
        calc_mode = st.session_state.indicator_transforms.get(
            ind_name, "原始水準 (Level/Raw)"
        )

        if code:
          s_df = fetch_smart_data(code)
          if not s_df.empty:
            s_df["Date"] = pd.to_datetime(s_df["Date"])
            s_df = s_df.sort_values("Date").set_index("Date")
            series = s_df.iloc[:, 0]

            if calc_mode == "年增率 (YoY %)":
              processed = series.pct_change(12) * 100
            elif calc_mode == "月/日增額 (Diff)":
              processed = series.diff()
            else:
              processed = series

            res_series = processed.resample("ME").last().dropna()
            res_df = res_series.to_frame(name=ind_name).reset_index()
            dfs_to_merge.append(res_df)

    if dfs_to_merge:
      all_max_date = max([df["Date"].max() for df in dfs_to_merge])
      if time_range == "近 1 年":
        start_date = all_max_date - pd.DateOffset(years=1)
      elif time_range == "近 3 年":
        start_date = all_max_date - pd.DateOffset(years=3)
      elif time_range == "近 5 年":
        start_date = all_max_date - pd.DateOffset(years=5)
      elif time_range == "近 10 年":
        start_date = all_max_date - pd.DateOffset(years=10)
      elif time_range == "近 15 年":
        start_date = all_max_date - pd.DateOffset(years=15)
      else:
        start_date = pd.to_datetime("1900-01-01")

      merged_df = dfs_to_merge[0]
      for df in dfs_to_merge[1:]:
        merged_df = pd.merge(merged_df, df, on="Date", how="outer")
      merged_df = merged_df.sort_values("Date")
      merged_df = merged_df[merged_df["Date"] >= start_date]

      fig = make_subplots(specs=[[{"secondary_y": use_secondary_y}]])
      colors = [
          "#00d2ff",
          "#ff9900",
          "#00ff66",
          "#ff3366",
          "#cc66ff",
          "#ffff33",
          "#33ffff",
      ]

      for idx, col_name in enumerate(selected_indicators):
        if col_name in merged_df.columns:
          sub_df = merged_df[["Date", col_name]].dropna()
          is_sec = use_secondary_y and (idx % 2 == 1)
          fig.add_trace(
              go.Scatter(
                  x=sub_df["Date"],
                  y=sub_df[col_name],
                  name=col_name,
                  line=dict(
                      color=colors[idx % len(colors)],
                      width=2.5 if idx == 0 else 1.8,
                  ),
              ),
              secondary_y=is_sec,
          )

      fig.update_layout(
          title_text="<b>全球總體經濟與金融市場指標動態對比圖</b>",
          height=chart_height,
          template="plotly_dark",
          legend=dict(
              orientation="h",
              yanchor="bottom",
              y=1.02,
              xanchor="right",
              x=1,
          ),
          margin=dict(l=40, r=40, t=60, b=40),
      )
      st.plotly_chart(fig, use_container_width=True)

      with st.expander("📋 檢視與下載合併後的對比數據表格"):
        st.dataframe(merged_df.set_index("Date").sort_index(ascending=False))
        csv_data = merged_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 下載篩選後數據 (.csv)",
            csv_data,
            file_name="macro_indicators_data.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------
# 模組三：基金 / ETF 交易決策評估
# ---------------------------------------------------------
elif app_mode == "🎯 基金 / ETF 交易決策評估":
  st.header("🎯 機構級基金與 ETF 交易決策評估系統")
  st.caption("輸入您的投資標的與基本面觀點，結合最新市場數據進行多維度回測與AI決策分析。")

  col_etf1, col_etf2 = st.columns(2)
  with col_etf1:
    target_ticker = st.text_input(
        "輸入欲評估的基金/ETF 代碼 (例如: 0050.TW, SPY, QQQ, TLT):",
        value="SPY",
    )
  with col_etf2:
    user_view = st.selectbox(
        "您的總經/操作觀點：",
        [
            "看多 (Bullish) - 經濟軟著陸/降息循環",
            "看空 (Bearish) - 經濟衰退/通膨再起/流動性緊縮",
            "震盪避險 (Consolidation/Hedging)",
        ],
    )

  if st.button("🚀 執行量化回測與 AI 決策評估", type="primary"):
    with st.spinner(f"正在擷取 {target_ticker} 歷史走勢並評估多維度量化指標..."):
      df_etf = fetch_smart_data(target_ticker)
      if df_etf.empty:
        st.error(
            f"❌ 無法取得標的【{target_ticker}】的歷史數據，請確認代碼是否正確。"
        )
      else:
        df_etf = df_etf.sort_values("Date")
        recent_price = df_etf.iloc[-1, 1]
        ma200 = (
            df_etf.iloc[:, 1].rolling(window=200).mean().iloc[-1]
            if len(df_etf) >= 200
            else recent_price
        )
        ma50 = (
            df_etf.iloc[:, 1].rolling(window=50).mean().iloc[-1]
            if len(df_etf) >= 50
            else recent_price
        )
        ret_1y = (
            (recent_price / df_etf.iloc[-252, 1] - 1) * 100
            if len(df_etf) >= 252
            else 0
        )

        st.success(
            f"✅ 數據擷取成功！當前價格: **{recent_price:.2f}** | 50日均線: **{ma50:.2f}** | 200日均線: **{ma200:.2f}** | 近1年報酬率: **{ret_1y:.2f}%**"
        )

        eval_prompt = f"""
你是一位頂尖的華爾街量化基金經理人與風險管理委員會主席。
投資人準備評估的標的為：{target_ticker}
當前價格：{recent_price:.2f}
50日均線：{ma50:.2f}
200日均線：{ma200:.2f}
近1年報酬率：{ret_1y:.2f}%
投資人當前總經觀點：{user_view}

請提供一份《機構級基金/ETF 交易決策與風險評估報告》，包含：
1. **技術面與趨勢結構判定**
2. **總經與觀點契合度分析**
3. **具體執行建議（建議配置比例、進場策略、停損停利點位）**
4. **潛在風險警示**
"""
        with st.spinner("🤖 Qwen 正在進行量化決策推演..."):
          eval_report, err = call_qwen_api(
              [{"role": "user", "content": eval_prompt}]
          )
          if eval_report:
            st.markdown("---")
            st.markdown(eval_report)
          else:
            st.error(f"❌ 評估生成失敗: {err}")

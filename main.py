import os
import sys
import time
import datetime
import urllib.parse
import feedparser
from openai import OpenAI

# 1. 取得 API Key
api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    print("❌ 錯誤：找不到 DASHSCOPE_API_KEY")
    sys.exit(1)

client = OpenAI(
    api_key=api_key.strip(),
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)

# 2. 抓取 RSS 新聞
today_str = datetime.datetime.now().strftime("%Y-%m-%d")
rss_urls = [
    "https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com+hl:zh-TW&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=聯準會+OR+美債殖利率+OR+美股三大指數&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
]

raw_news = []
for url in rss_urls:
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            raw_news.append(f"【時間: {entry.get('published', '')}】\n標題: {entry.get('title', '')}\n摘要: {entry.get('summary', '')[:120]}\n")
    except Exception as e:
        print(f"⚠️ RSS 讀取失敗: {e}")

if not raw_news:
    print("❌ 無法取得新聞")
    sys.exit(1)

# 3. 呼叫 Qwen API 生成日報
prompt = f"""
你是一位機構級高級總體經濟分析師。今天是 {today_str}。

以下是今日重點財經新聞原始資料：
{"".join(raw_news)}

請編譯一份標準繁體中文的《每日金融市場要聞》，包含以下章節：
一、全球金融市場焦點與數據速覽
二、總體經濟、央行政策與債券市場
三、科技產業與企業財務動態
四、外匯、大宗商品與信用市場
"""

report_content = None
for model in ['qwen-max', 'qwen-plus', 'qwen-turbo']:
    try:
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        report_content = res.choices[0].message.content
        break
    except Exception as e:
        print(f"⚠️ 模型 {model} 呼叫失敗: {e}")

if not report_content:
    sys.exit(1)

# 4. 寫入檔案
os.makedirs("daily_reports", exist_ok=True)
file_path = f"daily_reports/{today_str}.md"
with open(file_path, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"✅ 成功儲存今日研報至 {file_path}")

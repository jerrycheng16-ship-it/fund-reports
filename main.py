import os
import sys
import time
import re
import datetime
from datetime import timezone, timedelta
import urllib.parse
import feedparser
from openai import OpenAI

# 1. 取得 API Key
api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    print("❌ 錯誤：找不到 DASHSCOPE_API_KEY！請檢查 GitHub Secrets 或環境變數。")
    sys.exit(1)

client = OpenAI(
    api_key=api_key.strip(),
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)

# 2. 強制設定為台灣時間 (UTC+8)
tz_taiwan = timezone(timedelta(hours=8))
today_dt = datetime.datetime.now(tz_taiwan)
today_str = today_dt.strftime("%Y-%m-%d")
date_display = today_dt.strftime("%Y 年 %m 月 %d 日")

# 3. 抓取 RSS 新聞並過濾 HTML 標籤
rss_urls = [
    "https://news.google.com/rss/search?q=site:cn.reuters.com+OR+site:reuters.com+hl:zh-TW&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com+OR+site:finance.yahoo.com+通膨+OR+聯準會+OR+美股+OR+美債+OR+殖利率&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=聯準會+OR+美債殖利率+OR+美股三大指數&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
]

def clean_html(raw_html):
    """去除 RSS 摘要中的 HTML 標籤"""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

raw_news = []
print(f"📡 正在抓取 {date_display} 最新財經新聞...")

for url in rss_urls:
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title = clean_html(entry.get('title', ''))
            published = entry.get('published', '')
            summary = clean_html(entry.get('summary', ''))[:120]
            raw_news.append(f"【時間: {published}】\n標題: {title}\n摘要: {summary}\n")
    except Exception as e:
        print(f"⚠️ RSS 讀取失敗 ({url}): {e}")

if not raw_news:
    print("❌ 錯誤：無法取得任何新聞資料！")
    sys.exit(1)

print(f"✅ 成功擷取 {len(raw_news)} 則新聞資料。")

# 4. 構建 Qwen API Prompt
prompt = f"""
你是一位機構級高級總體經濟分析師與資深財經主編。
今天確切的日期是：{date_display}。

以下是今日重點財經新聞原始資料：
=== 今日新聞資料 ===
{"".join(raw_news)}
====================

【任務要求】：
請編譯一份標準繁體中文的《每日金融市場要聞》，內容需精準、嚴謹且富含數據（如指數漲跌、殖利率 bp 變化等）。

【章節結構】：
一、全球金融市場焦點與數據速覽
二、總體經濟、央行政策與債券市場
三、科技產業與企業財務動態
四、外匯、大宗商品與信用市場
"""

# 5. 呼叫 Qwen API (具備多模型自動降級備用機制)
report_content = None
for model in ['qwen-max', 'qwen-plus', 'qwen-turbo']:
    try:
        print(f"🔄 嘗試使用模型 [{model}] 生成研報...")
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        if res and res.choices:
            report_content = res.choices[0].message.content
            print(f"🎉 模型 [{model}] 回應成功！")
            break
    except Exception as e:
        print(f"⚠️ 模型 [{model}] 呼叫失敗: {e}")
        time.sleep(2)

if not report_content:
    print("❌ 所有模型均無回應或呼叫失敗！")
    sys.exit(1)

# 6. 寫入 Markdown 檔案
os.makedirs("daily_reports", exist_ok=True)
file_path = f"daily_reports/{today_str}.md"

with open(file_path, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"🎉 成功生成並儲存今日研報至：{file_path}")

def search_fred_series_by_llm(keyword):
    """利用 Qwen AI 搜尋最匹配的 FRED Series ID 與推薦名稱"""
    prompt = f"""
你是一個精通 FRED (Federal Reserve Economic Data) 資料庫的總經數據專家。
使用者輸入的自然語言關鍵字為："{keyword}"

請提供 3 個最精準、最常用的 FRED Series ID 與對應名稱。
請嚴格以 JSON 陣列格式輸出，格式如下，不要加任何 Markdown 註解或多餘文字：
[
  {{"code": "CLV10MEURB1GQSCAEA20", "name": "Eurozone Real GDP", "default_calc": "pct_change_4q"}},
  {{"code": "CP0000EZ19M086NEST", "name": "Eurozone CPI YoY", "default_calc": "pct_change_12m"}}
]
"""
    res, err = call_qwen_api([{"role": "user", "content": prompt}])
    if res:
        try:
            # 修正：避開反引號轉義問題，改用 split 與 strip 安全擷取 JSON 內容
            clean_text = res.strip()
            if "```" in clean_text:
                clean_text = clean_text.split("```")[1]
                if clean_text.startswith("json"):
                    clean_text = clean_text[4:]
            clean_json = clean_text.strip()
            import json
            data = json.loads(clean_json)
            return data
        except Exception as e:
            return []
    return []

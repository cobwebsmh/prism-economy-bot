import os
import feedparser
import requests
import yfinance as yf
import json
from datetime import datetime
import pytz
from google import genai

# [설정]
REC_FILE = 'recommendations.json'
HISTORY_FILE = 'history.json'

# ... (기존 get_market_data, verify_past, fetch_global_news 함수는 동일) ...

# 메인 실행부
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
market_info = get_market_data()
past_results = verify_past()
news_data = fetch_global_news()

# AI 프롬프트 수정 (종목명만 깔끔하게 추출하도록 강조)
prompt = f"""
전략가로서 다음 데이터를 분석하세요:
1. 뉴스: {news_data[:15]}
2. 어제 성적: {past_results}

다음 형식의 JSON으로만 답하세요:
{{
  "summary": "시장 요약 3문장 이내",
  "news_headlines": ["핵심뉴스1", ..., "핵심뉴스7"],
  "tickers": ["삼성전자", "SK하이닉스", "NVDA"], 
  "reason": "종목 선정 이유와 괄호 안의 상세 설명을 여기에 포함하여 작성하세요."
}}
"""

response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
ai_data = json.loads(response.text.replace('```json', '').replace('```', ''))

# 최종 데이터 병합
final_data = {
    "date": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),
    "market_info": market_info,
    "past_results": past_results,
    **ai_data
}

# 1. recommendations.json 저장 (현재 화면용)
with open(REC_FILE, 'w', encoding='utf-8') as f:
    json.dump(final_data, f, ensure_ascii=False, indent=2)

# 2. history.json 누적 저장 (통계용)
try:
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    
    # 오늘 기록 추가
    history.append({
        "date": final_data["date"],
        "performance": past_results,
        "predictions": ai_data["tickers"]
    })
    
    # 최근 30일 데이터만 유지
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)
except Exception as e:
    print(f"History 저장 실패: {e}")

print("✅ 분석 및 History 누적 완료")

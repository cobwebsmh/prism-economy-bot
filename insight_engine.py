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

def get_market_data():
    """지수 데이터 및 시장 상태 확인"""
    indices = {
        "KOSPI": "^KS11", "KOSDAQ": "^KQ11", 
        "S&P500": "^GSPC", "NASDAQ": "^IXIC"
    }
    result = {}
    now_utc = datetime.now(pytz.utc)
    
    for name, ticker in indices.items():
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) >= 2:
            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = ((current - prev) / prev) * 100
            
            # 시장 상태 (한국/미국 구분)
            is_open = False
            if name in ["KOSPI", "KOSDAQ"]:
                kst = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                is_open = kst.weekday() < 5 and 9 <= kst.hour < 16
            else:
                est = now_utc.astimezone(pytz.timezone('US/Eastern'))
                is_open = est.weekday() < 5 and 9 <= est.hour < 17 # 장외 포함 넉넉히

            result[name] = {
                "price": round(current, 2),
                "change": round(change, 2),
                "status": "🟢" if is_open else "⚪"
            }
    return result

def verify_past():
    """어제 추천 종목 성적 확인"""
    try:
        with open(REC_FILE, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            past_tickers = old_data.get('tickers', [])
            results = []
            for t in past_tickers:
                s = yf.Ticker(t)
                h = s.history(period="2d")
                if len(h) >= 2:
                    c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                    results.append({"ticker": t, "change": round(c, 2)})
            return results
    except: return []

def fetch_global_news():
    """한국 및 글로벌 뉴스 수집"""
    feeds = [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"
    ]
    news_list = []
    for url in feeds:
        f = feedparser.parse(url)
        for entry in f.entries[:10]:
            news_list.append(entry.title)
    return news_list

# 메인 실행부
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
market_info = get_market_data()
past_results = verify_past()
news_data = fetch_global_news()

# AI 프롬프트 (프리즘님의 요청 반영)
prompt = f"""
전략가로서 다음 데이터를 분석하세요:
1. 뉴스: {news_data[:15]}
2. 어제 성적: {past_results}

다음 형식의 JSON으로만 답하세요:
{{
  "summary": "시장 요약 3문장 이내",
  "news_headlines": ["핵심뉴스1", "핵심뉴스2", ... "핵심뉴스7"],
  "tickers": ["추천티커1", "추천티커2", "추천티커3"],
  "reason": "추천 이유 요약"
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

with open(REC_FILE, 'w', encoding='utf-8') as f:
    json.dump(final_data, f, ensure_ascii=False, indent=2)

print("✅ 분석 완료 및 저장됨")

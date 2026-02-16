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

def get_market_data():
    """지수 데이터 및 시장 상태 확인 (🟢/⚪)"""
    indices = {
        "KOSPI": "^KS11", "KOSDAQ": "^KQ11", 
        "S&P500": "^GSPC", "NASDAQ": "^IXIC"
    }
    result = {}
    now_utc = datetime.now(pytz.utc)
    
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((current - prev) / prev) * 100
                
                # 시장 개장 상태 판별
                if name in ["KOSPI", "KOSDAQ"]:
                    kst = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                    is_open = kst.weekday() < 5 and 9 <= kst.hour < 16
                else:
                    est = now_utc.astimezone(pytz.timezone('US/Eastern'))
                    is_open = est.weekday() < 5 and 9 <= est.hour < 17

                result[name] = {
                    "price": round(current, 2),
                    "change": round(change, 2),
                    "status": "🟢" if is_open else "⚪"
                }
        except:
            continue
    return result

def verify_past():
    """어제 추천 종목 성적 확인"""
    try:
        if not os.path.exists(REC_FILE): return []
        with open(REC_FILE, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            past_tickers = old_data.get('tickers', [])
            results = []
            for t in past_tickers:
                # 괄호 제거 후 티커만 추출 (예: "삼성전자(005930)" -> "005930.KS")
                clean_t = t.split('(')[-1].replace(')', '') if '(' in t else t
                if clean_t.isdigit() and len(clean_t) == 6: clean_t += ".KS"
                
                s = yf.Ticker(clean_t)
                h = s.history(period="2d")
                if len(h) >= 2:
                    c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                    results.append({"ticker": t.split('(')[0], "change": round(c, 2)})
            return results
    except: return []


def fetch_global_news():
    """뉴스 제목과 링크를 함께 수집"""
    feeds = [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"
    ]
    news_list = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]: # 각 소스당 5개씩
                news_list.append({
                    "title": entry.title,
                    "link": entry.link # 링크 추가!
                })
        except: continue
    return news_list


# --- 메인 실행 로직 ---
try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()

    prompt = f"""
    전략가로서 다음 데이터를 분석하세요:
    1. 뉴스: {news_data[:15]}
    2. 어제 성적: {past_results}

    반드시 다음 형식의 JSON으로만 답하세요:
    {{
      "summary": "시장 요약 3문장 이내",
      "news_headlines": ["핵심뉴스1", "핵심뉴스2", "핵심뉴스3", "핵심뉴스4", "핵심뉴스5"],
      "tickers": ["삼성전자", "SK하이닉스", "NVDA"], 
      "reason": "종목 선정 이유와 상세 분석 내용을 여기에 포함하세요."
    }}
    """

    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    # JSON 파싱 전처리
    clean_response = response.text.strip().replace('```json', '').replace('```', '')
    ai_data = json.loads(clean_response)

    # 데이터 병합
    final_data = {
        "date": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),
        "market_info": market_info,
        "past_results": past_results,
        **ai_data
    }

    # 1. recommendations.json 저장
    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    # 2. history.json 누적
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    
    history.append({
        "date": final_data["date"],
        "performance": past_results,
        "predictions": ai_data["tickers"]
    })
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)

    print("✅ 모든 작업 성공적 완료")

except Exception as e:
    print(f"❌ 오류 발생: {e}")

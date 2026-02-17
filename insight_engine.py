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
    """주요 시장 지수 데이터 수집 및 '날짜 기반' 개장 여부 판단"""
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC"}
    result = {}
    now_utc = datetime.now(pytz.utc)
    
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            # 연휴 기간을 고려하여 5일치 데이터를 가져옴
            hist = stock.history(period="5d")
            if not hist.empty and len(hist) >= 1:
                current_day = hist.iloc[-1]
                prev_day = hist.iloc[-2] if len(hist) >= 2 else current_day
                
                current_price = current_day['Close']
                prev_price = prev_day['Close']
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                # 핵심: 데이터의 날짜와 현재 날짜를 비교하여 휴장 여부 판단
                if name in ["KOSPI", "KOSDAQ"]:
                    kst_now = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                    data_date = hist.index[-1].astimezone(pytz.timezone('Asia/Seoul')).date()
                    is_today = (data_date == kst_now.date())
                    # 한국 시간 기준 9시~16시 & 오늘 데이터 & 거래량 존재
                    is_open = is_today and (9 <= kst_now.hour < 16) and (current_day['Volume'] > 0)
                else:
                    est_now = now_utc.astimezone(pytz.timezone('US/Eastern'))
                    data_date_us = hist.index[-1].astimezone(pytz.timezone('US/Eastern')).date()
                    is_today_us = (data_date_us == est_now.date())
                    # 미국 시간 기준 9시~17시 & 오늘 데이터 & 거래량 존재
                    is_open = is_today_us and (9 <= est_now.hour < 17) and (current_day['Volume'] > 0)
                
                result[name] = {
                    "price": round(current_price, 2), 
                    "change": round(change_pct, 2), 
                    "is_open": is_open,
                    "status": "🟢" if is_open else "⚪"
                }
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            continue
    return result

def verify_past():
    """어제 추천 종목의 오늘 수익률 확인 (휴장일 수익률 0% 처리)"""
    ticker_map = {
        "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "NAVER": "035420.KS", 
        "카카오": "035720.KS", "현대차": "005380.KS", "NVDA": "NVDA", "AAPL": "AAPL", "TSLA": "TSLA"
    }
    try:
        if not os.path.exists(REC_FILE): return []
        with open(REC_FILE, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            past_tickers = old_data.get('tickers', [])
            results = []
            for t in past_tickers:
                clean_t = ticker_map.get(t, t)
                if clean_t.isdigit() and len(clean_t) == 6: clean_t += ".KS"
                
                try:
                    s = yf.Ticker(clean_t)
                    h = s.history(period="2d")
                    if not h.empty and len(h) >= 2:
                        # 오늘 거래량이 없으면 수익률 계산 제외 (0.0으로 표시)
                        if h['Volume'].iloc[-1] == 0:
                            results.append({"ticker": t, "change": 0.0})
                        else:
                            c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                            results.append({"ticker": t, "change": round(c, 2)})
                except: continue
            return results
    except: return []

def fetch_global_news():
    """뉴스 데이터 수집"""
    feeds = [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"
    ]
    news_list = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]:
                news_list.append({"title": entry.title.replace('"', "'"), "link": entry.link})
        except: continue
    return news_list

# --- 메인 실행 ---
try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()

    kr_status = "개장" if market_info.get("KOSPI", {}).get("is_open") else "휴장"
    us_status = "개장" if market_info.get("S&P500", {}).get("is_open") else "휴장"

    prompt = f"""
    당신은 프리즘(Prism) AI 금융 분석가입니다.
    현재 시장 상태: 한국({kr_status}), 미국({us_status})
    원천 데이터: 뉴스({news_data}), 과거성적({past_results})

    [지침]
    1. 현재 '개장' 상태인 시장의 종목을 최우선적으로 추천하세요. 
    2. 양쪽 모두 개장 시 한국과 미국 종목을 적절히 섞어서 추천하세요.
    3. 한국이 휴장일 경우 미국 시장 위주로, 미국이 휴장일 경우 한국 시장 위주로 분석하세요.
    4. 반드시 아래 JSON 형식으로만 출력하세요.

    {{
      "summary": "시장 상황 3문장 요약",
      "news_headlines": [ {{"title": "뉴스제목", "link": "링크"}} ],
      "tickers": ["종목명1", "종목명2", "종목명3"],
      "reason": "추천 사유 (어느 시장이 휴장이라 어떤 전략을 취했는지 포함)"
    }}
    """

    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    ai_data = json.loads(response.text.strip().replace('```json', '').replace('```', ''))

    final_data = {
        "date": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),
        "market_info": market_info,
        "past_results": past_results,
        **ai_data
    }

    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    # 히스토리 업데이트 (휴장일 제외)
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    
    history.append({
        "date": final_data["date"],
        "performance": [r for r in past_results if r['change'] != 0],
        "predictions": ai_data["tickers"]
    })
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)

    print(f"✅ 리포트 생성 완료 (KR:{kr_status} / US:{us_status})")

except Exception as e:
    print(f"❌ 오류 발생: {e}")

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
    """주요 시장 지수 데이터 수집 및 개장 여부 판단"""
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC"}
    result = {}
    now_utc = datetime.now(pytz.utc)
    
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d") # 연휴 대비 5일치
            if not hist.empty and len(hist) >= 2:
                current_day = hist.iloc[-1]
                prev_day = hist.iloc[-2]
                
                current = current_day['Close']
                prev = prev_day['Close']
                change = ((current - prev) / prev) * 100
                
                # 거래량이 0이면 휴장으로 판단
                is_vol_zero = current_day['Volume'] == 0
                
                if name in ["KOSPI", "KOSDAQ"]:
                    kst = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                    # 시간 체크 + 거래량 체크
                    is_open = (kst.weekday() < 5 and 9 <= kst.hour < 16) and not is_vol_zero
                else:
                    est = now_utc.astimezone(pytz.timezone('US/Eastern'))
                    is_open = (est.weekday() < 5 and 9 <= est.hour < 17) and not is_vol_zero
                
                result[name] = {
                    "price": round(current, 2), 
                    "change": round(change, 2), 
                    "is_open": is_open,
                    "status": "🟢" if is_open else "⚪"
                }
        except: continue
    return result

def verify_past():
    """어제 추천 종목 수익률 확인 (휴장일 제외 로직)"""
    # 티커 맵 확장 (미국 종목 포함 가능성 대비)
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
                # 한국 종목 티커 처리
                if clean_t.isdigit() and len(clean_t) == 6: clean_t += ".KS"
                
                try:
                    s = yf.Ticker(clean_t)
                    h = s.history(period="2d")
                    if not h.empty and len(h) >= 2:
                        # 오늘 거래량이 0이면 수익률 0% 처리 (적중률 영향 없음)
                        if h['Volume'].iloc[-1] == 0:
                            results.append({"ticker": t, "change": 0.0})
                        else:
                            c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                            results.append({"ticker": t, "change": round(c, 2)})
                except: continue
            return results
    except: return []

def fetch_global_news():
    """글로벌 뉴스 수집"""
    feeds = [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"
    ]
    news_list = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]:
                clean_title = entry.title.replace('"', "'").replace('\\', '')
                news_list.append({"title": clean_title, "link": entry.link})
        except: continue
    return news_list

# --- 메인 로직 ---
try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()

    # 시장 개장 상태 파악 (추천 가이드라인)
    kr_open = market_info.get("KOSPI", {}).get("is_open", False)
    us_open = market_info.get("S&P500", {}).get("is_open", False)

    prompt = f"""
    당신은 글로벌 금융 분석가입니다. 다음 데이터를 분석하여 투자 리포트를 작성하세요.
    현재 시장 개장 상태: 한국({'개장' if kr_open else '휴장'}), 미국({'개장' if us_open else '휴장'})

    [요구사항]
    1. 개장 중인 시장의 종목을 우선적으로 3개 추천하세요. (둘 다 휴장일 경우 가장 최근 유망주 추천)
    2. news_headlines에 제공된 뉴스 {news_data}를 포함하세요.
    3. 반드시 아래 JSON 형식으로만 응답하세요.

    {{
      "summary": "시장 상황 3문장 요약",
      "news_headlines": [ {{"title": "제목", "link": "링크"}} ],
      "tickers": ["종목명1", "종목명2", "종목명3"],
      "reason": "추천 사유 (어느 시장이 휴장인지 언급 포함)"
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

    # 히스토리 저장 (수익률이 0인 휴장일 데이터는 적중률 계산에서 제외됨)
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    else: history = []

    history.append({
        "date": final_data["date"],
        "performance": [r for r in past_results if r['change'] != 0], # 0%인 데이터는 기록에서 제외(선택사항)
        "predictions": ai_data["tickers"]
    })
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)

    print("✅ 지능형 리포트 생성 완료")

except Exception as e:
    print(f"❌ 오류: {e}")

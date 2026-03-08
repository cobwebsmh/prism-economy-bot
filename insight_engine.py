import os
import feedparser
import requests
import yfinance as yf
import json
from datetime import datetime
import pytz
from google import genai
import firebase_admin
from firebase_admin import credentials, messaging

# [설정]
REC_FILE = 'recommendations.json'
HISTORY_FILE = 'history.json'

def send_push_notification(title, body):
    try:
        service_account_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if not service_account_str: return
        service_account_info = json.loads(service_account_str)
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic="all_users", 
        )
        messaging.send(message)
        print(f"✅ 푸시 알림 발송 성공")
    except Exception as e:
        print(f"❌ 푸시 알림 발송 실패: {e}")

def get_market_data():
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC"}
    result = {}
    now_utc = datetime.now(pytz.utc)
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty:
                curr = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) >= 2 else curr
                change_val = ((curr['Close'] - prev['Close']) / prev['Close']) * 100
                is_open_val = False
                if name in ["KOSPI", "KOSDAQ"]:
                    kst = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                    is_open_val = bool((9 <= kst.hour < 16) and (curr['Volume'] > 0))
                else:
                    est = now_utc.astimezone(pytz.timezone('US/Eastern'))
                    is_open_val = bool((9 <= est.hour < 17) and (curr['Volume'] > 0))
                result[name] = {
                    "price": float(round(curr['Close'], 2)), 
                    "change": float(round(change_val, 2)), 
                    "is_open": is_open_val,
                    "status": "🟢" if is_open_val else "⚪"
                }
        except: continue
    return result

def check_trading_day():
    now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
    is_kr_trading_day = now_kst.weekday() < 5 
    is_us_trading_day = now_kst.weekday() < 5
    kr_status_msg = "정상 거래일(개장 예정)" if is_kr_trading_day else "휴장(주말)"
    us_status_msg = "정상 거래일(개장 예정)" if is_us_trading_day else "휴장(주말)"
    return kr_status_msg, us_status_msg

def verify_past():
    """AI가 제공한 정밀 티커(symbol)를 사용하여 수익률 검증"""
    try:
        if not os.path.exists(REC_FILE): return []
        with open(REC_FILE, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            past_tickers = old_data.get('tickers', [])
            results = []
            for item in past_tickers:
                # 새로운 구조 {"name": "...", "symbol": "..."} 대응
                name = item.get('name')
                symbol = item.get('symbol')
                try:
                    s = yf.Ticker(symbol)
                    h = s.history(period="2d")
                    if len(h) >= 2:
                        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                        results.append({"ticker": name, "change": float(round(c, 2))})
                except Exception as e:
                    print(f"⚠️ {name}({symbol}) 수익률 조회 실패: {e}")
                    continue
            return results
    except: return []

def fetch_global_news():
    feeds = ["https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR", 
             "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"]
    news_list = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:15]:
                news_list.append({
                    "title": str(entry.title).replace('"', "'"), 
                    "link": str(entry.link),
                    "published": getattr(entry, 'published', 'N/A')
                })
        except: continue
    return news_list

try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()
    kr_trading_status, us_trading_status = check_trading_day()

    prompt = f"""
    당신은 프리즘(Prism) AI 금융 분석가입니다. 30개의 최신 뉴스를 분석하여 전문가로서 시장의 심리와 기술적 위치를 분석하고 제공된 {len(news_data)}개의 뉴스를 분석하여 핵심 모멘텀을 파악하세요.

    [데이터]
    - 시장 상태: 한국({kr_trading_status}), 미국({us_trading_status})
    - 지수: {market_info}
    - 뉴스: {news_data}

    [필수 규칙]
    1. 데이터 마이닝: 반복 언급되는 키워드나 섹터를 추출하여 '주도 테마'를 설정하세요.
    2. 종목 선정: 과매수(RSI 과열)를 피하고 '무릎' 위치의 종목을 선정하세요.
    3. 종목 구성: 한국이 '{kr_trading_status}'라면 한국 종목 1개는 꼭 포함시켜서 미국종목 포함 총 3개의 종목을 추천하세요 (한국이 오늘 내일 모두 휴장 시 미국 3개).
    4. 티커 형식: 야후 파이낸스에서 인식 가능한 정확한 티커를 'symbol'에 넣으세요.
       (한국은 005930.KS 또는 028300.KQ 형식, 미국은 NVDA, AAPL 형식)
    5. 트리맵 데이터: 뉴스 분석을 통해 추출한 핵심 키워드 8~10개의 비중(weight, 합계 100)을 계산하세요.

    [출력 양식]
    {{
      "summary": "시장 심리 분석 (3문장)",
      "news_headlines": [ {{"title": "제목", "link": "링크"}} ],
      "sectors": [ {{"name": "섹터", "sentiment": "HOT", "reason": "이유"}} ],
      "tickers": [
        {{"name": "포스코홀딩스", "symbol": "005490.KS"}},
        {{"name": "NVIDIA", "symbol": "NVDA"}},
        {{"name": "애플", "symbol": "AAPL"}}
      ],
      "keywords": [ {{"name": "키워드", "weight": 25}} ],
      "reason": "추천 사유 및 기술적 위치 분석",
      "push_message": "알림 요약"
    }}
    """
    
    response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
    raw_text = response.text.strip()
    ai_data = json.loads(raw_text[raw_text.find('{'):raw_text.rfind('}') + 1])

    final_output = {
        "date": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),
        "market_info": market_info,
        "past_results": past_results,
        "summary": ai_data.get("summary", ""),
        "news_headlines": ai_data.get("news_headlines", []),
        "sectors": ai_data.get("sectors", []),
        "tickers": ai_data.get("tickers", []), # 객체 리스트 유지
        "keywords": ai_data.get("keywords", []),
        "reason": ai_data.get("reason", ""),
        "push_message": ai_data.get("push_message", "")
    }

    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    # 히스토리 업데이트 (이름만 추출해서 저장)
    history_list = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
        except: history_list = []
    
    history_list.append({
        "date": final_output["date"],
        "performance": past_results,
        "predictions": [t['name'] for t in final_output["tickers"]]
    })
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_list[-30:], f, ensure_ascii=False, indent=2)

    send_push_notification("💎 프리즘 인사이트", final_output["push_message"])
    print(f"✅ 모든 공정 성공 완료")

except Exception as e:
    print(f"❌ 오류 발생: {e}")

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
    """Firebase를 통해 모든 앱 사용자에게 알림 전송"""
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
    """주요 시장 지수 데이터 수집 및 안전한 데이터 타입 변환"""
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
                
                # 개장 여부 판단
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
    """오늘이 한국/미국의 실제 거래 가능일(평일)인지 확인"""
    now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
    # 월(0)~일(6) 중 토(5), 일(6)이 아니면 거래일로 간주 (공휴일은 뉴스/볼륨으로 AI가 추가 판단)
    is_kr_trading_day = now_kst.weekday() < 5 
    
    # 미국 시장은 한국 시간 기준 당일 밤 혹은 익일 새벽에 열리므로 동일하게 평일 여부 판단
    is_us_trading_day = now_kst.weekday() < 5
    
    kr_status_msg = "정상 거래일(개장 예정)" if is_kr_trading_day else "휴장(주말)"
    us_status_msg = "정상 거래일(개장 예정)" if is_us_trading_day else "휴장(주말)"
    
    return kr_status_msg, us_status_msg

def verify_past():
    """어제 추천 종목 수익률 확인"""
    ticker_map = {
        "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "NAVER": "035420.KS", 
        "카카오": "035720.KS", "현대차": "005380.KS", "NVDA": "NVDA", "AAPL": "AAPL", "TSLA": "TSLA",
        "MSFT": "MSFT", "GOOGL": "GOOGL", "GOOG": "GOOG"
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
                    if len(h) >= 2:
                        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                        results.append({"ticker": str(t), "change": float(round(c, 2))})
                except: continue
            return results
    except: return []

def fetch_global_news():
    feeds = ["https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"]
    news_list = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:15]:
                news_list.append({
                    "title": str(entry.title).replace('"', "'"), 
                    "link": str(entry.link),
                    "published": getattr(entry, 'published', 'N/A') # 발행 시간 추가
                })
        except: continue
    return news_list

# --- 메인 실행 ---
try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()

    # [수정 포인트] 시점 기반이 아닌 '날짜 기반' 거래일 판단
    kr_trading_status, us_trading_status = check_trading_day()

    prompt = f"""
    당신은 프리즘(Prism) AI 금융 분석가입니다. 
    전문가로서 단순히 뉴스를 전달하는 것이 아니라, 시장의 심리와 기술적 위치를 분석하고 제공된 {len(news_data)}개의 최신 뉴스를 교차 분석하여 시장의 핵심 모멘텀을 파악하세요.

    [데이터]
    - 시장 상태: 한국({kr_trading_status}), 미국({us_trading_status})
    - 뉴스 스냅샷: {news_data}
    - 최근 지수 흐름: {market_info}

    [분석 지침]
    1. **데이터 마이닝**: 많은 뉴스 중 반복적으로 언급되는 키워드나 섹터를 추출하여 '주도 테마'를 설정하세요.
    2. **필터링**: 뉴스 수집량이 늘어난 만큼, 자극적인 헤드라인보다는 실제 실적이나 기술적 우위, 매크로 지표가 뒷받침되는 종목을 선별하세요.
    3. **기술적/심리적 필터링 (중요)**:
    - **과매수 경계**: 최근 며칠간 급등하여 RSI가 높을 것으로 예상되거나 '탐욕'이 지배적인 종목은 피하세요. (고점에서 추천하는 실수를 방지)
    - **무릎 위치 선정**: 강력한 호재가 있지만 아직 주가가 본격적으로 분출되지 않았거나, 건강한 조정을 거치고 반등 직전인 '무릎' 위치의 종목을 우선하세요.
    - **매크로 분석**: 뉴스가 개별 호재라 하더라도 금리나 환율 등 거시 경제 흐름에 역행하는 종목은 제외하세요.
    
    
    [투자 전략 및 종목 선정 규칙]
    1. **종목 구성 비율 강제 규칙**:
       - 한국이 '{kr_trading_status}' 상태라면, **무조건 한국 종목 1개**는 꼭 포함시켜서 추천하세요.
       - 한국 시장이 '휴장(주말)'인 경우에만 미국 종목으로 3개를 채우세요.
       - 오늘 한국 시장이 열리는 날임에도 미국 종목만 추천하는 것은 금지됩니다.
       - 추천종목 tickers 배열에는 반드시 종목 코드(숫자)가 아닌 사람이 읽을 수 있는 '한글명' 또는 '공식 기업명'(예: '삼성전자', 'SK하이닉스', 'NVIDIA')으로 작성하세요.

    2. [출력 양식]: 반드시 아래 JSON 형식으로만 답변하고 앞뒤 설명은 생략하세요.

    3. [키워드 분석]: 수집된 30개의 뉴스에서 가장 많이 언급된 핵심 키워드 8~10개를 추출하고 비중(%)을 계산하세요. 
    비중의 총합은 100%가 되어야 합니다.
    
    {{
      "summary": "시장 흐름 및 과열/공포 심리 분석 (3문장)",
      "news_headlines": [ {{"title": "뉴스제목", "link": "링크"}} ],
      "sectors": [ {{"name": "섹터명", "sentiment": "HOT", "reason": "이유"}} ],
      "tickers": ["종목1", "종목2", "종목3"],
      "reason": "기술적 위치(과매수 여부 등)와 호재를 결합한 추천 사유",
      "push_message": "알림용 요약"
    }}
    """
    
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    raw_text = response.text.strip()
    
    start_idx = raw_text.find('{')
    end_idx = raw_text.rfind('}') + 1
    ai_data = json.loads(raw_text[start_idx:end_idx])

    final_output = {
        "date": str(datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')),
        "market_info": market_info,
        "past_results": past_results,
        "summary": str(ai_data.get("summary", "")),
        "news_headlines": ai_data.get("news_headlines", []),
        "sectors": ai_data.get("sectors", []),
        "tickers": [str(t) for t in ai_data.get("tickers", [])],
        "reason": str(ai_data.get("reason", "")),
        "push_message": str(ai_data.get("push_message", "오늘의 분석 완료"))
    }

    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    history_list = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
        except: history_list = []
    
    history_list.append({
        "date": final_output["date"],
        "performance": past_results,
        "predictions": final_output["tickers"]
    })
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_list[-30:], f, ensure_ascii=False, indent=2)

    send_push_notification("💎 프리즘 인사이트", final_output["push_message"])
    print(f"✅ 모든 공정 성공 완료 (KR:{kr_trading_status}/US:{us_trading_status})")

except Exception as e:
    print(f"❌ 최종 실행 오류 발생: {e}")

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
    """Firebase를 통해 모든 앱 사용자(all_users 토픽 구독자)에게 알림 전송"""
    try:
        service_account_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if not service_account_str:
            print("⚠️ FIREBASE_SERVICE_ACCOUNT Secret이 설정되지 않았습니다.")
            return

        service_account_info = json.loads(service_account_str)
        
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            topic="all_users", 
        )
        
        response = messaging.send(message)
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
                
                # 개장 여부 판단 및 bool 타입 강제 변환
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

def verify_past():
    """어제 추천 종목의 오늘 수익률 확인 및 타입 변환"""
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
                    if len(h) >= 2:
                        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                        results.append({"ticker": str(t), "change": float(round(c, 2))})
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
            for entry in f.entries[:7]: # 뉴스 개수 7개로 상향
                news_list.append({"title": str(entry.title).replace('"', "'"), "link": str(entry.link)})
        except: continue
    return news_list

# --- 메인 실행 ---
try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()

    # 시장 상태 텍스트화
    kr_status = "개장" if market_info.get("KOSPI", {}).get("is_open") else "휴장"
    us_status = "개장" if market_info.get("S&P500", {}).get("is_open") else "휴장"

    prompt = f"""
    당신은 프리즘(Prism) AI 금융 분석가입니다.
    현재 시장 상태: 한국({kr_status}), 미국({us_status})
    데이터: 뉴스({news_data}), 과거성적({past_results})

    [투자 전략 지침]
    1. **추천 종목 선정 최우선 순위**:
       - 한국이 오늘/내일 휴장이라면 한국 종목은 제외하고 오늘 밤 열릴 미국 시장 종목 위주로 3개를 추천하세요.
       - 현재 개장 중인 시장({kr_status})의 기회를 우선 분석하세요.
    2. [뉴스] 글로벌 경제 뉴스를 기반으로 중요한 헤드라인 5~10개를 정리하세요.
    3. [출력] 반드시 아래 JSON 형식으로만 답변하고 앞뒤 설명은 생략하세요.

    {{
      "summary": "시장 요약 3문장",
      "news_headlines": [ {{"title": "뉴스제목", "link": "링크"}} ],
      "sectors": [ {{"name": "섹터명", "sentiment": "HOT", "reason": "이유"}} ],
      "tickers": ["종목1", "종목2", "종목3"],
      "reason": "추천 사유",
      "push_message": "알림용 요약"
    }}
    """

    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    raw_text = response.text.strip()
    
    # 안전한 JSON 추출
    start_idx = raw_text.find('{')
    end_idx = raw_text.rfind('}') + 1
    ai_data = json.loads(raw_text[start_idx:end_idx])

    # 최종 데이터 구조 생성 (모든 타입 str, float, bool 확인)
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

    # 파일 저장
    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    # 히스토리 업데이트
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

    # 푸시 알림 발송
    send_push_notification("💎 프리즘 인사이트", final_output["push_message"])
    print(f"✅ 모든 공정 성공 완료 (KR:{kr_status}/US:{us_status})")

except Exception as e:
    print(f"❌ 최종 실행 오류 발생: {e}")

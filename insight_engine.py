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
        # GitHub Secrets에 저장한 JSON 문자열을 로드
        service_account_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if not service_account_str:
            print("⚠️ FIREBASE_SERVICE_ACCOUNT Secret이 설정되지 않았습니다.")
            return

        service_account_info = json.loads(service_account_str)
        
        # Firebase 초기화 (중복 초기화 방지)
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        
        # 'all_users' 토픽을 구독한 모든 기기에 메시지 구성
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            topic="all_users", 
        )
        
        response = messaging.send(message)
        print(f"✅ 푸시 알림 발송 성공: {response}")
    except Exception as e:
        print(f"❌ 푸시 알림 발송 실패: {e}")

def get_market_data():
    """주요 시장 지수 데이터 수집 및 '날짜 기반' 개장 여부 판단"""
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC"}
    result = {}
    now_utc = datetime.now(pytz.utc)
    
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty and len(hist) >= 1:
                current_day = hist.iloc[-1]
                prev_day = hist.iloc[-2] if len(hist) >= 2 else current_day
                
                current_price = current_day['Close']
                prev_price = prev_day['Close']
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                if name in ["KOSPI", "KOSDAQ"]:
                    kst_now = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                    data_date = hist.index[-1].astimezone(pytz.timezone('Asia/Seoul')).date()
                    is_today = (data_date == kst_now.date())
                    is_open = is_today and (9 <= kst_now.hour < 16) and (current_day['Volume'] > 0)
                else:
                    est_now = now_utc.astimezone(pytz.timezone('US/Eastern'))
                    data_date_us = hist.index[-1].astimezone(pytz.timezone('US/Eastern')).date()
                    is_today_us = (data_date_us == est_now.date())
                    is_open = is_today_us and (9 <= est_now.hour < 17) and (current_day['Volume'] > 0)
                
                result[name] = {
                    "price": round(current_price, 2), 
                    "change": round(change_pct, 2), 
                    "is_open": is_open,
                    "status": "🟢" if is_open else "⚪"
                }
        except: continue
    return result

def verify_past():
    """어제 추천 종목의 오늘 수익률 확인"""
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

    # [수정된 프롬프트]
    prompt = f"""
    당신은 프리즘(Prism) AI 금융 분석가입니다.
    현재 시장 상태: 한국({kr_status}), 미국({us_status})
    데이터: 뉴스({news_data}), 과거성적({past_results})

    [투자 전략 지침]
    1. **추천 종목 선정 최우선 순위**:
       - 한국 또는 미국이 오늘/내일 휴장이라면, 휴장예정인 시장의 종목은 분석에서 제외하세요.
       - 한국이 오늘/내일 휴장이고 오늘 밤(또는 현재) 미국장이 열린다면, 반드시 미국 시장(NASDAQ, S&P500) 종목 위주로 3개를 추천하세요.
       - 한국 및 global 경제 뉴스를 면밀히 분석하여 이를 바탕으로 투자자가 바로 거래할 수 있는 시장의 종목을 추천하는 것이 핵심입니다.
    2. [뉴스] 수집된 뉴스 데이터를 기반으로 가장 중요한 헤드라인 5~10개를 정리하세요.
    3. [섹터] 현재 유망한 섹터 3개를 HOT/COOL로 분류하세요.

    {{
      "summary": "시장 요약 3문장",
      "news_headlines": [ {{"title": "뉴스제목", "link": "링크"}} ],
      "sectors": [ {{"name": "섹터명", "sentiment": "HOT", "reason": "이유"}} ],
      "tickers": ["추천 종목 3개"],
      "reason": "추천 사유",
      "push_message": "알림용 요약"
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

    # 히스토리 업데이트
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

    # --- [핵심] 푸시 알림 발송 ---
    push_title = "💎 프리즘 인사이트 리포트"
    push_msg = ai_data.get("push_message", "오늘의 시장 분석이 완료되었습니다.")
    send_push_notification(push_title, push_msg)

    print(f"✅ 엔진 가동 및 푸시 알림 전송 완료!")

except Exception as e:
    print(f"❌ 오류 발생: {e}")

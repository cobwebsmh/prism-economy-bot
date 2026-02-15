import os
import feedparser
import requests
import yfinance as yf
import json
import re
from datetime import datetimeㅁ
import pytz

# 라이브러리 임포트
try:
    from google import genai
except ImportError:
    from google.genai import Client

# [설정값]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
REC_FILE = 'recommendations.json'

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 3800:
        message = message[:3800] + "\n\n...(중략)"
    
    # parse_mode를 제거하여 특수 기호 충돌을 원천 차단합니다.
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message} 
    
    try:
        response = requests.post(url, json=payload)
        if response.json().get("ok"):
            print("✅ 텔레그램 전송 성공!")
        else:
            print(f"❌ 전송 실패: {response.json().get('description')}")
    except Exception as e:
        print(f"전송 오류: {e}")

def get_market_indices():
    """세계 주요 지수 수집"""
    indices = {"S&P 500": "^GSPC", "나스닥": "^IXIC", "코스피": "^KS11", "닛케이225": "^N225"}
    market_data = []
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                market_data.append({"name": name, "change": round(change, 2)})
        except: continue
    return market_data

def run_analysis():
    print("🚀 프리즘 인사이트 엔진 가동...")
    
    # 1. 데이터 수집
    market_indices = get_market_indices()
    kr_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
    us_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en")
    
    mixed_news = [f"[국내] {e.title}" for e in kr_feed.entries[:5]] + [f"[글로벌] {e.title}" for e in us_feed.entries[:5]]
    news_text = "\n".join(mixed_news)

    # 2. 유연한 분석 프롬프트 (JSON 형식 강제)
    prompt = f"""
전략가로서 다음 뉴스를 분석해 시장 흐름 요약과 추천 종목 3개를 제시하세요.
[뉴스]: {news_text}

반드시 다음 형식을 지켜주세요:
1. 요약: (시장 흐름 한 문장 요약)
2. 종목: (종목명과 이유)
3. TICKERS: ["티커1", "티커2", "티커3"]
"""

    # 3. AI 분석
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        full_text = response.text
        print("✅ AI 분석 완료")

        # 4. 파싱 보완 (TICKERS 및 요약 추출)
        # TICKERS: ["AAPL", "TSLA"...] 형태를 찾음
        match = re.search(r'TICKERS:\s*\[(.*?)\]', full_text, re.IGNORECASE)
        if match:
            raw_tickers = match.group(1).replace('"', '').replace("'", "").split(',')
            tickers = [t.strip() for t in raw_tickers]
        else:
            tickers = []

        # 요약 부분 추출 (첫 번째 줄 또는 '요약:' 뒤의 텍스트)
        summary_match = re.search(r'요약:\s*(.*)', full_text)
        summary = summary_match.group(1).strip() if summary_match else full_text.split('\n')[0][:50]
        
        # 4. 데이터 저장 (기본값 설정으로 에러 방지)
        dashboard_data = {
            'date': datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),
            'indices': market_indices if market_indices else [], # 비어있어도 리스트 유지
            'tickers': tickers if tickers else [],
            'summary': summary if summary else "분석 결과 요약 중입니다.",
            'news_list': mixed_news[:5] if mixed_news else []
        }
        
        # 파일 저장 (이 위치가 중요합니다!)
        with open(REC_FILE, 'w', encoding='utf-8') as f:
            json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
        print(f"💾 Dashboard 데이터 저장 완료: {REC_FILE}")
   
        # 6. 전송
        report_msg = f"📅 *프리즘 마켓 인사이트 ({dashboard_data['date']})*\n\n{full_text}"
        send_telegram_message(report_msg)

    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    run_analysis()

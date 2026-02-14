import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
import json
import re
from datetime import datetime
import pytz

# 설정값
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODEL_NAME = 'gemini-2.0-flash' # 최신 모델 권장
REC_FILE = 'recommendations.json'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 3800: message = message[:3800] + "\n\n...(중략)"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except Exception as e: print(f"전송 오류: {e}")

def get_market_indices():
    """세계 주요 지수 및 거래 상태 수집"""
    indices = {
        "S&P 500": "^GSPC", "나스닥": "^IXIC", "코스피": "^KS11",
        "상해종합": "000001.SS", "닛케이225": "^N225", "유로스톡스": "^STOXX50E"  # ^FEZ 대신 수정
    }
    market_data = []
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                # 거래 상태 판별 (마지막 거래 데이터가 15분 이내면 초록불)
                last_time = hist.index[-1].to_pydatetime()
                now = datetime.now(pytz.timezone('UTC'))
                # yfinance 데이터는 UTC 기준이므로 현재 UTC와 비교
                is_open = (now - last_time.replace(tzinfo=pytz.UTC)).total_seconds() < 1200 
                
                market_data.append({"name": name, "change": round(change_pct, 2), "is_open": is_open})
        except: continue
    return market_data

def run_analysis():
    print("글로벌 인사이트 엔진 가동...")
    market_indices = get_market_indices()
    
    # 뉴스 수집 및 믹스
    kr_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
    us_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en")
    
    mixed_news = []
    for i in range(5):
        if i < len(kr_feed.entries): mixed_news.append(f"[국내] {kr_feed.entries[i].title}")
        if i < len(us_feed.entries): mixed_news.append(f"[글로벌] {us_feed.entries[i].title}")
    
    news_text = "\n".join(mixed_news)

    # Gemini 분석
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"""
    당신은 글로벌 헤지펀드 전략가입니다. 아래 제공된 [데이터]는 한국과 미국의 주요 경제 뉴스입니다.
    
    [데이터]:
    {news_text}

    [작성 규칙]:
    1. '핵심 분석:' 섹션에 오늘 시장의 핵심 흐름을 한 문장으로 요약할 것.
    2. 상승 기대 종목 3개를 추천할 것. 
       - **중요**: 뉴스 내용을 바탕으로 한국 시장(KOSPI/KOSDAQ)과 미국 시장(NYSE/NASDAQ) 종목을 적절히 섞어서 추천하세요.
       - 예: 1. 삼성전자(005930), 2. NVIDIA(NVDA)...
    3. 반드시 마지막 줄에 다음 형식을 포함하세요: TICKERS: ["티커1", "티커2", "티커3"]
       - 한국 종목은 6자리 숫자로, 미국 종목은 심볼로 작성하세요.

    한국어로 명확하고 간결하게 작성하세요.
    """
    
    try:
        response = model.generate_content(prompt)
        full_text = response.text
        match = re.search(r'TICKERS:\s*(\[.*?\])', full_text)
        tickers = json.loads(match.group(1)) if match else []

        dashboard_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'indices': market_indices,
            'tickers': tickers,
            'summary': full_text.split("핵심 분석:")[1].split("\n")[0].strip() if "핵심 분석:" in full_text else "시장 변동성에 주의가 필요한 시점입니다.",
            'news_list': mixed_news
        }
        
        with open(REC_FILE, 'w', encoding='utf-8') as f:
            json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
        
        send_telegram_message(f"📅 *{dashboard_data['date']} 리포트*\n\n{full_text}")
    except Exception as e:
        print(f"오류: {e}")

if __name__ == "__main__":
    run_analysis()

import os
import feedparser
import requests
import yfinance as yf
import json
import re
from datetime import datetime
import pytz

# 최신 google-genai 라이브러리 임포트 (충돌 방지 로직)
try:
    from google import genai
except ImportError:
    try:
        from google.genai import Client
    except ImportError:
        print("❌ google-genai 라이브러리가 설치되지 않았습니다. requirements.txt를 확인하세요.")

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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"전송 오류: {e}")

def get_market_indices():
    """세계 주요 지수 수집"""
    indices = {
        "S&P 500": "^GSPC", "나스닥": "^IXIC", "코스피": "^KS11",
        "상해종합": "000001.SS", "닛케이225": "^N225", "유로스톡스": "^STOXX50E"
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
                last_time = hist.index[-1].to_pydatetime()
                now = datetime.now(pytz.timezone('UTC'))
                is_open = (now - last_time.replace(tzinfo=pytz.UTC)).total_seconds() < 1200 
                market_data.append({"name": name, "change": round(change_pct, 2), "is_open": is_open})
        except: continue
    return market_data

def run_analysis():
    print("🚀 프리즘 인사이트 엔진 가동 (최신 GenAI 버전)...")
    
    # 1. 데이터 수집
    market_indices = get_market_indices()
    kr_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
    us_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en")
    
    mixed_news = []
    for i in range(5):
        if i < len(kr_feed.entries): mixed_news.append(f"[국내] {kr_feed.entries[i].title}")
        if i < len(us_feed.entries): mixed_news.append(f"[글로벌] {us_feed.entries[i].title}")
    news_text = "\n".join(mixed_news)

    # 2. 프롬프트 설정
    prompt = f"""
전략가로서 다음 뉴스를 분석해 시장 흐름을 한 문장으로 요약하고, 한국(.KS)과 미국 시장 종목을 섞어 3개를 추천하세요.
[데이터]: {news_text}
반드시 마지막 줄에 TICKERS: ["티커1", "티커2", "티커3"] 형식을 포함하세요.
"""

    # 3. AI 클라이언트 생성 및 분석 시도
    try:
        # 두 가지 임포트 방식 모두에 대응
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
        except:
            from google.genai import Client
            client = Client(api_key=GEMINI_API_KEY)

        model_candidates = ['gemini-2.0-flash', 'gemini-1.5-flash']
        full_text = ""

        for model_id in model_candidates:
            try:
                print(f"[{model_id}] 분석 시도 중...")
                response = client.models.generate_content(model=model_id, contents=prompt)
                full_text = response.text
                print(f"✅ [{model_id}] 분석 성공!")
                break
            except Exception as e:
                print(f"⚠️ [{model_id}] 실패: {e}")
                continue

        if not full_text:
            print("❌ 모든 모델 호출 실패")
            return

        # 4. 결과 파싱 및 저장
        match = re.search(r'TICKERS:\s*(\[.*?\])', full_text)
        tickers = json.loads(match.group(1)) if match else []
        summary = full_text.split("\n")[0].replace("핵심 분석:", "").strip()

        dashboard_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'indices': market_indices,
            'tickers': tickers,
            'summary': summary,
            'news_list': mixed_news
        }
        
        with open(REC_FILE, 'w', encoding='utf-8') as f:
            json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
        
        # 5. 텔레그램 전송
        report_msg = f"📅 *{dashboard_data['date']} 리포트*\n\n{full_text}"
        send_telegram_message(report_msg)
        print("🎉 모든 작업이 완료되었습니다!")

    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    run_analysis()

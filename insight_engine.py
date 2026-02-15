import os
import feedparser
from google import genai # 최신 라이브러리 방식
import requests
import yfinance as yf
import json
import re
from datetime import datetime
import pytz

# [설정값]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
REC_FILE = 'recommendations.json'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 3800: message = message[:3800] + "\n\n...(중략)"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except Exception as e: print(f"전송 오류: {e}")

def get_market_indices():
    indices = {"S&P 500": "^GSPC", "나스닥": "^IXIC", "코스피": "^KS11", "상해종합": "000001.SS", "닛케이225": "^N225", "유로스톡스": "^STOXX50E"}
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
    print("🚀 프리즘 인사이트 엔진 (New GenAI) 가동...")
    market_indices = get_market_indices()
    
    kr_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
    us_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en")
    mixed_news = [f"[국내] {e.title}" for e in kr_feed.entries[:5]] + [f"[글로벌] {e.title}" for e in us_feed.entries[:5]]
    news_text = "\n".join(mixed_news)

    prompt = f"전략가로서 뉴스 분석 후 시장요약(한문장)과 한/미 추천종목 3개를 뽑아주세요.\n[데이터]:{news_text}\n규칙: 마지막줄에 TICKERS: [\"티커1.KS\", \"티커2\"] 형식 필수."

    # 3. 최신 모델 호출 방식 (google-genai)
    client = genai.Client(api_key=GEMINI_API_KEY)
    model_candidates = ['gemini-2.0-flash', 'gemini-1.5-flash']
    full_text = ""

    for model_id in model_candidates:
        try:
            print(f"[{model_id}] 시도 중...")
            response = client.models.generate_content(model=model_id, contents=prompt)
            full_text = response.text
            print(f"✅ [{model_id}] 성공!")
            break
        except Exception as e:
            print(f"⚠️ [{model_id}] 실패: {e}")
            continue

    if not full_text: return

    # 데이터 저장 및 전송
    match = re.search(r'TICKERS:\s*(\[.*?\])', full_text)
    tickers = json.loads(match.group(1)) if match else []
    summary = full_text.split("\n")[0] # 첫 줄을 요약으로 간주

    dashboard_data = {'date': datetime.now().strftime('%Y-%m-%d %H:%M'), 'indices': market_indices, 'tickers': tickers, 'summary': summary, 'news_list': mixed_news}
    with open(REC_FILE, 'w', encoding='utf-8') as f: json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
    
    send_telegram_message(f"📅 *{dashboard_data['date']} 리포트*\n\n{full_text}")
    print("🎉 완료!")

if __name__ == "__main__":
    run_analysis()

import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
import json
from datetime import datetime, timedelta

# 1. 설정값
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODEL_NAME = 'gemini-2.5-flash'
REC_FILE = 'recommendations.json'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e: print(f"전송 오류: {e}")

def get_performance_report():
    """어제 추천했던 종목들의 실제 수익률 검증"""
    if not os.path.exists(REC_FILE):
        return "*[정합성 검증]*: 이전 기록이 없습니다.\n\n"
    
    try:
        with open(REC_FILE, 'r') as f:
            data = json.load(f)
        
        last_date = data.get('date', '알 수 없음')
        last_recs = data.get('tickers', []) # 예: ["NVDA", "AAPL", "005930.KS"]
        
        report = f"🎯 *[{last_date}] 추천 종목 성적표*\n"
        for t in last_recs:
            stock = yf.Ticker(t)
            # 어제 종가 대비 오늘 현재가 비교
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                emoji = "✅" if change > 0 else "❌"
                report += f"- {t}: {change:+.2f}% {emoji}\n"
        return report + "\n"
    except Exception as e:
        return f"*[정합성 검증 오류]*: {e}\n\n"

def run_analysis():
    print("분석 및 기록 시스템 가동...")
    
    # 1. 어제 성적표 생성
    accuracy_report = get_performance_report()
    
    # 2. 뉴스 수집 (기존 동일)
    kr_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    us_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"
    news_text = "\n".join([e.title for e in feedparser.parse(kr_url).entries[:10] + feedparser.parse(us_url).entries[:10]])

    # 3. Gemini 분석 (JSON 출력을 유도하여 티커만 추출)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    당신은 전문 투자 전략가입니다. 아래 뉴스를 분석하여 리포트를 작성하고, 
    마지막에 오늘 가장 큰 상승이 기대되는 종목 3개의 티커만 JSON 형식으로 한 줄로 적어주세요.
    예: TICKERS: ["NVDA", "005930.KS", "TSLA"]

    뉴스: {news_text}
    """
    
    response = model.generate_content(prompt)
    full_text = response.text
    
    # 4. 티커 추출 및 저장
    try:
        # 텍스트에서 TICKERS: [...] 부분만 찾아냅니다.
        import re
        match = re.search(r'TICKERS:\s*(\[.*?\])', full_text)
        if match:
            tickers = json.loads(match.group(1))
            with open(REC_FILE, 'w') as f:
                json.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'tickers': tickers}, f)
            # 리포트 본문에서 JSON 태그 부분 제거
            full_text = full_text.replace(match.group(0), "").strip()
    except:
        print("티커 추출 실패")

    # 5. 전송
    final_msg = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 글로벌 리포트*\n\n{accuracy_report}{full_text}"
    send_telegram_message(final_msg)

if __name__ == "__main__":
    run_analysis()

import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
from datetime import datetime, timedelta

# 1. 설정값 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODEL_NAME = 'gemini-2.5-flash'  # 프리즘님 계정에서 확인된 최신 모델

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"텔레그램 전송 오류: {e}")

def get_combined_news():
    """한국 및 미국 경제 뉴스 수집"""
    print("글로벌 뉴스 수집 중...")
    kr_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    us_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"
    
    kr_feed = feedparser.parse(kr_url)
    us_feed = feedparser.parse(us_url)
    
    combined = []
    for entry in kr_feed.entries[:7]:
        combined.append(f"[KR] {entry.title}")
    for entry in us_feed.entries[:8]:
        combined.append(f"[US] {entry.title}")
    
    return "\n".join(combined)

def check_yesterday_performance():
    """
    (개념 구현) 어제 추천 종목의 수익률 확인.
    실제 DB 연동 전이므로, 예시로 'NVDA'와 'AAPL'의 전일 대비 등락을 확인합니다.
    """
    print("전일 주요 종목 정합성 확인 중...")
    tickers = ["NVDA", "AAPL", "TSLA"] # 예시 종목
    perf_report = "*[어제 주요 종목 현황]*\n"
    
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            history = stock.history(period="2d")
            if len(history) >= 2:
                prev_close = history['Close'].iloc[-2]
                curr_close = history['Close'].iloc[-1]
                change = ((curr_close - prev_close) / prev_close) * 100
                emoji = "📈" if change > 0 else "📉"
                perf_report += f"- {t}: {change:+.2f}% {emoji}\n"
        except:
            continue
    return perf_report + "\n"

def run_analysis():
    print("시스템 가동...")
    
    # 1. 전일 성적표 확인 (정합성)
    accuracy_data = check_yesterday_performance()
    
    # 2. 뉴스 수집
    news_text = get_combined_news()
    if not news_text:
        print("뉴스 수집 실패")
        return

    # 3. Gemini 분석
    print(f"Gemini({MODEL_NAME}) 분석 시작...")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    당신은 월스트리트의 수석 전략가입니다. 아래의 한/미 핵심 뉴스 15개를 분석하세요.
    
    {news_text}
    
    [보고서 양식]
    1. 글로벌 마켓 핵심 요약 (3문장)
    2. 유망 종목 3선 (한국/미국 혼합, 티커 필수)
    3. 각 종목별 선정 이유 및 오늘 예상 시나리오
    
    반드시 한국어로 작성하고 중요 지표는 볼드(**) 처리하세요.
    """
    
    try:
        response = model.generate_content(prompt)
        report_content = response.text
    except Exception as e:
        print(f"분석 오류: {e}")
        return

    # 4. 최종 메시지 조합 및 전송
    final_report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 글로벌 경제 인사이트*\n\n"
    final_report += accuracy_data
    final_report += report_content
    
    send_telegram_message(final_report)
    print("모든 작업이 완료되었습니다!")

if __name__ == "__main__":
    run_analysis()

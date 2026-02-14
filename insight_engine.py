import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
from datetime import datetime

# 1. 설정값 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODEL_NAME = 'gemini-2.5-flash' 

def send_telegram_message(message):
    """텔레그램 메시지 전송 (Markdown 지원)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"텔레그램 전송 오류: {e}")

def get_combined_news():
    """글로벌 및 국내 핵심 뉴스 수집"""
    print("글로벌 뉴스 수집 중...")
    kr_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    us_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"
    
    kr_feed = feedparser.parse(kr_url)
    us_feed = feedparser.parse(us_url)
    
    combined = []
    # 한국 뉴스 상위 10개, 미국 뉴스 상위 10개 수집
    for entry in kr_feed.entries[:10]:
        combined.append(f"[KR] {entry.title}")
    for entry in us_feed.entries[:10]:
        combined.append(f"[US] {entry.title}")
    
    return "\n".join(combined)

def get_market_performance():
    """실시간 시장 주요 지표 및 전일 등락 자동 확인"""
    print("시장 지표 데이터 갱신 중...")
    # 주요 지수 및 관심 종목 (매일 최신가 반영)
    tickers = ["^IXIC", "^GSPC", "NVDA", "AAPL", "TSLA"] # 나스닥, S&P500, 엔비디아, 애플, 테슬라
    perf_report = "*[실시간 전일 대비 시장 현황]*\n"
    
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            history = stock.history(period="2d")
            if len(history) >= 2:
                prev_close = history['Close'].iloc[-2]
                curr_close = history['Close'].iloc[-1]
                change = ((curr_close - prev_close) / prev_close) * 100
                emoji = "📈" if change > 0 else "📉"
                name = "나스닥" if t=="^IXIC" else "S&P500" if t=="^GSPC" else t
                perf_report += f"- {name}: {change:+.2f}% {emoji}\n"
        except:
            continue
    return perf_report + "\n"

def run_analysis():
    print("시스템 가동...")
    
    # 1. 뉴스 및 시장 데이터 준비
    market_data = get_market_performance()
    news_text = get_combined_news()
    
    if not news_text:
        print("뉴스 수집 실패")
        return

    # 2. Gemini 분석
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    당신은 전 세계 자산 흐름을 꿰뚫어 보는 글로벌 투자 전략가입니다. 
    아래 뉴스 리스트를 바탕으로 오늘 아침의 핵심 리포트를 작성하세요.
    
    [분석 데이터]:
    {news_text}
    
    [리포트 작성 가이드라인]:
    1. **글로벌 마켓 핵심 요약**: 현재 시장의 흐름을 정확히 3줄로 요약하세요.
    2. **오늘의 영향력 TOP 10 뉴스**: 뉴스 중 한국과 글로벌 경제에 파급력이 가장 큰 이슈 10개를 선정하여 리스트 형태로 보여주세요.
    3. **상승 예측 종목 3선**: 수집된 뉴스를 근거로, 오늘 하루 '가장 큰 폭의 상승'이 기대되는 종목 3개를 순위별로 선정하세요. 
       - 형식: 순위. 종목명(티커) - 기대 등락폭(%) 및 선정 이유
    
    반드시 한국어로 작성하고, 가독성을 위해 볼드(**)와 기호를 적절히 사용하세요.
    """
    
    try:
        response = model.generate_content(prompt)
        report_content = response.text
    except Exception as e:
        print(f"분석 오류: {e}")
        return

    # 3. 최종 메시지 전송
    final_report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 글로벌 경제 인사이트*\n\n"
    final_report += market_data
    final_report += report_content
    
    send_telegram_message(final_report)
    print("전체 공정 완료 및 텔레그램 전송 성공!")

if __name__ == "__main__":
    run_analysis()

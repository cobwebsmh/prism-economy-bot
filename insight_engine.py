import os
import feedparser
import google.generativeai as genai
import requests
from datetime import datetime

# 설정값 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload)
        print(f"텔레그램 전송 결과: {res.status_code}")
    except Exception as e:
        print(f"텔레그램 전송 중 오류: {e}")

def run_analysis():
    print("시스템 가동...")
    
    # 1. 뉴스 수집
    news_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(news_url)
    
    if not feed.entries:
        print("뉴스 수집 실패")
        return

    news_text = "\n".join([f"- {entry.title}" for entry in feed.entries[:10]])
    print(f"뉴스 {len(feed.entries[:10])}개 수집 완료")

    # 2. Gemini 분석 (모델 이름 유연하게 설정)
    print("Gemini 분석 중...")
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 여러 모델 이름을 시도합니다.
    model_names = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    model = None
    response = None

    for name in model_names:
        try:
            print(f"{name} 모델로 시도 중...")
            model = genai.GenerativeModel(name)
            prompt = f"경제 전문가로서 다음 뉴스들을 요약하고 주가 상승이 기대되는 종목 3가지를 추천하세요:\n{news_text}"
            response = model.generate_content(prompt)
            if response:
                break
        except Exception as e:
            print(f"{name} 실패: {e}")
            continue

    if not response:
        print("모든 AI 모델 호출에 실패했습니다.")
        return

    # 3. 결과 전송
    report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 경제 리포트*\n\n{response.text}"
    send_telegram_message(report)
    print("전체 공정 완료!")

if __name__ == "__main__":
    run_analysis()

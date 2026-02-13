import os
import feedparser
import google.generativeai as genai
import requests  # 텔레그램 전송을 위해 추가
from datetime import datetime

# 설정값 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """텔레그램으로 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def run_analysis():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    print("뉴스 수집 및 분석 중...")
    url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNR3lm荤XpUaU1pSklSREl6S0FBU0Fnback?hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url)
    news_text = "\n".join([f"- {entry.title}" for entry in feed.entries[:10]])

    prompt = f"당신은 경제 전문가입니다. 다음 뉴스를 요약하고 유망 종목 3개를 추천하세요:\n{news_text}"
    response = model.generate_content(prompt)
    
    report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 경제 리포트*\n\n{response.text}"
    
    # 콘솔 출력 및 텔레그램 전송
    print(report)
    send_telegram_message(report)
    print("텔레그램 전송 완료!")

if __name__ == "__main__":
    run_analysis()

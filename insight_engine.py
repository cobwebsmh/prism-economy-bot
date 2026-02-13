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
    """텔레그램으로 메시지 전송"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # 텔레그램 메시지 글자수 제한(4096자)을 고려하여 자르기
        if len(message) > 4000:
            message = message[:4000] + "..."
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"텔레그램 전송 중 오류 발생: {e}")

def run_analysis():
    if not GEMINI_API_KEY:
        print("에러: GEMINI_API_KEY가 설정되지 않았습니다.")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    
    # 가장 안정적인 'gemini-pro' 모델로 고정합니다.
    model = genai.GenerativeModel('gemini-pro')

    print("뉴스 수집 중...")
    url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNR3lm荤XpUaU1pSklSREl6S0FBU0Fnback?hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url)
    
    if not feed.entries:
        print("뉴스를 가져오지 못했습니다.")
        return
        
    news_text = "\n".join([f"- {entry.title}" for entry in feed.entries[:10]])

    print("Gemini 분석 중...")
    prompt = f"""
    당신은 경제 전문가입니다. 다음 뉴스를 요약하고 유망 종목 3개를 추천하세요:
    
    {news_text}
    
    반드시 다음 형식을 지켜주세요:
    1. 오늘의 뉴스 요약
    2. 추천 종목 3가지 (종목명/티커/이유)
    """
    
    try:
        response = model.generate_content(prompt)
        report_content = response.text
    except Exception as e:
        report_content = f"AI 분석 중 오류가 발생했습니다: {e}"
    
    report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 경제 리포트*\n\n{report_content}"
    
    print(report)
    send_telegram_message(report)
    print("작업 완료!")

if __name__ == "__main__":
    run_analysis()

import os
import feedparser
import yfinance as yf
import google.generativeai as genai
from datetime import datetime

# 시스템(GitHub Secrets)에서 API 키를 가져옵니다.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def run_analysis():
    # API 키가 없는 경우 에러를 출력하도록 설정
    if not GEMINI_API_KEY:
        print("에러: GEMINI_API_KEY를 찾을 수 없습니다. Settings > Secrets를 확인하세요.")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # 1. 뉴스 수집
    print("뉴스 수집 중...")
    url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNR3lm荤XpUaU1pSklSREl6S0FBU0Fnback?hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url)
    news_text = "\n".join([f"- {entry.title}" for entry in feed.entries[:10]])

    # 2. Gemini 분석
    print("Gemini 분석 중...")
    prompt = f"당신은 경제 전문가입니다. 다음 뉴스를 요약하고 유망 종목 3개를 추천하세요:\n{news_text}"
    response = model.generate_content(prompt)
    
    # 3. 결과 출력
    print(f"\n=== {datetime.now().strftime('%Y-%m-%d')} 리포트 ===\n")
    print(response.text)

if __name__ == "__main__":
    run_analysis()

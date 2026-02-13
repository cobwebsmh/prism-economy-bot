import os
import feedparser
import yfinance as yf
import google.generativeai as genai
from datetime import datetime

# GitHub Secrets에서 키 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def run_analysis():
    if not GEMINI_API_KEY:
        print("에러: GEMINI_API_KEY를 찾을 수 없습니다.")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    
    # 모델명을 가장 안정적인 것으로 변경했습니다.
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest') 
        # 만약 위 이름도 안되면 'gemini-pro'로 바꿔보세요.
    except:
        model = genai.GenerativeModel('gemini-pro')

    # 1. 뉴스 수집
    print("뉴스 수집 중...")
    url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNR3lm荤XpUaU1pSklSREl6S0FBU0Fnback?hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url)
    
    if not feed.entries:
        print("뉴스를 가져오지 못했습니다.")
        return
        
    news_text = "\n".join([f"- {entry.title}" for entry in feed.entries[:10]])

    # 2. Gemini 분석
    print("Gemini 분석 중...")
    prompt = f"""
    당신은 글로벌 투자 전략가입니다. 다음 뉴스를 보고 보고서를 작성하세요.
    
    [오늘의 뉴스]:
    {news_text}
    
    [작성 지침]:
    1. 10대 뉴스 핵심 요약 (전문가적 시점)
    2. 주가 상승이 기대되는 종목 3가지 (한국/미국 포함, 티커 명시)
    3. 각 종목별 상승 예측 근거와 예상 등락폭
    """
    
    response = model.generate_content(prompt)
    
    # 3. 결과 출력
    print(f"\n=== {datetime.now().strftime('%Y-%m-%d')} 리포트 ===\n")
    print(response.text)

if __name__ == "__main__":
    run_analysis()

import os
import feedparser
import yfinance as yf
import google.generativeai as genai
from datetime import datetime

# --- [중요: GitHub Secrets에서 키를 불러오는 방식] ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

class PrismEconomicApp:
    def __init__(self):
        # 2026년 현재 가장 성능이 좋은 flash 모델 사용
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def get_news(self):
        """구글 경제 뉴스 수집"""
        url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNR3lm荤XpUaU1pSklSREl6S0FBU0Fnback?hl=ko&gl=KR&ceid=KR%3Ako"
        feed = feedparser.parse(url)
        titles = [f"{i+1}. {entry.title}" for i, entry in enumerate(feed.entries[:10])]
        return "\n".join(titles)

    def analyze(self, news_text):
        """Gemini 전문가 분석"""
        prompt = f"""
        당신은 글로벌 투자 전략가입니다. 다음 뉴스를 보고 보고서를 작성하세요.
        
        [오늘의 뉴스]:
        {news_text}
        
        [작성 지침]:
        1. 10대 뉴스 핵심 요약 (전문가적 시점)
        2. 주가 상승이 기대되는 종목 3가지 (한국/미국 포함, 티커 명시)
        3. 각 종목별 상승 예측 근거와 예상 등락폭
        """
        response = self.model.generate_content(prompt)
        return response.text

    def run(self):
        print(f"--- {datetime.now().strftime('%Y-%m-%d')} 경제 분석 시작 ---")
        news = self.get_news()
        report = self.analyze(news)
        print(report)
        print("--- 분석 완료 ---")

if __name__ == "__main__":
    app = PrismEconomicApp()
    app.run()

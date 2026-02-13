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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload)
        print(f"텔레그램 전송 결과: {res.status_code}")
    except Exception as e:
        print(f"텔레그램 전송 중 오류: {e}")

def run_analysis():
    print("시스템 가동...")
    
    # 1. 뉴스 수집 (주소 변경 및 예비 주소 설정)
    print("뉴스 수집 중...")
    # 더 안정적인 구글 뉴스 '비즈니스' 섹션 한국어 주소입니다.
    news_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(news_url)
    
    # 만약 수집 실패 시 예비 주소로 시도
    if not feed.entries:
        print("기본 뉴스 수집 실패, 예비 주소로 시도합니다.")
        news_url = "https://www.yonhapnewstv.co.kr/browse/feed/" # 연합뉴스TV RSS
        feed = feedparser.parse(news_url)

    if not feed.entries:
        print("모든 뉴스 수집 실패. 실행을 중단합니다.")
        return

    # 상위 10개 추출
    news_text = "\n".join([f"- {entry.title}" for entry in feed.entries[:10]])
    print(f"수집된 뉴스 개수: {len(feed.entries[:10])}개")

    # 2. Gemini 분석
    print("Gemini 분석 중...")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    
    prompt = f"당신은 경제 전문가입니다. 다음 뉴스들을 요약하고 주가 상승이 기대되는 종목 3가지를 추천하세요:\n{news_text}"
    
    try:
        response = model.generate_content(prompt)
        report_content = response.text
    except Exception as e:
        print(f"AI 분석 중 오류: {e}")
        return

    # 3. 결과 전송
    report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 경제 리포트*\n\n{report_content}"
    send_telegram_message(report)
    print("전체 공정 완료!")

if __name__ == "__main__":
    run_analysis()

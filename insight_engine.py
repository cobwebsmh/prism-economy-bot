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
    print(f"뉴스 10개 수집 완료")

    # 2. Gemini 분석 (확인된 모델명 적용)
    print("Gemini 분석 중...")
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 프리즘님의 로그에서 확인된 가장 최신 모델명입니다.
    target_model = 'gemini-2.5-flash' 
    
    try:
        model = genai.GenerativeModel(target_model)
        prompt = f"당신은 전문 투자 분석가입니다. 다음 뉴스들의 핵심을 요약하고, 관련하여 주가 상승이 기대되는 종목 3가지를 추천하세요. 종목명, 티커, 추천 사유를 명확히 작성해 주세요:\n{news_text}"
        
        response = model.generate_content(prompt)
        
        if response.text:
            report_content = response.text
            print(f"AI({target_model}) 분석 성공!")
        else:
            print("AI 응답 내용이 비어있습니다.")
            return
            
    except Exception as e:
        print(f"최종 분석 실패: {e}")
        return

    # 3. 결과 전송
    report = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 경제 리포트*\n\n{report_content}"
    send_telegram_message(report)
    print("전체 공정 완료!")

if __name__ == "__main__":
    run_analysis()

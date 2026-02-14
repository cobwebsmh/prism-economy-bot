import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
import json
import re
from datetime import datetime

# 설정값
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODEL_NAME = 'gemini-2.5-flash'
REC_FILE = 'recommendations.json'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 3800:
        message = message[:3800] + "\n\n...(중략)"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"전송 오류: {e}")

def get_performance_report():
    if not os.path.exists(REC_FILE):
        return "🆕 *[정합성 검증]*: 첫 기록을 시작합니다.\n\n"
    try:
        with open(REC_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        last_date = data.get('date', '알 수 없음')
        last_recs = data.get('tickers', [])
        report = f"🎯 *[{last_date}] 추천 종목 성적표*\n"
        for t in last_recs:
            try:
                stock = yf.Ticker(t)
                hist = stock.history(period="2d")
                if len(hist) >= 2:
                    change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                    emoji = "✅" if change > 0 else "❌"
                    report += f"- {t}: {change:+.2f}% {emoji}\n"
            except:
                report += f"- {t}: 데이터 확인 불가\n"
        return report + "\n---\n"
    except: return ""

def run_analysis():
    print("글로벌 인사이트 엔진 가동...")
    accuracy_report = get_performance_report()
    
    # 1. 뉴스 수집
    kr_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    us_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"
    news_combined = [e.title for e in feedparser.parse(kr_url).entries[:10]] + \
                    [e.title for e in feedparser.parse(us_url).entries[:10]]
    news_text = "\n".join(news_combined)

    # 2. Gemini 분석 (실제 호출 부분이 꼭 필요합니다!)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    당신은 글로벌 헤지펀드 전략가입니다. 아래 뉴스를 기반으로 리포트를 작성하세요.
    [데이터]: {news_text}
    [작성 규칙]:
    1. 핵심 트렌드 요약 (주요 시장 트렌드 분석 이라는 제목을 포함할 것)
    2. 상승 기대 종목 3개
    3. 마지막 줄에 형식 준수: TICKERS: ["티커1", "티커2", "티커3"]
    """
    
    try:
        # 이 부분이 핵심! AI에게 답변을 받아옵니다.
        response = model.generate_content(prompt)
        full_text = response.text

        # 3. 데이터 저장 (프리즘님이 작성하신 로직 보완)
        match = re.search(r'TICKERS:\s*(\[.*?\])', full_text)
        if match:
            tickers = json.loads(match.group(1))
            
            # 요약 내용 추출 (트렌드 분석 전까지)
            summary_part = full_text.split("주요 시장 트렌드 분석")[0].strip() if "주요 시장 트렌드 분석" in full_text else "오늘의 분석 리포트입니다."

            dashboard_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'tickers': tickers,
                'summary': summary_part.replace("#", "").strip(), 
                'news_list': news_combined[:10] 
            }
            
            with open(REC_FILE, 'w', encoding='utf-8') as f:
                json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
            
            # 메시지 전송용 텍스트에서 데이터 태그 제거
            clean_text = full_text.replace(match.group(0), "").strip()
        else:
            clean_text = full_text

        # 4. 텔레그램 전송
        final_msg = f"📅 *{datetime.now().strftime('%Y-%m-%d')} 리포트*\n\n{accuracy_report}{clean_text}"
        send_telegram_message(final_msg)
        print("전체 공정 성공!")

    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    run_analysis()

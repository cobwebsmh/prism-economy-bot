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
    """글자 수 제한을 고려하여 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # 안전하게 3800자에서 자름
    if len(message) > 3800:
        message = message[:3800] + "\n\n...(내용이 너무 길어 중략되었습니다)"
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"전송 오류: {e}")

def get_performance_report():
    if not os.path.exists(REC_FILE):
        return "🆕 *[정합성 검증]*: 첫 기록을 시작합니다.\n\n"
    
    try:
        with open(REC_FILE, 'r') as f:
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
    except:
        return ""

def run_analysis():
    print("글로벌 인사이트 엔진 가동...")
    accuracy_report = get_performance_report()
    
    # 뉴스 수집
    kr_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    us_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"
    news_combined = [e.title for e in feedparser.parse(kr_url).entries[:10]] + \
                    [e.title for e in feedparser.parse(us_url).entries[:10]]
    news_text = "\n".join(news_combined)

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    # 프롬프트를 더 명확하게 수정
    prompt = f"""
    당신은 글로벌 헤지펀드 전략가입니다. 아래 뉴스를 기반으로 리포트를 작성하세요.
    
    [데이터]:
    {news_text}

    [작성 규칙]:
    1. 핵심 트렌드 3가지를 요약할 것.
    2. 오늘 가장 큰 상승이 기대되는 종목 3개를 '순위. 종목명(티커)' 형식으로 추천할 것.
    3. 반드시 마지막 줄에 다음 형식을 포함할 것: TICKERS: ["티커1", "티커2", "티커3"]

    한국어로 명확하고 간결하게 작성하세요.
    """

    # 4. 티커 추출 및 뉴스 데이터와 함께 저장
    try:
        import re
        match = re.search(r'TICKERS:\s*(\[.*?\])', response.text)
        if match:
            tickers = json.loads(match.group(1))
            
            # 대시보드용 데이터 구조 생성
            dashboard_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'tickers': tickers,
                'summary': response.text.split("주요 시장 트렌드 분석:")[0].replace("##", "").strip(), # 요약 부분만 추출
                'news_list': news_combined[:10] # 수집했던 뉴스 10개 포함
            }
            
            with open(REC_FILE, 'w', encoding='utf-8') as f:
                json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"데이터 저장 실패: {e}")

if __name__ == "__main__":
    run_analysis()

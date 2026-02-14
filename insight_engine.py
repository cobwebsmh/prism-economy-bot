import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
import json
import re
from datetime import datetime
import pytz

# [설정값]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
REC_FILE = 'recommendations.json'

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 3800:
        message = message[:3800] + "\n\n...(중략)"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"전송 오류: {e}")

def get_market_indices():
    """세계 주요 지수 및 거래 상태 수집 (유럽 지수 보정)"""
    indices = {
        "S&P 500": "^GSPC", 
        "나스닥": "^IXIC", 
        "코스피": "^KS11",
        "상해종합": "000001.SS", 
        "닛케이225": "^N225", 
        "유로스톡스": "^STOXX50E" # 기존 FEZ 대신 안정적인 티커로 변경
    }
    market_data = []
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                # 거래 상태 판별 (마지막 데이터가 20분 이내면 실시간으로 간주)
                last_time = hist.index[-1].to_pydatetime()
                now = datetime.now(pytz.timezone('UTC'))
                is_open = (now - last_time.replace(tzinfo=pytz.UTC)).total_seconds() < 1200 
                
                market_data.append({
                    "name": name, 
                    "change": round(change_pct, 2), 
                    "is_open": is_open
                })
        except Exception as e:
            print(f"{name} 데이터 수집 실패: {e}")
            continue
    return market_data

def run_analysis():
    print("🚀 프리즘 인사이트 엔진 가동...")
    
    # 1. 지수 및 뉴스 데이터 준비
    market_indices = get_market_indices()
    
    kr_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
    us_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en")
    
    mixed_news = []
    for i in range(5):
        if i < len(kr_feed.entries): mixed_news.append(f"[국내] {kr_feed.entries[i].title}")
        if i < len(us_feed.entries): mixed_news.append(f"[글로벌] {us_feed.entries[i].title}")
    
    news_text = "\n".join(mixed_news)

    # 2. AI 분석 프롬프트 (한/미 종목 믹스 지시)
    prompt = f"""
당신은 글로벌 헤지펀드 전략가입니다. 아래 제공된 [데이터]는 한국과 미국의 경제 뉴스입니다.
[데이터]:
{news_text}

[작성 규칙]:
1. '핵심 분석:' 섹션에 오늘 시장의 핵심 흐름을 한 문장으로 요약할 것.
2. 상승 기대 종목 3개를 한국(KOSPI/KOSDAQ)과 미국(NYSE/NASDAQ) 시장에서 골고루 섞어 추천할 것.
   - 예: 삼성전자(005930.KS), NVIDIA(NVDA)
3. 반드시 마지막 줄에 다음 형식을 포함하세요: TICKERS: ["티커1", "티커2", "티커3"]
   - 한국 종목은 반드시 '005930.KS' 처럼 시장 구분자를 붙이고, 미국은 심볼만 쓰세요.
"""

    # 3. 모델 자동 전환 (Fallback) 로직
    genai.configure(api_key=GEMINI_API_KEY)
    model_candidates = ['gemini-2.0-flash', 'gemini-1.5-flash']
    full_text = ""
    
    for model_name in model_candidates:
        try:
            print(f"[{model_name}] 분석 시도 중...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            full_text = response.text
            print(f"✅ [{model_name}] 분석 성공!")
            break 
        except Exception as e:
            print(f"⚠️ [{model_name}] 실패: {e}")
            continue

    if not full_text:
        print("❌ 모든 AI 모델 호출에 실패했습니다.")
        return

    # 4. 데이터 파싱 및 저장
    try:
        match = re.search(r'TICKERS:\s*(\[.*?\])', full_text)
        tickers = json.loads(match.group(1)) if match else []
        
        # 핵심 분석 요약 추출
        summary_part = "시장 변동성에 주의가 필요한 시점입니다."
        if "핵심 분석:" in full_text:
            summary_part = full_text.split("핵심 분석:")[1].split("\n")[0].strip()

        dashboard_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'indices': market_indices,
            'tickers': tickers,
            'summary': summary_part,
            'news_list': mixed_news
        }
        
        with open(REC_FILE, 'w', encoding='utf-8') as f:
            json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
        
        # 5. 텔레그램 리포트 발송
        clean_text = full_text.replace(match.group(0), "").strip() if match else full_text
        final_msg = f"📅 *{dashboard_data['date']} 리포트*\n\n{clean_text}"
        send_telegram_message(final_msg)
        print("🎉 전체 공정 완료!")

    except Exception as e:
        print(f"데이터 처리 오류: {e}")

if __name__ == "__main__":
    run_analysis()

import os
import feedparser
import requests
import yfinance as yf
import json
from datetime import datetime
import pytz
from google import genai

# [설정]
REC_FILE = 'recommendations.json'
HISTORY_FILE = 'history.json'

def get_market_data():
    """주요 시장 지수 데이터 수집"""
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC"}
    result = {}
    now_utc = datetime.now(pytz.utc)
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty and len(hist) >= 2:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((current - prev) / prev) * 100
                if name in ["KOSPI", "KOSDAQ"]:
                    kst = now_utc.astimezone(pytz.timezone('Asia/Seoul'))
                    is_open = kst.weekday() < 5 and 9 <= kst.hour < 16
                else:
                    est = now_utc.astimezone(pytz.timezone('US/Eastern'))
                    is_open = est.weekday() < 5 and 9 <= est.hour < 17
                result[name] = {"price": round(current, 2), "change": round(change, 2), "status": "🟢" if is_open else "⚪"}
        except: continue
    return result

def verify_past():
    """어제 추천 종목의 오늘 수익률 확인"""
    ticker_map = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "NAVER": "035420.KS", "카카오": "035720.KS", "현대차": "005380.KS"}
    try:
        if not os.path.exists(REC_FILE): return []
        with open(REC_FILE, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
            past_tickers = old_data.get('tickers', [])
            results = []
            for t in past_tickers:
                clean_t = ticker_map.get(t, t)
                if '(' in clean_t: clean_t = clean_t.split('(')[-1].replace(')', '')
                if clean_t.isdigit() and len(clean_t) == 6: clean_t += ".KS"
                try:
                    s = yf.Ticker(clean_t)
                    h = s.history(period="2d")
                    if not h.empty and len(h) >= 2:
                        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                        results.append({"ticker": t.split('(')[0], "change": round(c, 2)})
                except: continue
            return results
    except: return []

def fetch_global_news():
    """글로벌 경제 뉴스 수집 및 특수문자 정제"""
    feeds = [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US"
    ]
    news_list = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:5]:
                # JSON 파싱 에러 방지를 위해 따옴표 및 특수문자 제거
                clean_title = entry.title.replace('"', "'").replace('\\', '')
                news_list.append({"title": clean_title, "link": entry.link})
        except: continue
    return news_list

# --- 메인 실행 로직 ---
try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    market_info = get_market_data()
    past_results = verify_past()
    news_data = fetch_global_news()

    # AI 프롬프트 - 뉴스 링크 보존을 위해 더 엄격한 구조 요청
    prompt = f"""
    당신은 글로벌 금융 분석가입니다. 다음 데이터를 분석하여 투자 리포트를 JSON으로 작성하세요.
    
    1. 원천 뉴스 데이터: {news_data}
    2. 과거 종목 성적: {past_results}

    [조건]
    - news_headlines 리스트에 위에서 제공한 뉴스 데이터의 제목과 링크를 최소 5개 이상 반드시 포함하세요.
    - tickers에는 오늘의 추천 종목 3개를 넣으세요.
    - 반드시 아래의 JSON 형식으로만 응답하고, 다른 텍스트는 포함하지 마세요.

    {{
      "summary": "시장 상황에 대한 3문장 요약",
      "news_headlines": [
        {{"title": "뉴스 제목", "link": "뉴스 링크"}}
      ],
      "tickers": ["종목1", "종목2", "종목3"],
      "reason": "추천 사유 및 전략"
    }}
    """

    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    json_text = response.text.strip().replace('```json', '').replace('```', '')
    ai_data = json.loads(json_text)

    # 최종 데이터 구성
    final_data = {
        "date": datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M'),
        "market_info": market_info,
        "past_results": past_results,
        **ai_data
    }

    # 현재 리포트 저장 (recommendations.json)
    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    # 누적 기록 저장 (history.json)
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except: history = []
    
    # 중복 기록 방지를 위해 날짜가 다른 경우만 추가하거나 마지막 기록 업데이트
    history.append({
        "date": final_data["date"],
        "performance": past_results,
        "predictions": ai_data["tickers"]
    })
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)

    print("✅ 데이터 수집 및 분석 완료")

except Exception as e:
    print(f"❌ 오류 발생: {e}")

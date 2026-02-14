import os
import feedparser
import google.generativeai as genai
import requests
import yfinance as yf
import json
import re
from datetime import datetime
import pytz

# ... (기존 설정값 동일)

def get_market_indices():
    """세계 주요 지수 및 거래 상태 수집"""
    indices = {
        "S&P 500": "^GSPC",
        "나스닥": "^IXIC",
        "코스피": "^KS11",
        "상해종합": "000001.SS",
        "닛케이225": "^N225",
        "유로스톡스50": "^FEZ"
    }
    
    market_data = []
    for name, ticker in indices.items():
        try:
            stock = yf.Ticker(ticker)
            # 최신 데이터 및 이전 종가 가져오기
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                # 거래 상태 판별 (단순화: 마지막 데이터가 15분 이내면 실시간으로 간주)
                last_time = hist.index[-1].replace(tzinfo=pytz.UTC)
                now = datetime.now(pytz.UTC)
                is_open = (now - last_time).total_seconds() < 900 # 15분 이내
                
                market_data.append({
                    "name": name,
                    "change": round(change_pct, 2),
                    "is_open": is_open
                })
        except: continue
    return market_data

def run_analysis():
    print("글로벌 인사이트 엔진 가동...")
    # 1. 지수 수집
    market_indices = get_market_indices()
    
    # 2. 뉴스 수집 및 믹스
    kr_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
    us_feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en")
    
    # 국내/해외 뉴스에 태그 붙여서 5개씩 섞기
    mixed_news = []
    for i in range(5):
        if i < len(kr_feed.entries): mixed_news.append(f"[국내] {kr_feed.entries[i].title}")
        if i < len(us_feed.entries): mixed_news.append(f"[글로벌] {us_feed.entries[i].title}")

    # 3. Gemini 분석 (기존 로직 동일)
    # ... (생략된 기존 Gemini 호출 및 response.text 획득 과정) ...
    
    # 4. JSON 저장 구조 고도화
    dashboard_data = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'indices': market_indices, # 수집한 지수 데이터 추가
        'tickers': tickers,
        'summary': summary_part, 
        'news_list': mixed_news # 태그된 뉴스 믹스 추가
    }
    
    with open(REC_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
    
    # 텔레그램 발송 (기존과 동일)

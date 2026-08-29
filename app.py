import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd

st.set_page_config(page_title="AI 포트폴리오 일간 브리핑", layout="wide")

# API 키 설정
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key를 입력하세요", type="password")

st.title("📊 맞춤형 AI 포트폴리오 일간 브리핑")
st.caption("내 보유 종목의 당일 주가 변동 및 핵심 뉴스를 AI가 분석해 드립니다.")

# 1. 포트폴리오 입력
st.sidebar.header("내 포트폴리오 설정")
tickers_input = st.sidebar.text_input("티커 입력 (쉼표 구분)", "SPLG, QQQ, AAPL")
weights_input = st.sidebar.text_input("비중 (%) 입력 (쉼표 구분)", "40, 40, 20")

if st.button("🚀 일간 브리핑 생성하기"):
    if not api_key or not api_key.strip():
        st.error("좌측 사이드바에 Gemini API Key를 입력해 주세요.")
    else:
        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
        
        with st.spinner("주가 데이터 및 최신 뉴스 수집 중..."):
            market_data = []
            news_data = []
            
            for ticker in tickers:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="5d")
                if len(hist) >= 2:
                    today_close = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2]
                    change_pct = ((today_close - prev_close) / prev_close) * 100
                    market_data.append({"Ticker": ticker, "Close": f"${today_close:.2f}", "Change (%)": f"{change_pct:+.2f}%"})
                
                # 최신 뉴스 수집
                try:
                    news = stock.news
                    if news:
                        top_news = news[0].get('title', '뉴스 없음')
                        news_data.append(f"[{ticker}] {top_news}")
                except Exception:
                    pass
            
            # 주가 요약 테이블 표시
            st.subheader("📈 포트폴리오 당일 현황")
            if market_data:
                st.dataframe(pd.DataFrame(market_data), use_container_width=True)
            else:
                st.warning("주가 데이터를 불러오지 못했습니다. 티커명을 확인해 주세요.")

        with st.spinner("AI가 공시 및 뉴스를 분석하는 중..."):
            try:
                # 최신 공식 Google GenAI Client 사용
                client = genai.Client(api_key=api_key.strip())
                
                prompt = f"""
당신은 금융 데이터 전문 애널리스트입니다.
아래 사용자의 포트폴리오 현황과 종목별 최신 뉴스 데이터를 바탕으로 '일간 맞춤 브리핑 리포트'를 한글로 작성해주세요.

[포트폴리오 정보]
{market_data}

[종목별 최신 뉴스]
{news_data}

작성 규칙:
1. 💡 **포트폴리오 총평**: 전체적인 흐름과 비중을 고려한 코멘트 (2줄)
2. 🔍 **종목별 핵심 변동 원인 & 리스크 요인**: 각 종목별로 당일 등락 이유와 공시/뉴스 핵심을 2~3줄로 요약
3. ⚠️ **내일 주목할 포인트/액션 제안**: 리스크 관리 관점의 팁 1줄
"""
                # 무료 티어에서 완벽 지원되는 gemini-2.0-flash 호출
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt
                )
                
                st.subheader("🤖 AI 맞춤형 분석 브리핑")
                st.markdown(response.text)
                
            except Exception as e:
                st.error(f"상세 에러 내용: {e}")

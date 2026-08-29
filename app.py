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
tickers_input = st.sidebar.text_input("티커 입력 (쉼표 구분)", "SPLG, QQQ, TSLL")
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
                try:
                    stock = yf.Ticker(ticker)
                    # 1달치 데이터를 가져온 후 결측치(NaN) 제거
                    hist = stock.history(period="1mo").dropna(subset=['Close'])
                    
                    if len(hist) >= 2:
                        today_close = hist['Close'].iloc[-1]
                        prev_close = hist['Close'].iloc[-2]
                        change_pct = ((today_close - prev_close) / prev_close) * 100
                        market_data.append({
                            "Ticker": ticker, 
                            "Close": f"${today_close:.2f}", 
                            "Change (%)": f"{change_pct:+.2f}%"
                        })
                    elif len(hist) == 1:
                        today_close = hist['Close'].iloc[-1]
                        market_data.append({
                            "Ticker": ticker, 
                            "Close": f"${today_close:.2f}", 
                            "Change (%)": "0.00%"
                        })
                    else:
                        market_data.append({
                            "Ticker": ticker, 
                            "Close": "N/A", 
                            "Change (%)": "N/A"
                        })
                except Exception as e:
                    market_data.append({"Ticker": ticker, "Close": "Error", "Change (%)": "Error"})
                
                # 최신 뉴스 수집 (예외 처리 강화)
                try:
                    news = stock.news
                    if news and len(news) > 0:
                        # 최신 뉴스 최대 2개 추출
                        titles = [n.get('title') for n in news[:2] if n.get('title')]
                        news_text = " / ".join(titles) if titles else "최신 뉴스 없음"
                        news_data.append(f"[{ticker}] {news_text}")
                    else:
                        news_data.append(f"[{ticker}] 특이 뉴스 없음")
                except Exception:
                    news_data.append(f"[{ticker}] 뉴스 수집 불가")
            
            # 주가 요약 테이블 표시
            st.subheader("📈 포트폴리오 최근 거래일 현황")
            if market_data:
                st.dataframe(pd.DataFrame(market_data), use_container_width=True)
            else:
                st.warning("주가 데이터를 불러오지 못했습니다. 티커명을 확인해 주세요.")

        with st.spinner("AI가 공시 및 뉴스를 분석하는 중..."):
            try:
                client = genai.Client(api_key=api_key.strip())
                
                prompt = f"""
당신은 금융 데이터 전문 애널리스트입니다.
아래 사용자의 포트폴리오 현황(주가 및 등락률)과 종목별 최신 뉴스 데이터를 바탕으로 '일간 맞춤 브리핑 리포트'를 한글로 작성해주세요.

[포트폴리오 정보]
{market_data}

[종목별 최신 뉴스]
{news_data}

작성 규칙:
1. 💡 **포트폴리오 총평**: 전체적인 흐름과 비중을 고려한 코멘트 (2줄)
2. 🔍 **종목별 핵심 변동 원인 & 리스크 요인**: 각 종목별로 당일 등락 이유와 공시/뉴스 핵심을 2~3줄로 요약 (수치 데이터가 있으면 함께 언급)
3. ⚠️ **내일 주목할 포인트/액션 제안**: 리스크 관리 관점의 팁 1줄
"""
                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=prompt
                )
                
                st.subheader("🤖 AI 맞춤형 분석 브리핑")
                st.markdown(response.text)
                
            except Exception as e:
                st.error(f"상세 에러 내용: {e}")

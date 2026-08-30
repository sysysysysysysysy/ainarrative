import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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

# 차트 기간 선택
chart_period = st.sidebar.selectbox("주가 차트 조회 기간", ["1mo", "3mo", "6mo", "1y"], index=0)

if st.button("🚀 일간 브리핑 생성하기"):
    if not api_key or not api_key.strip():
        st.error("좌측 사이드바에 Gemini API Key를 입력해 주세요.")
    else:
        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
        
        # 비중 파싱
        try:
            weights = [float(w.strip()) for w in weights_input.split(",") if w.strip()]
            if len(weights) != len(tickers):
                weights = [100 / len(tickers)] * len(tickers)
        except Exception:
            weights = [100 / len(tickers)] * len(tickers)

        with st.spinner("주가 데이터 및 최신 뉴스 수집 중..."):
            market_data = []
            news_data = []
            chart_df = pd.DataFrame()
            
            for ticker in tickers:
                close_str = None
                change_str = None
                ticker_obj = yf.Ticker(ticker)
                
                # 1) 차트 및 주가 계산용 히스토리 데이터 수집
                try:
                    hist = ticker_obj.history(period=chart_period)
                    if not hist.empty and 'Close' in hist:
                        # 차트용 데이터프레임 병합
                        chart_df[ticker] = hist['Close']
                        
                        close_vals = hist['Close'].dropna().tolist()
                        if len(close_vals) >= 2:
                            p_today = float(close_vals[-1])
                            p_prev = float(close_vals[-2])
                            diff_pct = ((p_today - p_prev) / p_prev) * 100
                            close_str = f"${p_today:.2f}"
                            change_str = f"{diff_pct:+.2f}%"
                except Exception:
                    pass
                
                # 2) Fallback 가격 조회
                if not close_str:
                    try:
                        f_info = ticker_obj.fast_info
                        p_today = f_info.last_price
                        p_prev = f_info.previous_close
                        if p_today and p_prev:
                            close_str = f"${float(p_today):.2f}"
                            diff_pct = ((float(p_today) - float(p_prev)) / float(p_prev)) * 100
                            change_str = f"{diff_pct:+.2f}%"
                    except Exception:
                        pass

                market_data.append({
                    "Ticker": ticker,
                    "Close": close_str if close_str else "N/A",
                    "Change (%)": change_str if change_str else "0.00%"
                })
                
                # 3) 최신 뉴스 수집
                try:
                    news_list = getattr(ticker_obj, 'news', [])
                    if news_list and isinstance(news_list, list):
                        titles = [item.get('title') for item in news_list[:2] if isinstance(item, dict) and item.get('title')]
                        news_text = " / ".join(titles) if titles else "최신 특이 뉴스 없음"
                        news_data.append(f"[{ticker}] {news_text}")
                    else:
                        news_data.append(f"[{ticker}] 특이 뉴스 없음")
                except Exception:
                    news_data.append(f"[{ticker}] 뉴스 수집 불가")
            
            # --- 상단: 포트폴리오 현황 테이블 & 비중 차트 ---
            st.subheader("📈 포트폴리오 최근 거래일 현황")
            col1, col2 = st.columns([3, 2])
            
            with col1:
                st.dataframe(pd.DataFrame(market_data), use_container_width=True)
                
            with col2:
                # 포트폴리오 비중 도넛 차트
                pie_fig = px.pie(
                    names=tickers, 
                    values=weights, 
                    hole=0.4, 
                    title="포트폴리오 비중 구성",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                pie_fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=220)
                st.plotly_chart(pie_fig, use_container_width=True)

            # --- 중단: 종목별 주가 추이 인터랙티브 라인 차트 ---
            if not chart_df.empty:
                st.subheader(f"📊 종목별 주가 추이 ({chart_period.upper()})")
                
                # 수익률 기준 정규화(기준점 100) 옵션
                normalize = st.checkbox("기준일 대비 수익률(%)로 정규화해서 비교하기", value=False)
                
                if normalize:
                    plot_data = (chart_df / chart_df.iloc[0] - 1) * 100
                    y_title = "수익률 (%)"
                else:
                    plot_data = chart_df
                    y_title = "주가 ($)"
                
                line_fig = px.line(
                    plot_data, 
                    labels={"value": y_title, "Date": "날짜", "variable": "종목"},
                    title=f"포트폴리오 종목별 가격 흐름"
                )
                line_fig.update_layout(
                    hovermode="x unified",
                    margin=dict(t=40, b=20, l=20, r=20),
                    height=380
                )
                st.plotly_chart(line_fig, use_container_width=True)

        # --- 하단: AI 맞춤형 분석 브리핑 ---
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

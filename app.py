import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
import time

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
            price_dict = {}
            
            for ticker in tickers:
                close_str = "N/A"
                change_str = "0.00%"
                
                try:
                    t_obj = yf.Ticker(ticker)
                    hist = t_obj.history(period=chart_period)
                    
                    if not hist.empty and 'Close' in hist.columns:
                        hist.index = hist.index.tz_localize(None)
                        s = hist['Close'].dropna()
                        
                        if len(s) >= 2:
                            p_today = float(s.iloc[-1])
                            p_prev = float(s.iloc[-2])
                            diff_pct = ((p_today - p_prev) / p_prev) * 100
                            close_str = f"${p_today:.2f}"
                            change_str = f"{diff_pct:+.2f}%"
                            price_dict[ticker] = s
                        elif len(s) == 1:
                            p_today = float(s.iloc[-1])
                            close_str = f"${p_today:.2f}"
                            price_dict[ticker] = s
                except Exception:
                    pass
                
                market_data.append({
                    "Ticker": ticker,
                    "Close": close_str,
                    "Change (%)": change_str
                })
                
                # 최신 뉴스 수집
                try:
                    t_obj = yf.Ticker(ticker)
                    news_list = getattr(t_obj, 'news', [])
                    if news_list and isinstance(news_list, list):
                        titles = [item.get('title') for item in news_list[:2] if isinstance(item, dict) and item.get('title')]
                        news_text = " / ".join(titles) if titles else "최신 특이 뉴스 없음"
                        news_data.append(f"[{ticker}] {news_text}")
                    else:
                        news_data.append(f"[{ticker}] 특이 뉴스 없음")
                except Exception:
                    news_data.append(f"[{ticker}] 뉴스 수집 불가")

            # --- 상단: 포트폴리오 현황 테이블 & 비중 도넛 차트 ---
            st.subheader("📈 포트폴리오 최근 거래일 현황")
            col1, col2 = st.columns([3, 2])
            
            with col1:
                st.dataframe(pd.DataFrame(market_data), use_container_width=True)
                
            with col2:
                pie_fig = px.pie(
                    names=tickers, 
                    values=weights, 
                    hole=0.4, 
                    title="포트폴리오 비중 구성",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                pie_fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=220)
                st.plotly_chart(pie_fig, use_container_width=True)

            # --- 중단: 종목별 개별 주가 추이 차트 (단독 Y축) ---
            if price_dict:
                st.subheader(f"📊 종목별 개별 주가 흐름 ({chart_period.upper()})")
                
                # 화면 너비에 맞게 종목 수만큼 컬럼 생성 (최대 3단)
                cols_count = min(3, len(price_dict))
                chart_cols = st.columns(cols_count)
                
                for idx, (ticker, series) in enumerate(price_dict.items()):
                    col_idx = idx % cols_count
                    with chart_cols[col_idx]:
                        # 개별 데이터프레임 구성
                        single_df = pd.DataFrame({
                            "Date": series.index.strftime('%Y-%m-%d'),
                            "Price": series.values
                        })
                        
                        # 종목별 등락에 따른 메인 색상 선택
                        line_color = "#00C805" if series.values[-1] >= series.values[0] else "#FF333A"
                        
                        fig = px.line(
                            single_df, 
                            x="Date", 
                            y="Price", 
                            title=f"<b>{ticker}</b> (${series.values[-1]:.2f})",
                            labels={"Price": "주가 ($)", "Date": "날짜"}
                        )
                        fig.update_traces(line_color=line_color, line_width=2.5)
                        fig.update_layout(
                            hovermode="x unified",
                            margin=dict(t=40, b=10, l=10, r=10),
                            height=250,
                            xaxis=dict(showgrid=False),
                            yaxis=dict(showgrid=True)
                        )
                        st.plotly_chart(fig, use_container_width=True)

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
                # 부하 분산 및 안정적 대체 모델 풀
                candidate_models = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.5-pro']
                response_text = None
                last_error = None

                for target_model in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=target_model,
                            contents=prompt
                        )
                        if response and response.text:
                            response_text = response.text
                            break
                    except Exception as e:
                        last_error = e
                        time.sleep(1)  # 503 발생 시 1초 대기 후 대체 모델 시도
                        continue
                
                if response_text:
                    st.subheader("🤖 AI 맞춤형 분석 브리핑")
                    st.markdown(response_text)
                else:
                    st.error(f"일시적인 서버 부하로 응답을 생성하지 못했습니다: {last_error}")
                
            except Exception as e:
                st.error(f"상세 에러 내용: {e}")

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
tickers_input = st.sidebar.text_input(
    "보유 종목 입력 (한글명 또는 티커, 쉼표 구분)", 
    "테슬라, QQQM, SPYM"
)
weights_input = st.sidebar.text_input("비중 (%) 입력 (쉼표 구분)", "40, 40, 20")

# 차트 기간 선택
chart_period = st.sidebar.selectbox("주가 차트 조회 기간", ["1mo", "3mo", "6mo", "1y"], index=0)

def resolve_tickers_with_ai(client, user_text):
    """한글/영문 종목명 및 별칭을 yfinance 공식 티커 심볼로 자동 변환"""
    prompt = f"""
당신은 금융 데이터 시스템의 종목명-티커 변환기입니다.
다음 사용자가 입력한 주식 종목명들을 야후 파이낸스(yfinance)에서 조회 가능한 '공식 티커 심볼'로 변환하세요.

규칙:
1. 미국 주식/ETF는 영문 티커(예: TSLA, QQQ, AAPL, SPYM)로 변환
2. 한국 주식은 코스피는 .KS, 코스닥은 .KQ(예: 삼성전자 -> 005930.KS, 에코프로비엠 -> 247540.KQ)
3. 레버리지/인버스/ETF 별칭도 정확한 티커로 매핑 (예: 테슬라 2배 -> TSLL)
4. 오직 쉼표(,)로 구분된 티커 심볼 문자열만 출력 (마크다운, 코드블록, 부가 설명 금지)

사용자 입력: "{user_text}"
출력 예시: TSLA, QQQM, SPYM
"""
    candidate_models = ['gemini-3.6-flash', 'gemini-3.1-pro-preview']
    for model_name in candidate_models:
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if res and res.text:
                cleaned = res.text.strip().replace('`', '').replace('\n', '')
                tickers = [t.strip().upper() for t in cleaned.split(',') if t.strip()]
                if tickers:
                    return tickers
        except Exception:
            continue
            
    # AI 변환 실패 시 사용자 입력 단순 분리 fallback
    return [t.strip().upper() for t in user_text.split(',') if t.strip()]

def fetch_robust_history(ticker_symbol, period):
    """ETF 및 개별 종목의 과거 데이터를 안전하게 수집하는 함수"""
    # 1차 시도: yf.download
    try:
        df = yf.download(
            ticker_symbol, 
            period=period, 
            auto_adjust=False, 
            progress=False, 
            multi_level_index=False
        )
        if not df.empty and 'Close' in df.columns:
            s = df['Close'].dropna()
            if len(s) >= 2:
                return s
    except Exception:
        pass

    # 2차 시도: Ticker.history (auto_adjust=False)
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period=period, auto_adjust=False)
        if not hist.empty and 'Close' in hist.columns:
            s = hist['Close'].dropna()
            if len(s) >= 2:
                return s
    except Exception:
        pass

    # 3차 시도: 1년치 fallback
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="1y")
        if not hist.empty and 'Close' in hist.columns:
            s = hist['Close'].dropna()
            if len(s) >= 2:
                return s
    except Exception:
        pass

    return pd.Series(dtype='float64')

if st.button("🚀 일간 브리핑 생성하기"):
    if not api_key or not api_key.strip():
        st.error("좌측 사이드바에 Gemini API Key를 입력해 주세요.")
    else:
        client = genai.Client(api_key=api_key.strip())
        
        with st.spinner("입력된 종목명을 분석하고 공식 티커로 변환 중..."):
            tickers = resolve_tickers_with_ai(client, tickers_input)
            st.info(f"💡 인식된 공식 티커: **{', '.join(tickers)}**")

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
                
                series = fetch_robust_history(ticker, chart_period)
                
                if not series.empty and len(series) >= 2:
                    p_today = float(series.iloc[-1])
                    p_prev = float(series.iloc[-2])
                    diff_pct = ((p_today - p_prev) / p_prev) * 100
                    
                    currency_symbol = "₩" if ticker.endswith((".KS", ".KQ")) else "$"
                    close_str = f"{currency_symbol}{p_today:,.2f}"
                    change_str = f"{diff_pct:+.2f}%"
                    price_dict[ticker] = series
                
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

            # --- 중단: 종목별 개별 주가 추이 차트 ---
            if price_dict:
                st.subheader(f"📊 종목별 개별 주가 흐름 ({chart_period.upper()})")
                
                cols_count = min(3, len(price_dict))
                chart_cols = st.columns(cols_count)
                
                for idx, (ticker, series) in enumerate(price_dict.items()):
                    col_idx = idx % cols_count
                    with chart_cols[col_idx]:
                        dates = [pd.to_datetime(d).strftime('%Y-%m-%d') for d in series.index]
                        
                        single_df = pd.DataFrame({
                            "Date": dates,
                            "Price": series.values
                        })
                        
                        line_color = "#00C805" if series.values[-1] >= series.values[0] else "#FF333A"
                        currency_symbol = "₩" if ticker.endswith((".KS", ".KQ")) else "$"
                        
                        fig = px.line(
                            single_df, 
                            x="Date", 
                            y="Price", 
                            title=f"<b>{ticker}</b> ({currency_symbol}{series.values[-1]:,.2f})",
                            labels={"Price": f"주가 ({currency_symbol})", "Date": "날짜"}
                        )
                        fig.update_traces(line_color=line_color, line_width=2.5)
                        fig.update_layout(
                            hovermode="x unified",
                            margin=dict(t=40, b=10, l=10, r=10),
                            height=250,
                            xaxis=dict(showgrid=False, nticks=5),
                            yaxis=dict(showgrid=True)
                        )
                        st.plotly_chart(fig, use_container_width=True)

        # --- 하단: AI 맞춤형 분석 브리핑 ---
        with st.spinner("AI가 공시 및 뉴스를 분석하는 중..."):
            try:
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
                candidate_models = ['gemini-3.6-flash', 'gemini-3.1-pro-preview']
                response_text = None
                last_error = None

                for target_model in candidate_models:
                    for attempt in range(2):
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
                            time.sleep(2)
                    
                    if response_text:
                        break
                
                if response_text:
                    st.subheader("🤖 AI 맞춤형 분석 브리핑")
                    st.markdown(response_text)
                else:
                    st.error(f"일시적인 서버 부하로 응답을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요: {last_error}")
                
            except Exception as e:
                st.error(f"상세 에러 내용: {e}")

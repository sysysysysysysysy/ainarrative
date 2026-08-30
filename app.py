import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
import json
import re
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
    "삼성전자, 테슬라, QQQM"
)
weights_input = st.sidebar.text_input("비중 (%) 입력 (쉼표 구분)", "40, 40, 20")

# 차트 기간 선택
period_mapping = {
    "1일 (당일 실시간 흐름)": "1d",
    "5일 (최근 1주일)": "5d",
    "1개월": "1mo",
    "3개월": "3mo",
    "6개월": "6mo",
    "1년": "1y",
    "3년": "3y",
    "5년": "5y",
    "전체 (Max)": "max"
}
selected_period_label = st.sidebar.selectbox(
    "주가 차트 조회 기간", 
    list(period_mapping.keys()), 
    index=2
)
chart_period = period_mapping[selected_period_label]

# 주요 종목 내장 사전 (API 호출 쿼터 절약)
COMMON_STOCK_MAP = {
    "삼성전자": {"display_name": "삼성전자 (005930.KS)", "ticker": "005930.KS"},
    "SK하이닉스": {"display_name": "SK하이닉스 (000660.KS)", "ticker": "000660.KS"},
    "현대차": {"display_name": "현대차 (005380.KS)", "ticker": "005380.KS"},
    "NAVER": {"display_name": "NAVER (035420.KS)", "ticker": "035420.KS"},
    "네이버": {"display_name": "NAVER (035420.KS)", "ticker": "035420.KS"},
    "카카오": {"display_name": "카카오 (035720.KS)", "ticker": "035720.KS"},
    "테슬라": {"display_name": "테슬라 (TSLA)", "ticker": "TSLA"},
    "애플": {"display_name": "애플 (AAPL)", "ticker": "AAPL"},
    "엔비디아": {"display_name": "엔비디아 (NVDA)", "ticker": "NVDA"},
    "마이크로소프트": {"display_name": "마이크로소프트 (MSFT)", "ticker": "MSFT"},
    "구글": {"display_name": "알파벳 (GOOGL)", "ticker": "GOOGL"},
    "알파벳": {"display_name": "알파벳 (GOOGL)", "ticker": "GOOGL"},
    "아마존": {"display_name": "아마존 (AMZN)", "ticker": "AMZN"},
    "TSLL": {"display_name": "TSLL (테슬라 2X)", "ticker": "TSLL"},
    "테슬라 2배": {"display_name": "TSLL (테슬라 2X)", "ticker": "TSLL"},
    "QQQM": {"display_name": "QQQM (나스닥100)", "ticker": "QQQM"},
    "QQQ": {"display_name": "QQQ (나스닥100)", "ticker": "QQQ"},
    "SPYM": {"display_name": "SPYM (S&P500)", "ticker": "SPYM"},
    "SPLG": {"display_name": "SPLG (S&P500)", "ticker": "SPLG"},
    "VOO": {"display_name": "VOO (S&P500)", "ticker": "VOO"},
    "SCHD": {"display_name": "SCHD (미국배당다우존스)", "ticker": "SCHD"}
}

def resolve_stock_info(client, user_text):
    """사전 매핑 우선 처리 후 미확인 종목만 Gemini로 안전하게 변환"""
    items = [t.strip() for t in user_text.split(',') if t.strip()]
    resolved_list = []
    unresolved_items = []

    for item in items:
        clean_item = item.upper()
        if item in COMMON_STOCK_MAP:
            resolved_list.append(COMMON_STOCK_MAP[item])
        elif clean_item in COMMON_STOCK_MAP:
            resolved_list.append(COMMON_STOCK_MAP[clean_item])
        elif clean_item.endswith((".KS", ".KQ")):
            resolved_list.append({"display_name": clean_item, "ticker": clean_item})
        elif clean_item.isalpha() and len(clean_item) <= 5:
            # 영문 일반 티커
            resolved_list.append({"display_name": f"{clean_item}", "ticker": clean_item})
        else:
            unresolved_items.append(item)

    # 사전에 없는 특수 종목만 Gemini에 1회 호출
    if unresolved_items:
        prompt = f"""
다음 주식명들을 yfinance 공식 티커와 친숙한 표시명(display_name) JSON 배열로 변환해줘.
한국주식: .KS 또는 .KQ / 미국주식: 영문티커
순수 JSON 배열만 반환:
[
  {{"display_name": "종목명 (티커)", "ticker": "공식티커"}}
]
입력: "{', '.join(unresolved_items)}"
"""
        try:
            res = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            if res and res.text:
                cleaned = re.sub(r'```json\s*|\s*```', '', res.text).strip()
                data = json.loads(cleaned)
                if isinstance(data, list):
                    resolved_list.extend(data)
        except Exception:
            for item in unresolved_items:
                resolved_list.append({"display_name": item, "ticker": item})

    return resolved_list if resolved_list else [{"display_name": t, "ticker": t} for t in items]

def fetch_daily_summary(ticker_symbol, is_korean):
    """일간 최신 종가 및 전일비 등락률 산출"""
    close_str = "N/A"
    change_str = "0.00%"
    currency_symbol = "₩" if is_korean else "$"
    
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="1mo", auto_adjust=False)
        if not hist.empty and 'Close' in hist.columns:
            s = hist['Close'].dropna()
            if len(s) >= 2:
                p_today = float(s.iloc[-1])
                p_prev = float(s.iloc[-2])
                diff_pct = ((p_today - p_prev) / p_prev) * 100
                price_format = f"{currency_symbol}{p_today:,.0f}" if is_korean else f"{currency_symbol}{p_today:,.2f}"
                return price_format, f"{diff_pct:+.2f}%"
    except Exception:
        pass
    
    return close_str, change_str

def fetch_chart_data(ticker_symbol, period):
    """기간별 적정 인터벌을 적용한 차트 데이터 수집"""
    interval = "5m" if period == "1d" else ("15m" if period == "5d" else "1d")
    
    try:
        df = yf.download(
            ticker_symbol, 
            period=period, 
            interval=interval,
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

    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period=period, interval=interval, auto_adjust=False)
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
        
        # 종목 매핑 (사전 기반 즉각 처리)
        stock_items = resolve_stock_info(client, tickers_input)
        display_names = [item['display_name'] for item in stock_items]
        st.info(f"💡 분석 대상 종목: **{' | '.join(display_names)}**")

        try:
            weights = [float(w.strip()) for w in weights_input.split(",") if w.strip()]
            if len(weights) != len(stock_items):
                weights = [100 / len(stock_items)] * len(stock_items)
        except Exception:
            weights = [100 / len(stock_items)] * len(stock_items)

        with st.spinner("주가 데이터 및 최신 뉴스 수집 중..."):
            market_data = []
            news_data = []
            price_dict = {}
            
            for item in stock_items:
                disp_name = item['display_name']
                ticker = item['ticker']
                is_korean = ticker.endswith((".KS", ".KQ"))
                
                # 1) 종가/등락률
                close_str, change_str = fetch_daily_summary(ticker, is_korean)
                market_data.append({
                    "종목명": disp_name,
                    "종가 (Close)": close_str,
                    "변동률 (%)": change_str
                })
                
                # 2) 차트 데이터
                series = fetch_chart_data(ticker, chart_period)
                if not series.empty:
                    price_dict[disp_name] = (series, is_korean)
                
                # 3) 뉴스
                try:
                    t_obj = yf.Ticker(ticker)
                    news_list = getattr(t_obj, 'news', [])
                    if news_list and isinstance(news_list, list):
                        titles = [n.get('title') for n in news_list[:2] if isinstance(n, dict) and n.get('title')]
                        news_text = " / ".join(titles) if titles else "최신 특이 뉴스 없음"
                        news_data.append(f"[{disp_name}] {news_text}")
                    else:
                        news_data.append(f"[{disp_name}] 특이 뉴스 없음")
                except Exception:
                    news_data.append(f"[{disp_name}] 뉴스 수집 불가")

            # --- 상단: 포트폴리오 현황 테이블 & 비중 도넛 차트 ---
            st.subheader("📈 포트폴리오 최근 거래일 현황")
            col1, col2 = st.columns([3, 2])
            
            with col1:
                st.dataframe(pd.DataFrame(market_data), use_container_width=True)
                
            with col2:
                pie_fig = px.pie(
                    names=display_names, 
                    values=weights, 
                    hole=0.4, 
                    title="포트폴리오 비중 구성",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                pie_fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=220)
                st.plotly_chart(pie_fig, use_container_width=True)

            # --- 중단: 종목별 개별 주가 추이 차트 ---
            if price_dict:
                st.subheader(f"📊 종목별 주가 흐름 ({selected_period_label})")
                
                cols_count = min(3, len(price_dict))
                chart_cols = st.columns(cols_count)
                
                for idx, (disp_name, (series, is_korean)) in enumerate(price_dict.items()):
                    col_idx = idx % cols_count
                    with chart_cols[col_idx]:
                        if chart_period == "1d":
                            dates = [pd.to_datetime(d).strftime('%H:%M') for d in series.index]
                            x_label = "시간"
                        elif chart_period == "5d":
                            dates = [pd.to_datetime(d).strftime('%m/%d %H:%M') for d in series.index]
                            x_label = "일시"
                        else:
                            dates = [pd.to_datetime(d).strftime('%Y-%m-%d') for d in series.index]
                            x_label = "날짜"
                        
                        single_df = pd.DataFrame({
                            "Date": dates,
                            "Price": series.values
                        })
                        
                        line_color = "#00C805" if series.values[-1] >= series.values[0] else "#FF333A"
                        currency_symbol = "₩" if is_korean else "$"
                        last_p_str = f"{currency_symbol}{series.values[-1]:,.0f}" if is_korean else f"{currency_symbol}{series.values[-1]:,.2f}"
                        
                        fig = px.line(
                            single_df, 
                            x="Date", 
                            y="Price", 
                            title=f"<b>{disp_name}</b> ({last_p_str})",
                            labels={"Price": f"주가 ({currency_symbol})", "Date": x_label}
                        )
                        fig.update_traces(line_color=line_color, line_width=2.5)
                        fig.update_layout(
                            hovermode="x unified",
                            margin=dict(t=40, b=10, l=10, r=10),
                            height=260,
                            xaxis=dict(showgrid=False, nticks=6),
                            yaxis=dict(showgrid=True)
                        )
                        st.plotly_chart(fig, use_container_width=True)

        # --- 하단: AI 맞춤형 분석 브리핑 (Flash 전용 & 429 방지) ---
        with st.spinner("AI가 공시 및 뉴스를 분석하는 중..."):
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
            response_text = None
            last_error = None

            # 무료 티어 지원 Flash 모델 단독 호출 및 자동 재시도
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=prompt
                    )
                    if response and response.text:
                        response_text = response.text
                        break
                except Exception as e:
                    last_error = e
                    time.sleep(3)  # 429 발생 시 3초 쿨다운 후 재시도
            
            if response_text:
                st.subheader("🤖 AI 맞춤형 분석 브리핑")
                st.markdown(response_text)
            else:
                st.error(f"일시적인 서버 부하로 응답을 생성하지 못했습니다: {last_error}")

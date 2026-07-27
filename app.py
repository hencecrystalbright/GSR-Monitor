import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

st.set_page_config(
    page_title="金銀市場與套利監測 (自動化版)", page_icon="🪙", layout="centered"
)

st.title("🪙 每日金銀市場與套利監測")
st.caption("數據來源：Stooq（主要）＋ Yahoo Finance（備援） / GoldSilver.ai（手動校正）")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

STOOQ_MAP = {
    "spot_silver": "xagusd",
    "spot_gold": "xauusd",
    "comex_silver": "si.f",
    "dxy": "dx.f",
}
YF_MAP = {
    "spot_silver": "XAGUSD=X",
    "spot_gold": "XAUUSD=X",
    "comex_silver": "SI=F",
    "dxy": "DX-Y.NYB",
}


def fetch_stooq(symbol):
    """用 Stooq 的 CSV 下載端點抓日線資料，對雲端主機 IP 較友善，不易被擋。"""
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if df.empty or "Close" not in df.columns:
        raise ValueError(f"Stooq 回傳空資料：{symbol}")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df["Close"].dropna()


def fetch_yfinance(symbol):
    """備援來源：Yahoo Finance。雲端主機常被封鎖，僅作為 Stooq 失敗時的救援手段。"""
    import yfinance as yf

    df = yf.Ticker(symbol).history(period="2mo")
    if df.empty or "Close" not in df:
        raise ValueError(f"Yahoo 回傳空資料：{symbol}")
    return df["Close"].dropna()


@st.cache_data(ttl=1800)  # 30分鐘快取
def fetch_market_data():
    errors = []
    series_map = {}

    for key, stooq_symbol in STOOQ_MAP.items():
        try:
            series_map[key] = fetch_stooq(stooq_symbol)
        except Exception as e:
            errors.append(f"Stooq 抓取 {key}({stooq_symbol}) 失敗：{e}")
            try:
                series_map[key] = fetch_yfinance(YF_MAP[key])
            except Exception as e2:
                errors.append(f"Yahoo 備援抓取 {key} 也失敗：{e2}")
                return None, errors

    s_silver = series_map["spot_silver"]
    s_gold = series_map["spot_gold"]
    s_comex = series_map["comex_silver"]
    s_dxy = series_map["dxy"]

    if len(s_silver) == 0 or len(s_gold) == 0:
        errors.append("現貨金/銀資料為空，無法計算 GSR。")
        return None, errors

    return {
        "spot_silver": round(float(s_silver.iloc[-1]), 2),
        "spot_gold": round(float(s_gold.iloc[-1]), 2),
        "comex_silver": round(float(s_comex.iloc[-1]), 2),
        "dxy": round(float(s_dxy.iloc[-1]), 2),
        "gsr": round(float(s_gold.iloc[-1] / s_silver.iloc[-1]), 2),
        "hist_spot_silver": s_silver,
        "hist_gsr": (s_gold / s_silver).dropna(),
        "as_of": s_silver.index[-1].strftime("%Y-%m-%d"),
    }, errors


if st.button("🔄 重新查詢", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

market_data, fetch_errors = fetch_market_data()

if fetch_errors and market_data is None:
    st.error("⚠️ 主要與備援資料源皆抓取失敗，請稍後再試：")
    for e in fetch_errors:
        st.code(e)
elif fetch_errors:
    with st.expander("⚠️ 部分資料改用備援來源，點此查看細節"):
        for e in fetch_errors:
            st.code(e)

# 側邊欄：上海銀溢價手動輸入
st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 (%)",
    value=12.22,
    step=0.1,
    help="請輸入今日最新的真實溢價數據",
)
st.sidebar.markdown(
    "👉 **[點此查看 GoldSilver.ai 即時溢價](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

if market_data:
    st.caption(f"資料時間：{market_data['as_of']}　|　查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.markdown("### 📍 當日核心市場數據")

    col1, col2, col3 = st.columns(3)
    col1.metric("現貨銀價 (Spot)", f"${market_data['spot_silver']}")
    col2.metric("COMEX 期銀", f"${market_data['comex_silver']}")
    col3.metric("DXY 美元指數", f"{market_data['dxy']}")

    col4, col5 = st.columns(2)
    col4.metric("金銀比 (GSR)", f"{market_data['gsr']}")
    col5.metric("上海銀溢價 (手動)", f"{sh_premium}%")

    st.markdown(
        "<div style='text-align: right;'><a href='https://goldsilver.ai/metal-prices/shanghai-silver-price' target='_blank'>🔗 前往確認上海銀真實溢價</a></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### 🚨 當日套利與轉置建議")

    if market_data["gsr"] >= 80:
        st.error(f"【GSR 警示】金銀比達 {market_data['gsr']}（>=80）。白銀相對嚴重低估，建議考慮「賣金買銀」。")
    elif market_data["gsr"] <= 50:
        st.warning(f"【GSR 警示】金銀比達 {market_data['gsr']}（<=50）。白銀相對昂貴，建議「賣銀買金」。")
    else:
        st.info(f"【GSR 狀態】金銀比為 {market_data['gsr']}，目前位於中性區間。")

    if sh_premium >= 20:
        st.error(f"【溢價警示】上海銀溢價達 {sh_premium}%！中國實體需求極強，建議避開 COMEX 空單。")
    elif sh_premium <= 10:
        st.success(f"【溢價狀態】上海銀溢價為 {sh_premium}%。東西方定價收斂，無顯著跨市套利空間。")
    else:
        st.warning(f"【溢價狀態】上海銀溢價為 {sh_premium}%，處於過渡區間，需求偏強但未達極端門檻。")

    st.markdown("---")
    st.markdown("### 📊 近期走勢圖")
    tab1, tab2 = st.tabs(["GSR 金銀比走勢", "現貨銀價走勢"])
    with tab1:
        st.line_chart(market_data["hist_gsr"])
    with tab2:
        st.area_chart(market_data["hist_spot_silver"])

st.divider()
st.caption("僅供研究參考，不構成投資建議。")

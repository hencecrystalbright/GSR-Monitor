import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(
    page_title="金銀市場與套利監測 (自動化版)", page_icon="🪙", layout="centered"
)

st.title("🪙 每日金銀市場與套利監測")
st.caption("數據來源：gold-api.com（現貨）＋ Frankfurter（DXY）＋ CoinGecko（白銀RSI） / 皆為免金鑰端點")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_metal_price(symbol):
    """gold-api.com：無需金鑰、無流量限制的現貨金屬價格端點。"""
    r = requests.get(f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"]), data.get("updatedAt")

def fetch_synthetic_dxy():
    """用 Frankfurter（免金鑰的 ECB 匯率源）依 ICE 官方公式重建合成 DXY。"""
    r = requests.get(
        "https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,JPY,GBP,CAD,SEK,CHF",
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    rates = r.json()["rates"]
    eurusd = 1 / rates["EUR"]
    usdjpy = rates["JPY"]
    gbpusd = 1 / rates["GBP"]
    usdcad = rates["CAD"]
    usdsek = rates["SEK"]
    usdchf = rates["CHF"]
    dxy = (
        50.14348112
        * (eurusd ** -0.576)
        * (usdjpy ** 0.136)
        * (gbpusd ** -0.119)
        * (usdcad ** 0.091)
        * (usdsek ** 0.042)
        * (usdchf ** 0.036)
    )
    return dxy

def fetch_silver_rsi(period=14):
    """
    【終極免金鑰 RSI 方案】
    呼叫 CoinGecko 免費端點，抓取與實體白銀 1:1 掛鉤的 Kinesis Silver (KAG) 歷史價格。
    免 API Key、且不受雲端防火牆阻擋。
    """
    url = "https://api.coingecko.com/api/v3/coins/kinesis-silver/market_chart"
    params = {
        "vs_currency": "usd",
        "days": "30",
        "interval": "daily"
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    
    prices = data.get("prices", [])
    if not prices or len(prices) < period + 1:
        raise ValueError("歷史資料不足以計算 RSI")
        
    # 擷取歷史收盤價 (prices 格式為 [timestamp, price])
    closes = pd.Series([p[1] for p in prices])
    
    # 計算 RSI
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return float(rsi.iloc[-1])

@st.cache_data(ttl=1800)  # 30分鐘快取
def fetch_market_data():
    errors = []

    try:
        silver_spot, silver_ts = fetch_metal_price("XAG")
        gold_spot, gold_ts = fetch_metal_price("XAU")
    except Exception as e:
        errors.append(f"gold-api.com 抓取金/銀現貨失敗：{e}")
        return None, errors

    try:
        dxy = fetch_synthetic_dxy()
    except Exception as e:
        errors.append(f"合成 DXY 計算失敗：{e}")
        dxy = None

    try:
        rsi = fetch_silver_rsi()
    except Exception as e:
        errors.append(f"白銀 RSI 抓取失敗（不影響其他數據）：{e}")
        rsi = None

    gsr = round(gold_spot / silver_spot, 2)

    return {
        "spot_silver": round(silver_spot, 2),
        "spot_gold": round(gold_spot, 2),
        "dxy": round(dxy, 2) if dxy is not None else None,
        "gsr": gsr,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "as_of": silver_ts,
    }, errors


if st.button("🔄 重新查詢", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# 側邊欄：上海銀溢價手動輸入 (RSI 已經全自動化，無需再輸入 Key)
st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 (%)", value=12.22, step=0.1, help="請輸入今日最新的真實溢價數據"
)
st.sidebar.markdown(
    "👉 **[點此查看 GoldSilver.ai 即時溢價](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

# 執行抓取
market_data, fetch_errors = fetch_market_data()

if fetch_errors and market_data is None:
    st.error("⚠️ 資料抓取失敗，請稍後再試：")
    for e in fetch_errors:
        st.code(e)
elif fetch_errors:
    with st.expander("⚠️ 部分數據抓取異常，點此查看細節"):
        for e in fetch_errors:
            st.code(e)

if market_data:
    st.caption(f"現貨資料時間：{market_data['as_of']} | 查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.markdown("### 📍 當日核心市場數據")

    col1, col2, col3 = st.columns(3)
    col1.metric("現貨銀價 (Spot)", f"${market_data['spot_silver']}")
    col2.metric("現貨金價 (Spot)", f"${market_data['spot_gold']}")
    col3.metric("合成 DXY", market_data["dxy"] if market_data["dxy"] is not None else "查詢失敗")

    col4, col5, col6 = st.columns(3)
    col4.metric("金銀比 (GSR)", f"{market_data['gsr']}")
    col5.metric("上海銀溢價 (手動)", f"{sh_premium}%")
    col6.metric("白銀 RSI(14)", market_data["rsi"] if market_data["rsi"] is not None else "資料不足")

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

st.divider()
st.caption(
    "現貨金銀價由 gold-api.com 提供；DXY 為合成指數；白銀 RSI 由 CoinGecko(KAG) 計算；"
    "上海銀溢價需手動輸入。僅供研究參考，不構成投資建議。"
)

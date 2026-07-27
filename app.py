import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(
    page_title="金銀市場與套利監測 (自動化版)", page_icon="🪙", layout="centered"
)

st.title("🪙 每日金銀市場與套利監測")
st.caption("數據來源：gold-api.com（現貨）＋ Frankfurter（DXY）＋ CoinGecko（RSI/5日歷史）")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_metal_price(symbol):
    """gold-api.com：無需金鑰、無流量限制的現貨金屬價格端點。"""
    r = requests.get(f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"]), data.get("updatedAt")

def fetch_synthetic_dxy():
    """用 Frankfurter 依 ICE 官方公式重建合成 DXY，並依需求下調 0.2。"""
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
    ) - 0.2  # 【修正】手動校正 -0.2 幅度
    return dxy

def fetch_crypto_history(coin_id, days):
    """呼叫 CoinGecko 免費端點，抓取與實體金銀 1:1 掛鉤的代幣歷史價格。"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily"
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json().get("prices", [])

@st.cache_data(ttl=1800)  # 30分鐘快取
def fetch_market_data():
    errors = []

    # 1. 抓取現貨即時價格
    try:
        silver_spot, silver_ts = fetch_metal_price("XAG")
        gold_spot, gold_ts = fetch_metal_price("XAU")
    except Exception as e:
        errors.append(f"gold-api.com 抓取金/銀現貨失敗：{e}")
        return None, errors

    # 2. 抓取 DXY
    try:
        dxy = fetch_synthetic_dxy()
    except Exception as e:
        errors.append(f"合成 DXY 計算失敗：{e}")
        dxy = None

    # 3. 抓取加密代幣歷史以計算 RSI 與 5日前的基準價
    rsi = None
    silver_5d = None
    gold_5d = None
    
    try:
        # 白銀 (Kinesis Silver): 抓 30 天算 RSI，並取倒數第 6 筆作為 5 天前價格
        ag_hist = fetch_crypto_history("kinesis-silver", 30)
        if ag_hist and len(ag_hist) >= 15:
            closes = pd.Series([p[1] for p in ag_hist])
            delta = closes.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            rs = gain.rolling(14).mean() / loss.rolling(14).mean()
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        if ag_hist and len(ag_hist) >= 6:
            silver_5d = ag_hist[-6][1]
            
        # 黃金 (PAX Gold): 只需抓 5 天取第一筆即可
        au_hist = fetch_crypto_history("pax-gold", 5)
        if au_hist and len(au_hist) > 0:
            gold_5d = au_hist[0][1]
            
    except Exception as e:
        errors.append(f"CoinGecko 歷史數據抓取失敗：{e}")

    gsr = round(gold_spot / silver_spot, 2) if silver_spot else None

    return {
        "spot_silver": round(silver_spot, 2) if silver_spot else None,
        "spot_gold": round(gold_spot, 2) if gold_spot else None,
        "dxy": round(dxy, 2) if dxy is not None else None,
        "gsr": gsr,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "silver_5d": silver_5d,
        "gold_5d": gold_5d,
        "as_of": silver_ts,
    }, errors

# 計算費波納契關鍵價位
def calc_fibonacci(current, past):
    if not current or not past:
        return "資料不足", None
    
    if current > past:
        # 上行趨勢：回撤支撐 = 高點 - (高點-低點) * 0.618
        diff = current - past
        fib = current - (diff * 0.618)
        return "上行 📈", round(fib, 2)
    elif current < past:
        # 下行趨勢：反彈壓力 = 低點 + (高點-低點) * 0.618
        diff = past - current
        fib = current + (diff * 0.618)
        return "下行 📉", round(fib, 2)
    else:
        return "盤整 ➖", round(current, 2)

if st.button("🔄 重新查詢", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 (%)", value=12.22, step=0.1, help="請輸入今日最新的真實溢價數據"
)
st.sidebar.markdown(
    "👉 **[點此查看 GoldSilver.ai 即時溢價](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

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
    
    # 區塊 1：核心市場數據
    st.markdown("### 📍 當日核心市場數據")
    col1, col2, col3 = st.columns(3)
    col1.metric("現貨銀價 (Spot)", f"${market_data['spot_silver']}")
    col2.metric("現貨金價 (Spot)", f"${market_data['spot_gold']}")
    col3.metric("合成 DXY (校正)", market_data["dxy"] if market_data["dxy"] is not None else "查詢失敗")

    col4, col5, col6 = st.columns(3)
    col4.metric("金銀比 (GSR)", f"{market_data['gsr']}")
    col5.metric("上海銀溢價 (手動)", f"{sh_premium}%")
    col6.metric("白銀 RSI(14)", market_data["rsi"] if market_data["rsi"] is not None else "資料不足")

    st.markdown("<div style='text-align: right;'><a href='https://goldsilver.ai/metal-prices/shanghai-silver-price' target='_blank'>🔗 前往確認上海銀真實溢價</a></div>", unsafe_allow_html=True)

    st.markdown("---")
    
    # 區塊 2：5日趨勢與費波納契推斷
    st.markdown("### 📐 5日趨勢與費波納契 0.618 關鍵價")
    st.caption("依據現價與 5 日前基準價之相對位置，推算下行反彈壓力或上行回撤支撐。")
    
    fib_col1, fib_col2 = st.columns(2)
    
    with fib_col1:
        st.markdown("**【白銀 XAG】**")
        ag_trend, ag_fib = calc_fibonacci(market_data['spot_silver'], market_data['silver_5d'])
        if market_data['silver_5d']:
            st.metric(f"5日前基準: ${round(market_data['silver_5d'], 2)}", f"方向: {ag_trend}")
            st.info(f"🎯 0.618 關鍵推斷價: **${ag_fib}**")
        else:
            st.warning("缺乏 5 日前歷史數據")

    with fib_col2:
        st.markdown("**【黃金 XAU】**")
        au_trend, au_fib = calc_fibonacci(market_data['spot_gold'], market_data['gold_5d'])
        if market_data['gold_5d']:
            st.metric(f"5日前基準: ${round(market_data['gold_5d'], 2)}", f"方向: {au_trend}")
            st.info(f"🎯 0.618 關鍵推斷價: **${au_fib}**")
        else:
            st.warning("缺乏 5 日前歷史數據")

    st.markdown("---")
    
    # 區塊 3：套利與轉置建議
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
    "現貨金銀價由 gold-api.com 提供；DXY 為合成指數(-0.2)；白銀 RSI 與 5日基準由 CoinGecko 計算；"
    "費波納契推斷僅基於 5 日最高/低點差額運算。僅供研究參考，不構成投資建議。"
)

import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(
    page_title="金銀市場與套利監測 (自動化版)", page_icon="🪙", layout="centered"
)

st.title("🪙 每日金銀市場與套利監測")
st.caption("數據來源：gold-api.com（現貨金銀，免金鑰）＋ Frankfurter（合成DXY，免金鑰） / GoldSilver.ai（手動校正）")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_metal_price(symbol):
    """gold-api.com：無需金鑰、無流量限制的現貨金屬價格端點。"""
    r = requests.get(f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"]), data.get("updatedAt")


def fetch_synthetic_dxy():
    """用 Frankfurter（免金鑰的 ECB 匯率源）依 ICE 官方公式重建合成 DXY。
    公式：50.14348112 × EURUSD^-0.576 × USDJPY^0.136 × GBPUSD^-0.119
          × USDCAD^0.091 × USDSEK^0.042 × USDCHF^0.036
    與真實 DXY 期貨可能有極小誤差，但足夠日常監測方向判斷。
    """
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


def fetch_silver_rsi(api_key, period=14):
    """選用功能：需要 gold-api.com 免費 API Key（見側邊欄說明）。
    用 /history 端點抓近30天白銀日均價計算 RSI。免費額度 10 req/hr，每日跑一次完全足夠。
    """
    import time

    end_ts = int(time.time())
    start_ts = end_ts - 40 * 86400
    r = requests.get(
        "https://api.gold-api.com/history",
        params={
            "symbol": "XAG",
            "startTimestamp": start_ts,
            "endTimestamp": end_ts,
            "groupBy": "day",
            "aggregation": "avg",
            "orderBy": "asc",
        },
        headers={**HEADERS, "x-api-key": api_key},
        timeout=10,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows or len(rows) < period + 1:
        raise ValueError("歷史資料不足以計算 RSI")
    closes = pd.Series([row["avg_price"] for row in rows])
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


@st.cache_data(ttl=1800)  # 30分鐘快取
def fetch_market_data(rsi_api_key):
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

    rsi = None
    if rsi_api_key:
        try:
            rsi = fetch_silver_rsi(rsi_api_key)
        except Exception as e:
            errors.append(f"白銀 RSI 抓取失敗（不影響其他數據）：{e}")

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

# 側邊欄：上海銀溢價手動輸入 ＋ 選用 RSI API Key
st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 (%)", value=12.22, step=0.1, help="請輸入今日最新的真實溢價數據"
)
st.sidebar.markdown(
    "👉 **[點此查看 GoldSilver.ai 即時溢價](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 選用：白銀 RSI")
rsi_key = st.sidebar.text_input(
    "gold-api.com API Key（選填）",
    type="password",
    help="到 https://gold-api.com 免費註冊即可取得，才會計算白銀日線RSI。不填就只是少這一項，其餘功能正常。",
)

market_data, fetch_errors = fetch_market_data(rsi_key or None)

if fetch_errors and market_data is None:
    st.error("⚠️ 資料抓取失敗，請稍後再試：")
    for e in fetch_errors:
        st.code(e)
elif fetch_errors:
    with st.expander("⚠️ 部分數據抓取異常，點此查看細節"):
        for e in fetch_errors:
            st.code(e)

if market_data:
    st.caption(f"現貨資料時間：{market_data['as_of']}　|　查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.markdown("### 📍 當日核心市場數據")

    col1, col2, col3 = st.columns(3)
    col1.metric("現貨銀價 (Spot)", f"${market_data['spot_silver']}")
    col2.metric("現貨金價 (Spot)", f"${market_data['spot_gold']}")
    col3.metric("合成 DXY", market_data["dxy"] if market_data["dxy"] is not None else "查詢失敗")

    col4, col5, col6 = st.columns(3)
    col4.metric("金銀比 (GSR)", f"{market_data['gsr']}")
    col5.metric("上海銀溢價 (手動)", f"{sh_premium}%")
    col6.metric("白銀 RSI(14)", market_data["rsi"] if market_data["rsi"] is not None else "未設定 Key")

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
    "現貨金銀價由 gold-api.com 提供；DXY 為依 ICE 官方公式重建的合成指數，與真實期貨報價可能有小幅誤差；"
    "上海銀溢價需手動輸入。僅供研究參考，不構成投資建議。"
)

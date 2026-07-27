import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import calendar

st.set_page_config(
    page_title="金銀市場與套利監測(自動化版)", page_icon="🪙", layout="centered"
)

st.markdown(
    "<h1>🪙 每日金銀市場與套利監測<br>"
    "<span style='font-size: 0.55em; color: grey;'>Daily Gold & Silver Market and Monitor</span></h1>", 
    unsafe_allow_html=True
)
st.caption("數據來源：gold-api.com（現貨）＋ Frankfurter（DXY）＋ CoinGecko（RSI/5日波段）")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- 重大數據曆法推算模組 ---
def get_next_nfp(current_date):
    month, year = current_date.month, current_date.year
    c = calendar.monthcalendar(year, month)
    first_friday_day = c[0][4] if c[0][4] != 0 else c[1][4]
    first_friday = date(year, month, first_friday_day)
    
    if current_date > first_friday:
        month = 1 if month == 12 else month + 1
        year = year + 1 if month == 1 else year
        c = calendar.monthcalendar(year, month)
        first_friday_day = c[0][4] if c[0][4] != 0 else c[1][4]
        first_friday = date(year, month, first_friday_day)
    return first_friday

def get_next_cpi(current_date):
    month, year = current_date.month, current_date.year
    cpi_date = date(year, month, 13)
    
    if cpi_date.weekday() == 5: 
        cpi_date = date(year, month, 12)
    elif cpi_date.weekday() == 6: 
        cpi_date = date(year, month, 14)
        
    if current_date > cpi_date:
        month = 1 if month == 12 else month + 1
        year = year + 1 if month == 1 else year
        cpi_date = date(year, month, 13)
        if cpi_date.weekday() == 5:
            cpi_date = date(year, month, 12)
        elif cpi_date.weekday() == 6:
            cpi_date = date(year, month, 14)
    return cpi_date

# --- API 抓取模組 ---
def fetch_metal_price(symbol):
    r = requests.get(f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"]), data.get("updatedAt")

def fetch_synthetic_dxy():
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
    ) - 0.2  
    return dxy

def fetch_crypto_history(coin_id, days):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily"
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json().get("prices", [])

@st.cache_data(ttl=1800)
def fetch_market_data():
def send_telegram_alert(message):
    # 請替換為您的真實 Token 與 Chat ID
    bot_token = "8850511159:AAFygXc9GaX6Mhjry4y_57tfKXA13t5IilU" 
    chat_id = "5259644398"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown" # 支援簡單排版
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        # 即使推播失敗，也不要讓整個儀表板當機
        pass
    errors = []

    try:
        silver_spot, silver_ts = fetch_metal_price("XAG")
        gold_spot, gold_ts = fetch_metal_price("XAU")
    except Exception as e:
        errors.append(f"gold-api.com 抓取失敗：{e}")
        return None, errors

    try:
        dxy = fetch_synthetic_dxy()
    except Exception as e:
        errors.append(f"合成 DXY 計算失敗：{e}")
        dxy = None

    rsi = silver_past = silver_high = silver_low = None
    gold_past = gold_high = gold_low = None
    
    try:
        ag_hist = fetch_crypto_history("kinesis-silver", 30)
        if ag_hist and len(ag_hist) >= 15:
            closes = pd.Series([p[1] for p in ag_hist])
            delta = closes.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            rs = gain.rolling(14).mean() / loss.rolling(14).mean()
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        if ag_hist and len(ag_hist) >= 6:
            recent_5d = [p[1] for p in ag_hist[-6:]]
            silver_past = recent_5d[0]
            silver_high = max(recent_5d)
            silver_low = min(recent_5d)
            
        au_hist = fetch_crypto_history("pax-gold", 6)
        if au_hist and len(au_hist) > 0:
            recent_5d = [p[1] for p in au_hist]
            gold_past = recent_5d[0]
            gold_high = max(recent_5d)
            gold_low = min(recent_5d)
            
    except Exception as e:
        errors.append(f"CoinGecko 歷史數據抓取失敗：{e}")

    gsr = round(gold_spot / silver_spot, 2) if silver_spot else None

    return {
        "spot_silver": round(silver_spot, 2) if silver_spot else None,
        "spot_gold": round(gold_spot, 2) if gold_spot else None,
        "dxy": round(dxy, 2) if dxy is not None else None,
        "gsr": gsr,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "silver_past": silver_past,
        "silver_high": silver_high,
        "silver_low": silver_low,
        "gold_past": gold_past,
        "gold_high": gold_high,
        "gold_low": gold_low,
        "as_of": silver_ts,
    }, errors

def calc_fibonacci(current, past, high, low):
    if any(v is None for v in [current, past, high, low]):
        return "資料不足", None
    
    diff = high - low
    if diff == 0:
        return "盤整 ➖", round(current, 2)
        
    if current > past:
        fib = high - (diff * 0.618)
        return "回撤支撐", round(fib, 2)
    elif current < past:
        fib = low + (diff * 0.618)
        return "反彈壓力", round(fib, 2)
    else:
        return "盤整", round(current, 2)

if st.button("🔄 重新查詢", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# --- 側邊欄設計 ---
st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 Premium (%)", value=12.22, step=0.1, help="請輸入今日最新的真實溢價數據"
)
st.sidebar.markdown(
    "👉 **[點此查看 GoldSilver.ai 即時溢價](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 警示門檻微調")
st.sidebar.caption("滑動以調整您的個人交易策略觸發點")

gsr_upper = st.sidebar.slider("GSR 高估門檻 (賣金買銀)", min_value=65.0, max_value=95.0, value=80.0, step=0.5)
gsr_lower = st.sidebar.slider("GSR 低估門檻 (賣銀買金)", min_value=40.0, max_value=65.0, value=50.0, step=0.5)

st.sidebar.markdown("<br>", unsafe_allow_html=True)
premium_upper = st.sidebar.slider("溢價極端門檻 (%)", min_value=15.0, max_value=30.0, value=20.0, step=0.5)
premium_lower = st.sidebar.slider("溢價收斂門檻 (%)", min_value=0.0, max_value=15.0, value=10.0, step=0.5)


# --- 執行抓取 ---
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
    st.caption(f"查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    st.markdown("### 📍 當日核心市場數據")
    col1, col2, col3 = st.columns(3)
    col1.metric("🥈 現貨銀價 Silver (Spot)", f"${market_data['spot_silver']}")
    col2.metric("🥇 現貨金價 GOLD (Spot)", f"${market_data['spot_gold']}")
    col3.metric("💵 合成 DXY (校正)", market_data["dxy"] if market_data["dxy"] is not None else "查詢失敗")

    col4, col5, col6 = st.columns(3)
    col4.metric("⚖️ 金銀比 (GSR)", f"{market_data['gsr']}")
    col5.metric("🇨🇳 上海銀溢價 Premium (手動)", f"{sh_premium}%")
    col6.metric("📈 白銀 Silver RSI(14)", market_data["rsi"] if market_data["rsi"] is not None else "資料不足")

    st.markdown("<div style='text-align: right;'><a href='https://goldsilver.ai/metal-prices/shanghai-silver-price' target='_blank'>🔗 前往確認上海銀真實溢價</a></div>", unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("### 📐 5日波段 0.618 關鍵價位 (支撐/壓力)")
    st.caption("自動抓取近5日高低點。趨勢向上時提供「回撤防守支撐」，趨勢向下時提供「反彈解套壓力」。")
    
    fib_col1, fib_col2 = st.columns(2)
    
    with fib_col1:
        st.markdown("**【白銀 XAG】**")
        if market_data['silver_past']:
            ag_type, ag_fib = calc_fibonacci(
                market_data['spot_silver'], market_data['silver_past'], 
                market_data['silver_high'], market_data['silver_low']
            )
            st.metric(f"5日區間: ${round(market_data['silver_low'], 2)} - ${round(market_data['silver_high'], 2)}", f"型態: {ag_type}")
            if "支撐" in ag_type:
                st.info(f"🛡️ 0.618 防守支撐: **${ag_fib}**")
            elif "壓力" in ag_type:
                st.error(f"🛑 0.618 反彈壓力: **${ag_fib}**")
        else:
            st.warning("缺乏歷史數據")

    with fib_col2:
        st.markdown("**【黃金 XAU】**")
        if market_data['gold_past']:
            au_type, au_fib = calc_fibonacci(
                market_data['spot_gold'], market_data['gold_past'], 
                market_data['gold_high'], market_data['gold_low']
            )
            st.metric(f"5日區間: ${round(market_data['gold_low'], 2)} - ${round(market_data['gold_high'], 2)}", f"型態: {au_type}")
            if "支撐" in au_type:
                st.info(f"🛡️ 0.618 防守支撐: **${au_fib}**")
            elif "壓力" in au_type:
                st.error(f"🛑 0.618 反彈壓力: **${au_fib}**")
        else:
            st.warning("缺乏歷史數據")

    st.markdown("---")
    
    st.markdown("### 🚨 當日套利與轉置建議")
    
    today = datetime.now().date()
    next_nfp = get_next_nfp(today)
    next_cpi = get_next_cpi(today)
    
    st.info(
        f"⏱️ **現貨資料時間：** {market_data['as_of']}\n\n"
        f"📅 **下次重大數據：** 非農 (NFP) `{next_nfp.strftime('%Y-%m-%d')}` ｜ CPI 預測 `{next_cpi.strftime('%Y-%m-%d')}`\n\n"
        f"*(註：此日期為系統推斷，如遇美國假日或特殊情況，官方實際發布日可能提前或順延)*"
    )

    if market_data["gsr"] >= gsr_upper:
        st.error(f"【GSR 警示】金銀比達 {market_data['gsr']}（>= {gsr_upper}）。白銀相對嚴重低估，建議考慮「賣金買銀」。")
    elif market_data["gsr"] <= gsr_lower:
        st.warning(f"【GSR 警示】金銀比達 {market_data['gsr']}（<= {gsr_lower}）。白銀相對昂貴，建議「賣銀買金」。")
    else:
        st.info(f"【GSR 狀態】金銀比為 {market_data['gsr']}，目前位於中性區間。")

    if sh_premium >= premium_upper:
        st.error(f"【溢價警示】上海銀溢價達 {sh_premium}%！中國實體需求極強（>= {premium_upper}%），建議避開 COMEX 空單。")
    elif sh_premium <= premium_lower:
        st.success(f"【溢價狀態】上海銀溢價為 {sh_premium}%（<= {premium_lower}%）。東西方定價收斂，無顯著跨市套利空間。")
    else:
        st.warning(f"【溢價狀態】上海銀溢價為 {sh_premium}%，處於過渡區間，需求偏強但未達極端門檻。")
        # 🚨 當日套利與轉置建議
    st.markdown("### 🚨 當日套利與轉置建議")
    
    # ... (保留您原本的日期推斷與提示文字) ...

    # 初始化推播記錄，避免重新整理網頁時重複發送
    if "alert_sent" not in st.session_state:
        st.session_state.alert_sent = False

    # GSR 判斷邏輯
    if market_data["gsr"] >= gsr_upper:
        msg = f"【GSR 警示】金銀比達 {market_data['gsr']}（>= {gsr_upper}）。白銀相對嚴重低估，建議考慮「賣金買銀」。"
        st.error(msg)
        if not st.session_state.alert_sent:
            send_telegram_alert(f"🚨 *戰情室快訊* 🚨\n\n{msg}")
            st.session_state.alert_sent = True
            
    elif market_data["gsr"] <= gsr_lower:
        msg = f"【GSR 警示】金銀比達 {market_data['gsr']}（<= {gsr_lower}）。白銀相對昂貴，建議「賣銀買金」。"
        st.warning(msg)
        if not st.session_state.alert_sent:
            send_telegram_alert(f"⚠️ *戰情室快訊* ⚠️\n\n{msg}")
            st.session_state.alert_sent = True
    else:
        st.info(f"【GSR 狀態】金銀比為 {market_data['gsr']}，目前位於中性區間。")

    # 溢價判斷邏輯
    if sh_premium >= premium_upper:
        msg = f"【溢價警示】上海銀溢價達 {sh_premium}%！中國實體需求極強（>= {premium_upper}%），建議避開 COMEX 空單。"
        st.error(msg)
        if not st.session_state.alert_sent:
            send_telegram_alert(f"🚨 *戰情室快訊* 🚨\n\n{msg}")
            st.session_state.alert_sent = True
            
    elif sh_premium <= premium_lower:
        st.success(f"【溢價狀態】上海銀溢價為 {sh_premium}%（<= {premium_lower}%）。東西方定價收斂，無顯著跨市套利空間。")
    else:
        st.warning(f"【溢價狀態】上海銀溢價為 {sh_premium}%，處於過渡區間，需求偏強但未達極端門檻。")

st.divider()
st.caption(
    "現貨金銀價由 gold-api.com 提供；DXY 為合成指數(-0.2)；白銀 RSI 與 5日波段由 CoinGecko 抓取實體代幣換算。"
    "重大事件日期為程式自動推算。僅供研究參考，不構成投資建議。"
)

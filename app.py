import threading
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import calendar
from deep_translator import GoogleTranslator

st.set_page_config(
    page_title="金銀市場與套利監測(自動化版)", page_icon="🪙", layout="centered"
)

st.markdown(
    "<h1>🪙 每日金銀市場與套利監測<br>"
    "<span style='font-size: 0.55em; color: grey;'>Daily Gold & Silver Market and Monitor</span></h1>", 
    unsafe_allow_html=True
)
st.caption("數據來源：gold-api.com（現貨）10/m＋ Frankfurter（DXY）1/3m＋ CoinGecko（RSI/5日波段）1/10m")
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}

import json
import os

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"sh_premium": 12.22, "trading_note": ""}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_premium_cb():
    data = load_data()
    data["sh_premium"] = st.session_state.sh_premium_val
    save_data(data)

def update_note_cb():
    data = load_data()
    data["trading_note"] = st.session_state.trading_note_val
    save_data(data)

saved_data = load_data()

if "sh_premium_val" not in st.session_state:
    st.session_state.sh_premium_val = saved_data.get("sh_premium", 12.22)

if "trading_note_val" not in st.session_state:
    st.session_state.trading_note_val = saved_data.get("trading_note", "")

# --- Telegram 憑證：改用 st.secrets 讀取，不再寫死在程式碼裡 ---
# 部署前請到 Streamlit Cloud → Manage app → Settings → Secrets 貼入：
#   BOT_TOKEN = "你的機器人token"
#   ALLOWED_CHAT_ID = "你的chat id"
# 本機測試則在專案根目錄建立 .streamlit/secrets.toml 放相同內容（記得加進 .gitignore，不要上傳）
try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    ALLOWED_CHAT_ID = str(st.secrets["ALLOWED_CHAT_ID"])
except Exception:
    BOT_TOKEN = None
    ALLOWED_CHAT_ID = None
    st.sidebar.error("⚠️ 尚未設定 Telegram Secrets，推播與雙向控制功能停用。請至 App 設定新增 BOT_TOKEN / ALLOWED_CHAT_ID。")

async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): 
        return
    await update.message.reply_text(
        "🪙 *金銀戰情室控制台已連線！*\n\n"
        "指令列表：\n"
        "1. `/p 12.35` ：更新溢價\n"
        "2. `/note 內容` ：更新筆記\n"
        "3. `/get` ：查詢當前設定",
        parse_mode="Markdown"
    )

async def tg_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    if not context.args:
        await update.message.reply_text("⚠️ 請輸入數值，範例：`/p 12.35`", parse_mode="Markdown")
        return
    try:
        raw_val = context.args[0].replace("%", "")
        val = float(raw_val)
        data = load_data()
        data["sh_premium"] = val
        save_data(data)
        st.session_state.sh_premium_val = val
        await update.message.reply_text(f"✅ 上海銀溢價已更新為：*{val}%*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ 請輸入有效的數字格式！")

async def tg_set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("⚠️ 請輸入內容，範例：`/note hawkish FED`", parse_mode="Markdown")
        return
        
    try:
        from deep_translator import GoogleTranslator
        
        # 1. 執行多國語言翻譯 (自動偵測輸入語言)
        trans_zh = GoogleTranslator(source='auto', target='zh-TW').translate(text)
        trans_en = GoogleTranslator(source='auto', target='en').translate(text)
        trans_vi = GoogleTranslator(source='auto', target='vi').translate(text)
        
        # 2. 組合多語種筆記格式
        final_note = f"【原文】{text}\n【中】{trans_zh}\n【EN】{trans_en}\n【VN】{trans_vi}"
        
        # 3. 存入 JSON 檔案 (供 Streamlit 網頁下次重整時讀取)
        data = load_data()
        data["trading_note"] = final_note
        save_data(data)
        
        # 4. 回傳給 Telegram
        await update.message.reply_text(f"📝 *多語翻譯完成並寫入！*\n\n`{final_note}`", parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ 翻譯或存檔失敗：{e}")
        
async def tg_get_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    data = load_data()
    await update.message.reply_text(
        f"📊 *當前戰情室參數：*\n\n"
        f"🇨🇳 上海銀溢價：`{data.get('sh_premium')}%`\n"
        f"📝 交易筆記：\n`{data.get('trading_note')}`",
        parse_mode="Markdown"
    )

def run_bot_thread():
    # 設定獨立的 Event Loop，避免 Streamlit 衝突
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
        bot_app.add_handler(CommandHandler("start", tg_start))
        bot_app.add_handler(CommandHandler(["p", "premium"], tg_set_premium))
        bot_app.add_handler(CommandHandler("note", tg_set_note))
        bot_app.add_handler(CommandHandler("get", tg_get_status))
        # 關鍵修正：stop_signals=None
        # run_polling() 預設會嘗試註冊 SIGINT/SIGTERM 訊號處理器，
        # 但訊號處理器只能在「主執行緒」註冊；這裡是背景執行緒，不設 stop_signals=None
        # 會直接丟出 ValueError 讓這條 thread 靜默死掉（daemon thread 例外不會顯示在畫面上）。
        bot_app.run_polling(drop_pending_updates=True, stop_signals=None)
    except Exception as e:
        # 印出錯誤，方便到 Streamlit Cloud 的 Manage app → Logs 查看，不再靜默失敗
        print(f"[Telegram Bot Thread Error] {e}")

# 啟動背景執行緒（只在「整個伺服器程序」啟動時執行一次，而不是每個使用者連線都各自啟動一次）
# 注意：原本用 st.session_state 判斷是「每個瀏覽器分頁/使用者」各自的狀態，
# 如果同時有兩個 session 都判斷「尚未啟動」，會同時起兩條 thread 對同一個 BOT_TOKEN 做 polling，
# Telegram 只允許同時一個 polling 連線，會導致 Conflict 錯誤。改用全域旗標避免重複啟動。
if BOT_TOKEN and ALLOWED_CHAT_ID:
    if "_bot_thread_started" not in globals():
        globals()["_bot_thread_started"] = True
        threading.Thread(target=run_bot_thread, daemon=True).start()

def send_telegram_alert(message):
    if not BOT_TOKEN or not ALLOWED_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ALLOWED_CHAT_ID,
        "text": message
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            st.sidebar.error(f"Telegram API 錯誤: {r.text}")
            return False
        return True
    except Exception as e:
        st.sidebar.error(f"連線異常: {e}")
        return False

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

def fetch_metal_price(symbol):
    r = requests.get(f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"]), data.get("updatedAt")

@st.cache_data(ttl=300)
def fetch_synthetic_dxy():
    try:
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
    except Exception:
        return None

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
    except Exception as e:
        errors.append(f"CoinGecko 白銀歷史抓取失敗 (可能觸發429限流)：{e}")

    try:
        au_hist = fetch_crypto_history("pax-gold", 6)
        if au_hist and len(au_hist) > 0:
            recent_5d = [p[1] for p in au_hist]
            gold_past = recent_5d[0]
            gold_high = max(recent_5d)
            gold_low = min(recent_5d)
    except Exception as e:
        errors.append(f"CoinGecko 黃金歷史抓取失敗 (可能觸發429限流)：{e}")

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
        return "資料不足 (限流保護中)", None
    
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
    st.toast("已清除 API 快取並更新數據！", icon="✅")

st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 Premium (%)", step=0.1, 
    help="請輸入今日最新的真實溢價數據",
    key="sh_premium_val",
    on_change=update_premium_cb
)
st.sidebar.markdown(
    "👉 **[ 即時溢價premium中國倫敦價差](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 警示門檻微調")
st.sidebar.caption("滑動以調整您的個人交易策略觸發點")

gsr_upper = st.sidebar.slider("GSR 高估門檻 (賣金買銀)", min_value=65.0, max_value=95.0, value=80.0, step=0.5, key="gsr_upper_val")
gsr_lower = st.sidebar.slider("GSR 低估門檻 (賣銀買金)", min_value=40.0, max_value=65.0, value=50.0, step=0.5, key="gsr_lower_val")

st.sidebar.markdown("<br>", unsafe_allow_html=True)
premium_upper = st.sidebar.slider("溢價極端門檻 (%)", min_value=15.0, max_value=30.0, value=20.0, step=0.5, key="premium_upper_val")
premium_lower = st.sidebar.slider("溢價收斂門檻 (%)", min_value=0.0, max_value=15.0, value=10.0, step=0.5, key="premium_lower_val")

st.sidebar.markdown("---")
st.sidebar.header("🛠️ 工具與個人戰術筆記")

with st.sidebar.expander("📱 Telegram 測試推播"):
    if st.button("📤 發送測試訊息", use_container_width=True):
        success = send_telegram_alert("🔔 *這是一則來自金銀戰情室的手動測試推播！* 🚀")
        if success:
            st.success("推播發送成功！請檢查手機。")
        else:
            st.error("發送失敗，請檢查 Token 或 Chat ID。")

with st.sidebar.expander("📖 Setup Telegram 設定？"):
    st.markdown("""
    **1. 建立 Telegram 機器人**
    * 在 Telegram 搜尋 `@BotFather` 並發送 `/newbot`
    * 複製獲得的 **API Token**
    
    **2. 取得 Chat ID**
    * 在 Telegram 搜尋 `@userinfobot` 發送 `/start` 取得 ID
    
    **3. 啟用機器人**
    * 搜尋您的 Bot Username，點擊 **`Start`** (發送 `/start`)
    """)

with st.sidebar.expander("📝 教戰手則 & 臨時筆記"):
    st.markdown("**【個人核心交易紀律】**")
    st.caption("1. 達極端溢價時避開 COMEX 空單\n2. GSR 突破門檻分批套利\n3. 嚴格執行止損")
    st.markdown("---")
    user_note = st.text_area(
        "輸入臨時心得（自動記憶）：",
        height=120,
        placeholder="例如：美盤開盤注意 CPI 數據...",
        key="trading_note_val",
        on_change=update_note_cb
    )
    
market_data, fetch_errors = fetch_market_data()

if fetch_errors and market_data is None:
    st.error("⚠️ 資料抓取失敗，請稍後再試：")
    for e in fetch_errors:
        st.code(e)
elif fetch_errors:
    with st.expander("⚠️ 部分數據抓取異常 (可能因短時間重新整理過多觸發 CoinGecko 429 限制)"):
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
    col5.metric("📈 白銀 Silver RSI(14)", market_data["rsi"] if market_data["rsi"] is not None else "資料不足")
    col6.metric("🇨🇳 銀溢價 Premium (手動/manual)", f"{st.session_state.sh_premium_val}%")


    st.markdown("<div style='text-align: right;'><a href='https://goldsilver.ai/metal-prices/shanghai-silver-price' target='_blank'>🔗 搜尋銀真實溢價To check the premium</a></div>", unsafe_allow_html=True)

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
            st.warning("缺乏歷史數據 (等待 CoinGecko 解除 429 限制)")

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
            st.warning("缺乏歷史數據 (等待 CoinGecko 解除 429 限制)")

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

    if "last_gsr_upper" not in st.session_state:
        st.session_state.last_gsr_upper = gsr_upper
    if "last_gsr_lower" not in st.session_state:
        st.session_state.last_gsr_lower = gsr_lower
    if "alert_sent_state" not in st.session_state:
        st.session_state.alert_sent_state = None

    if gsr_upper != st.session_state.last_gsr_upper or gsr_lower != st.session_state.last_gsr_lower:
        st.session_state.alert_sent_state = None
        st.session_state.last_gsr_upper = gsr_upper
        st.session_state.last_gsr_lower = gsr_lower

    current_alert = None
    if market_data["gsr"] >= gsr_upper:
        msg = f"【GSR 警示】金銀比達 {market_data['gsr']}（>= {gsr_upper}）。白銀相對嚴重低估，建議考慮「賣金買銀」。「sell GOLD to buy SILVER」"
        st.error(msg)
        current_alert = "gsr_high"
    elif market_data["gsr"] <= gsr_lower:
        msg = f"【GSR 警示】金銀比達 {market_data['gsr']}（<= {gsr_lower}）。白銀相對昂貴，建議專注「賣銀買金」。「sell SILVER to buy GOLD」"
        st.warning(msg)
        current_alert = "gsr_low"
    else:
        st.info(f"【GSR 狀態】金銀比為 {market_data['gsr']}，目前位於中性區間。")
        current_alert = "neutral"

    if current_alert != st.session_state.alert_sent_state:
        if current_alert in ["gsr_high", "gsr_low"]:
            send_telegram_alert(f"🚨 *戰情室即時快訊* 🚨\n\n{msg}")
        st.session_state.alert_sent_state = current_alert

    if st.session_state.sh_premium_val >= premium_upper:
        msg_p = f"【溢價警示】上海銀溢價達 {st.session_state.sh_premium_val}%！中國實體需求極強（>= {premium_upper}%），建議避開 COMEX 空單。"
        st.error(msg_p)
        send_telegram_alert(f"🚨 *戰情室快訊* 🚨\n\n{msg_p}")
    elif st.session_state.sh_premium_val <= premium_lower:
        st.success(f"【溢價狀態】上海銀溢價為 {st.session_state.sh_premium_val}%（<= {premium_lower}%）。東西方定價收斂，無顯著跨市套利空間。")
    else:
        st.warning(f"【溢價狀態】上海銀溢價為 {st.session_state.sh_premium_val}%，處於過渡區間，需求偏強但未達極端門檻。")

st.divider()
st.caption(
    "現貨金銀價由 gold-api.com 提供；DXY 為合成指數(-0.2)；白銀 RSI 與 5日波段由 CoinGecko 抓取實體代幣換算。"
    "重大事件日期為程式自動推算。僅供研究參考，不構成投資建議。"
)

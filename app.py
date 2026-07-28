import threading
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import calendar
import json
import os
from deep_translator import GoogleTranslator
import re

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
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "chat_history" not in data: data["chat_history"] = []
                if "trading_note" not in data: data["trading_note"] = ""
                return data
        except Exception:
            pass
    return {"sh_premium": 12.22, "trading_note": "", "chat_history": []}

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

# 每次重新整理或查詢時，強制同步最新資料到 session_state
saved_data = load_data()
st.session_state.sh_premium_val = saved_data.get("sh_premium", 12.22)
st.session_state.trading_note_val = saved_data.get("trading_note", "")

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    ALLOWED_CHAT_ID = str(st.secrets["ALLOWED_CHAT_ID"])
except Exception:
    BOT_TOKEN = None
    ALLOWED_CHAT_ID = None
    st.sidebar.error("⚠️ 尚未設定 Telegram Secrets，推播與雙向控制功能停用。")

# --- Telegram 機器人非同步控制函數 ---
async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    await update.message.reply_text(
        "🪙 *金銀戰情室控制台已連線！*\n\n"
        "指令列表：\n"
        "1. `/p 12.35` ：更新溢價\n"
        "2. `/n` 或 `/note` ：新增純文字筆記\n"
        "3. `/t` 或 `/trans` ：多國語言自動翻譯並寫入聊天室\n"
        "4. `/get` ：查詢當前設定與近期對話",
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
        await update.message.reply_text(f"✅ 上海銀溢價已更新為：*{val}%*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ 請輸入有效的數字格式！")

async def tg_set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("⚠️ 請輸入內容，範例：`/n 今天觀望`", parse_mode="Markdown")
        return
    data = load_data()
    data["trading_note"] = text
    save_data(data)
    await update.message.reply_text(f"📝 *純文字筆記已更新：*\n\n`{text}`", parse_mode="Markdown")

async def tg_set_trans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("⚠️ 請輸入內容，範例：`/t hawkish FED`", parse_mode="Markdown")
        return
    try:
        src_lang = 'zh-TW' if re.search(r'[\u4e00-\u9fa5]', text) else 'auto'
        trans_zh = GoogleTranslator(source=src_lang, target='zh-TW').translate(text)
        trans_en = GoogleTranslator(source=src_lang, target='en').translate(text)
        trans_vi = GoogleTranslator(source=src_lang, target='vi').translate(text)
        
        # 精簡雙行格式
        final_msg = f"🇬🇧 {trans_en}\n\n🇨🇳 {trans_zh} ｜ 🇻🇳 {trans_vi}"
    except Exception:
        final_msg = f"🇬🇧 {text}\n\n*(⚠️ 翻譯失敗)*"
    
    data = load_data()
    if "chat_history" not in data: data["chat_history"] = []
    data["chat_history"].append(final_msg)
    if len(data["chat_history"]) > 20:
        data["chat_history"].pop(0)
    save_data(data)
    
    await update.message.reply_text(f"🌐 *新對話已同步加入聊天室！*\n\n{final_msg}", parse_mode="Markdown")

async def tg_get_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip(): return
    data = load_data()
    
    # 正確讀取 chat_history 陣列中的最後幾則對話
    history = data.get("chat_history", [])
    if history:
        # 取出最近 3 則對話並組合成字串
        chat_str = "\n\n---\n\n".join(history[-3:])
    else:
        chat_str = "目前無對話紀錄"
    
    await update.message.reply_text(
        f"📊 *當前戰情室參數：*\n\n"
        f"🇨🇳 上海銀溢價：`{data.get('sh_premium')}%`\n\n"
        f"📝 純文字筆記：\n`{data.get('trading_note')}`\n\n"
        f"🌐 *最近對話紀錄牆：*\n{chat_str}",
        parse_mode="Markdown"
    )

# --- 常駐背景 Bot 啟動器 ---
@st.cache_resource
def init_telegram_bot(token):
    if not token: return
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            app = ApplicationBuilder().token(token).build()
            app.add_handler(CommandHandler("start", tg_start))
            app.add_handler(CommandHandler(["p", "premium"], tg_set_premium))
            app.add_handler(CommandHandler(["n", "note"], tg_set_note))
            app.add_handler(CommandHandler(["t", "trans"], tg_set_trans))
            app.add_handler(CommandHandler("get", tg_get_status))
            app.run_polling(drop_pending_updates=True, stop_signals=None)
        except Exception as e:
            print(f"Bot Error: {e}")

    t = threading.Thread(target=run, daemon=True)
    t.start()

if BOT_TOKEN:
    init_telegram_bot(BOT_TOKEN)

def send_telegram_alert(message):
    if not BOT_TOKEN or not ALLOWED_CHAT_ID: return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": ALLOWED_CHAT_ID, "text": message}, timeout=10)
        return r.status_code == 200
    except Exception:
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
    if cpi_date.weekday() == 5: cpi_date = date(year, month, 12)
    elif cpi_date.weekday() == 6: cpi_date = date(year, month, 14)
    if current_date > cpi_date:
        month = 1 if month == 12 else month + 1
        year = year + 1 if month == 1 else year
        cpi_date = date(year, month, 13)
        if cpi_date.weekday() == 5: cpi_date = date(year, month, 12)
        elif cpi_date.weekday() == 6: cpi_date = date(year, month, 14)
    return cpi_date

def fetch_metal_price(symbol):
    r = requests.get(f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return float(data["price"]), data.get("updatedAt")

@st.cache_data(ttl=300)
def fetch_synthetic_dxy():
    try:
        r = requests.get("https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,JPY,GBP,CAD,SEK,CHF", headers=HEADERS, timeout=10)
        r.raise_for_status()
        rates = r.json()["rates"]
        dxy = (
            50.14348112
            * ((1 / rates["EUR"]) ** -0.576)
            * (rates["JPY"] ** 0.136)
            * ((1 / rates["GBP"]) ** -0.119)
            * (rates["CAD"] ** 0.091)
            * (rates["SEK"] ** 0.042)
            * (rates["CHF"] ** 0.036)
        ) - 0.2
        return dxy
    except Exception:
        return None

def fetch_crypto_history(coin_id, days):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days), "interval": "daily"}
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
        errors.append(f"CoinGecko 白銀歷史抓取失敗：{e}")

    try:
        au_hist = fetch_crypto_history("pax-gold", 6)
        if au_hist and len(au_hist) > 0:
            recent_5d = [p[1] for p in au_hist]
            gold_past = recent_5d[0]
            gold_high = max(recent_5d)
            gold_low = min(recent_5d)
    except Exception as e:
        errors.append(f"CoinGecko 黃金歷史抓取失敗：{e}")

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

if st.button("🔄 重新查詢", use_container_width=True):
    st.cache_data.clear()
    st.toast("已清除 API 快取並更新數據！", icon="✅")

st.sidebar.header("📌 上海銀溢價輸入區")
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 Premium (%)", step=0.1, 
    key="sh_premium_val",
    on_change=update_premium_cb
)
st.sidebar.markdown("👉 **[ 即時溢價premium中國倫敦價差](https://goldsilver.ai/metal-prices/shanghai-silver-price)**")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 警示門檻微調")
gsr_upper = st.sidebar.slider("GSR 高估門檻 (賣金買銀)", 65.0, 95.0, 80.0, 0.5, key="gsr_upper_val")
gsr_lower = st.sidebar.slider("GSR 低估門檻 (賣銀買金)", 40.0, 65.0, 50.0, 0.5, key="gsr_lower_val")
premium_upper = st.sidebar.slider("溢價極端門檻 (%)", 15.0, 30.0, 20.0, 0.5, key="premium_upper_val")
premium_lower = st.sidebar.slider("溢價收斂門檻 (%)", 0.0, 15.0, 10.0, 0.5, key="premium_lower_val")

st.sidebar.markdown("---")
st.sidebar.header("🛠️ 工具與個人戰術筆記")

with st.sidebar.expander("📝 教戰手則 & 臨時筆記", expanded=True):
    st.markdown("**【個人核心交易紀律】**")
    st.caption("1. 達極端溢價時避開 COMEX 空單\n2. GSR 突破門檻分批套利\n3. 嚴格執行止損")
    st.markdown("---")
    st.text_area("✍️ 輸入臨時心得（純紀錄）：", height=100, key="trading_note_val", on_change=update_note_cb)

market_data, fetch_errors = fetch_market_data()

if fetch_errors and market_data is None:
    st.error("⚠️ 資料抓取失敗：")
    for e in fetch_errors: st.code(e)

if market_data:
    st.caption(f"查詢時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.markdown("### 📍 當日核心市場數據")
    c1, c2, c3 = st.columns(3)
    c1.metric("🥈 現貨銀價 Silver (Spot)", f"${market_data['spot_silver']}")
    c2.metric("🥇 現貨金價 GOLD (Spot)", f"${market_data['spot_gold']}")
    c3.metric("💵 合成 DXY (校正)", market_data["dxy"] if market_data["dxy"] is not None else "查詢失敗")

    c4, c5, c6 = st.columns(3)
    c4.metric("⚖️ 金銀比 (GSR)", f"{market_data['gsr']}")
    c5.metric("📈 白銀 Silver RSI(14)", market_data["rsi"] if market_data["rsi"] is not None else "資料不足")
    c6.metric("🇨🇳 銀溢價 Premium", f"{st.session_state.sh_premium_val}%")

    st.markdown("---")
    st.markdown("### 🚨 當日套利與轉置建議")
    today = datetime.now().date()
    st.info(f"⏱️ **現貨資料時間：** {market_data['as_of']}\n\n📅 **下次重大數據：** 非農 `{get_next_nfp(today)}` ｜ CPI 預測 `{get_next_cpi(today)}`")

# --- 放在主畫面最下方的「多語交流聊天室 (精簡美化版)」 ---
st.markdown("---")
st.markdown("### 🌐 多語交流聊天室 (Chat & Translation Wall)")
st.caption("在此輸入訊息，系統將自動翻譯並記錄最近 20 則對話，支援 Telegram 雙向同步。")

def add_chat_cb():
    raw_text = st.session_state.get("new_chat_val", "")
    if raw_text:
        try:
            src_lang = 'zh-TW' if re.search(r'[\u4e00-\u9fa5]', raw_text) else 'auto'
            trans_zh = GoogleTranslator(source=src_lang, target='zh-TW').translate(raw_text)
            trans_en = GoogleTranslator(source=src_lang, target='en').translate(raw_text)
            trans_vi = GoogleTranslator(source=src_lang, target='vi').translate(raw_text)
            
            # 精簡雙行格式
            formatted_msg = f"🇬🇧 {trans_en}\n\n🇨🇳 {trans_zh} ｜ 🇻🇳 {trans_vi}"
        except Exception:
            formatted_msg = f"🇬🇧 {raw_text}\n\n*(⚠️ 翻譯失敗)*"
            
        data = load_data()
        if "chat_history" not in data: data["chat_history"] = []
        data["chat_history"].append(formatted_msg)
        if len(data["chat_history"]) > 20:
            data["chat_history"].pop(0)
        save_data(data)
        st.session_state.new_chat_val = ""

st.text_input("💬 輸入想翻譯交流的新訊息：", key="new_chat_val", on_change=add_chat_cb, placeholder="輸入後按 Enter 發送...")

# 渲染歷史對話牆 (美化卡片外觀)
data = load_data()
chat_history = data.get("chat_history", [])
if chat_history:
    for chat in chat_history:
        with st.container(border=True):
            st.markdown(chat)
else:
    st.info("目前尚無對話紀錄，趕快在上方輸入第一句話吧！")
    
st.divider()
st.caption("以上僅供研究參考，不構成投資建議，各人造業各人擔。")

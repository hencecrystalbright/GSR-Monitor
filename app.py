import asyncio
import calendar
import json
import os
import re
import threading
from datetime import date, datetime

from deep_translator import GoogleTranslator
import pandas as pd
import requests
import streamlit as st
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==========================================
# 1. 頁面配置與 Excel 隱蔽式 CSS 注入
# ==========================================
st.set_page_config(
    page_title="Financial_Data_Sheet_v2.4.xlsx",  # 偽裝成 Excel 檔名
    page_icon="📊",
    layout="wide",  # 寬螢幕模式更像試算表
    initial_sidebar_state="expanded",
)

# 注入 Excel 經典風格 CSS
excel_css = """
<style>
    /* 全局背景與字體 */
    .stApp {
        background-color: #F3F2F1 !important;
        font-family: "Segoe UI", "Calibri", "Microsoft JhengHei", sans-serif !important;
        color: #323130 !important;
    }
    
    /* 頂部 Header 偽裝成 Excel Ribbon 標頭 */
    header[data-testid="stHeader"] {
        background-color: #107C41 !important;
        height: 2.8rem;
    }
    header[data-testid="stHeader"] * {
        color: white !important;
    }

    /* 主標題樣式：Excel 工作表頂部風格 */
    .excel-title-bar {
        background-color: #107C41;
        color: white;
        padding: 8px 16px;
        font-size: 15px;
        font-weight: 600;
        border-radius: 2px 2px 0 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* 欄位/資料邊框：模擬 Excel 儲存格 (Grid) */
    div[data-testid="stMetric"], .stMarkdown div[data-testid="stBlock"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D1D1 !important;
        padding: 8px 12px !important;
        border-radius: 0px !important; /* 取消圓角 */
        box-shadow: none !important;
    }
    
    /* Metric 數值與標籤優化 */
    div[data-testid="stMetricLabel"] {
        font-size: 11px !important;
        color: #605E5C !important;
        text-transform: uppercase;
        font-weight: 600;
    }
    div[data-testid="stMetricValue"] {
        font-size: 18px !important;
        font-family: "Consolas", "Courier New", monospace !important;
        color: #201F1E !important;
        font-weight: bold;
    }

    /* 側邊欄：模擬 Excel 側邊參數與任務窗格 */
    section[data-testid="stSidebar"] {
        background-color: #EAE8E8 !important;
        border-right: 1px solid #C8C6C4 !important;
    }
    
    /* 容器邊框實心化（留言板與記事本） */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        border: 1px solid #C8C6C4 !important;
        border-radius: 0px !important;
        background-color: #FFFFFF !important;
    }

    /* 按鈕樣式：微軟軟體經典按鈕 */
    .stButton > button {
        background-color: #FFFFFF !important;
        color: #323130 !important;
        border: 1px solid #8A8886 !important;
        border-radius: 2px !important;
        font-size: 12px !important;
        padding: 2px 10px !important;
    }
    .stButton > button:hover {
        background-color: #EDEBE9 !important;
        border-color: #107C41 !important;
        color: #107C41 !important;
    }

    /* 輸入框樣式 */
    .stTextInput input, .stNumberInput input {
        border: 1px solid #8A8886 !important;
        border-radius: 0px !important;
        font-family: "Consolas", monospace !important;
        font-size: 13px !important;
        background-color: #FFFFFF !important;
    }
    
    /* 隱藏 Streamlit 原生頁尾浮點 */
    footer {visibility: hidden;}
</style>
"""
st.markdown(excel_css, unsafe_allow_html=True)

# ==========================================
# 2. 標題與假 UI 偽裝（式樣欄 / Formula Bar）
# ==========================================
st.markdown(
    """
    <div class="excel-title-bar">
        <span>📊 Workbook1.xlsx - Sheet1 [Market_Data_Summary]</span>
        <span style="font-size: 11px; opacity: 0.8;">AutoSave: ON | User: Analyst</span>
    </div>
    """,
    unsafe_allow_html=True,
)

HEADERS = {"User-Agent": "Mozilla/5.0"}
DATA_FILE = "data.json"

# --- 持久化儲存 logic ---
JSONBIN_API_KEY = st.secrets.get("JSONBIN_API_KEY", None)
JSONBIN_BIN_ID = st.secrets.get("JSONBIN_BIN_ID", None)
JSONBIN_URL = (
    f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}" if JSONBIN_BIN_ID else None
)
PERSIST_ENABLED = bool(JSONBIN_URL and JSONBIN_API_KEY)

if not PERSIST_ENABLED:
    st.sidebar.warning("⚠️ JSONBin 未連結 (本機暫存模式)")


def _default_data():
    return {"sh_premium": 12.22, "notes_history": [], "chat_history": []}


def _normalize(data):
    if "chat_history" not in data:
        data["chat_history"] = []
    if "notes_history" not in data:
        data["notes_history"] = []
    if "sh_premium" not in data:
        data["sh_premium"] = 12.22
    return data


def load_data():
    if PERSIST_ENABLED:
        try:
            r = requests.get(
                f"{JSONBIN_URL}/latest",
                headers={"X-Master-Key": JSONBIN_API_KEY},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("record", {})
            if not isinstance(data, dict) or not data:
                data = _default_data()
                save_data(data)
            return _normalize(data)
        except Exception as e:
            print(f"[JSONBin load error] {e}")
            return _default_data()

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return _normalize(json.load(f))
        except Exception:
            pass
    default_data = _default_data()
    save_data(default_data)
    return default_data


def save_data(data):
    if not isinstance(data, dict):
        return
    if PERSIST_ENABLED:
        try:
            requests.put(
                JSONBIN_URL,
                json=data,
                headers={
                    "X-Master-Key": JSONBIN_API_KEY,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[JSONBin save error] {e}")
        return

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_premium_cb():
    data = load_data()
    data["sh_premium"] = st.session_state.sh_premium_val
    save_data(data)


def update_note_cb():
    raw_text = st.session_state.get("trading_note_val", "")
    if raw_text.strip():
        data = load_data()
        if "notes_history" not in data:
            data["notes_history"] = []
        data["notes_history"].append(raw_text.strip())
        if len(data["notes_history"]) > 10:
            data["notes_history"].pop(0)
        save_data(data)
        st.session_state.trading_note_val = ""


saved_data = load_data()
st.session_state.sh_premium_val = saved_data.get("sh_premium", 12.22)

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    ALLOWED_CHAT_ID = str(st.secrets["ALLOWED_CHAT_ID"])
except Exception:
    BOT_TOKEN = None
    ALLOWED_CHAT_ID = None


def send_telegram_alert(message):
    if not BOT_TOKEN or not ALLOWED_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url, json={"chat_id": ALLOWED_CHAT_ID, "text": message}, timeout=10
        )
        return r.status_code == 200
    except Exception:
        return False


# --- Telegram 機器人非同步控制函數 ---
async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    await update.message.reply_text(
        "📊 *Data Console Connected*\n\n"
        "Commands:\n"
        "1. `/p 12.35` : Update Premium\n"
        "2. `/n Note` : Add memo\n"
        "3. `/t Text` : Translate & Post\n"
        "4. `/get` : Query Status",
        parse_mode="Markdown",
    )


async def tg_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    if not context.args:
        await update.message.reply_text("⚠️ Format error: `/p 12.35`")
        return
    try:
        val = float(context.args[0].replace("%", ""))
        data = load_data()
        data["sh_premium"] = val
        save_data(data)
        await update.message.reply_text(f"✅ Premium Updated: *{val}%*")
    except ValueError:
        await update.message.reply_text("❌ Invalid number format!")


async def tg_set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    text = " ".join(context.args)
    if not text:
        return
    data = load_data()
    if "notes_history" not in data:
        data["notes_history"] = []
    data["notes_history"].append(text)
    if len(data["notes_history"]) > 10:
        data["notes_history"].pop(0)
    save_data(data)
    await update.message.reply_text(f"📝 Memo logged: `{text}`")


async def tg_set_trans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    text = " ".join(context.args)
    if not text:
        return
    try:
        src_lang = "zh-TW" if re.search(r"[\u4e00-\u9fa5]", text) else "auto"
        trans_zh = GoogleTranslator(source=src_lang, target="zh-TW").translate(
            text
        )
        trans_en = GoogleTranslator(source=src_lang, target="en").translate(text)
        trans_vi = GoogleTranslator(source=src_lang, target="vi").translate(text)
        final_msg = f"🇬🇧 {trans_en}\n\n🇨🇳 {trans_zh} ｜ 🇻🇳 {trans_vi}"
    except Exception:
        final_msg = f"🇬🇧 {text}\n\n*(⚠️ Translation Error)*"

    data = load_data()
    if "chat_history" not in data:
        data["chat_history"] = []
    data["chat_history"].append(final_msg)
    if len(data["chat_history"]) > 20:
        data["chat_history"].pop(0)
    save_data(data)
    await update.message.reply_text(f"🌐 Message synchronized!\n\n{final_msg}")


async def tg_get_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    data = load_data()
    notes = [n for n in data.get("notes_history", []) if n.strip()]
    notes_str = (
        "\n".join([f"{i+1}. {n}" for i, n in enumerate(notes)])
        if notes
        else "None"
    )
    await update.message.reply_text(
        f"📊 *Current Metrics:*\n\n"
        f"SH Premium: `{data.get('sh_premium')}%`\n\n"
        f"📝 *Memos:*\n{notes_str}"
    )


@st.cache_resource
def init_telegram_bot(token):
    if not token:
        return

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
    r = requests.get(
        f"https://api.gold-api.com/price/{symbol}", headers=HEADERS, timeout=10
    )
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
        errors.append(f"gold-api error: {e}")
        return None, errors

    try:
        dxy = fetch_synthetic_dxy()
    except Exception as e:
        errors.append(f"DXY calc error: {e}")
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
        errors.append(f"CoinGecko AG error: {e}")

    try:
        au_hist = fetch_crypto_history("pax-gold", 6)
        if au_hist and len(au_hist) > 0:
            recent_5d = [p[1] for p in au_hist]
            gold_past = recent_5d[0]
            gold_high = max(recent_5d)
            gold_low = min(recent_5d)
    except Exception as e:
        errors.append(f"CoinGecko AU error: {e}")

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


# ==========================================
# 3. 側邊欄：控制面板與變數設定 (Properties Pane)
# ==========================================
st.sidebar.markdown("### 🛠️ Data Inputs & Parameters")

sh_premium = st.sidebar.number_input(
    "SH Premium Rate (%)",
    step=0.1,
    key="sh_premium_val",
    on_change=update_premium_cb,
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Threshold Settings**")
gsr_upper = st.sidebar.slider(
    "GSR Upper Limit", 65.0, 95.0, 80.0, 0.5, key="gsr_upper_val"
)
gsr_lower = st.sidebar.slider(
    "GSR Lower Limit", 40.0, 65.0, 50.0, 0.5, key="gsr_lower_val"
)
premium_upper = st.sidebar.slider(
    "Premium Threshold (%)", 15.0, 30.0, 20.0, 0.5, key="premium_upper_val"
)

st.sidebar.markdown("---")
with st.sidebar.expander("📝 Scratchpad / Memo", expanded=True):
    current_data = load_data()
    notes = [n for n in current_data.get("notes_history", []) if n.strip()]
    if notes:
        for idx, note_text in enumerate(notes, 1):
            clean_text = re.sub(r"^\d+[\.\、]\s*", "", note_text)
            st.markdown(f"`[{idx}]` {clean_text}")
    else:
        st.caption("No log entries.")

    st.text_input(
        "Add Log:",
        key="trading_note_val",
        on_change=update_note_cb,
        placeholder="Enter text...",
    )

st.sidebar.markdown("---")
if st.sidebar.button("⚡ Test Connection"):
    if send_telegram_alert("System Alert: Connection verified."):
        st.sidebar.success("OK")
    else:
        st.sidebar.error("Error")

# ==========================================
# 4. 主內容區域：試算表擬真展現 (Data Grid)
# ==========================================

# Formula Bar (假公式欄，極度增加真實感)
st.markdown(
    """
    <div style="background:#E6E6E6; border:1px solid #C8C6C4; padding:4px 10px; font-family:Consolas, monospace; font-size:12px; margin-bottom:12px; display:flex; align-items:center;">
        <span style="font-weight:bold; color:#107C41; margin-right:10px;">fx</span>
        <span style="color:#505050;">=SUM(Spot_Data)*INDEX(Market_Rates, "Live")</span>
    </div>
    """,
    unsafe_allow_html=True,
)

c_btn, c_space = st.columns([1, 5])
with c_btn:
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.toast("Data refreshed.")

market_data, fetch_errors = fetch_market_data()

if fetch_errors and market_data is None:
    st.error("Data Fetch Error")

if market_data:
    st.markdown("##### 📍 Summary Table 1: Real-time Market Benchmarks")

    # 運用 6 欄位網格排列，極度類似 Excel 儲存格
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("XAG/USD (Spot)", f"${market_data['spot_silver']}")
    col2.metric("XAU/USD (Spot)", f"${market_data['spot_gold']}")
    col3.metric("DXY Index", market_data["dxy"] if market_data["dxy"] else "N/A")
    col4.metric("GSR Ratio", f"{market_data['gsr']}")
    col5.metric(
        "AG RSI(14)",
        market_data["rsi"] if market_data["rsi"] else "N/A",
    )
    col6.metric("SH Premium", f"{st.session_state.sh_premium_val}%")

    st.markdown("---")

    today = datetime.now().date()
    st.markdown("##### 📍 Summary Table 2: System Status & Schedule")

    # 使用表格 DataFrame 渲染，比單純文字更有「Excel」味道
    status_df = pd.DataFrame(
        [
            {
                "Data Source Timestamp": market_data["as_of"],
                "Next NFP Target": str(get_next_nfp(today)),
                "Next CPI Target": str(get_next_cpi(today)),
                "Engine Status": "ACTIVE / NORMAL",
            }
        ]
    )
    st.dataframe(status_df, use_container_width=True, hide_index=True)

# ==========================================
# 5. 多語留言板 (Communication Log)
# ==========================================
st.markdown("---")
st.markdown("##### 📋 Communication Log (Multilingual Archive)")


def add_chat_cb():
    raw_text = st.session_state.get("new_chat_val", "")
    if raw_text.strip():
        try:
            src_lang = "zh-TW" if re.search(r"[\u4e00-\u9fa5]", raw_text) else "auto"
            trans_zh = GoogleTranslator(
                source=src_lang, target="zh-TW"
            ).translate(raw_text)
            trans_en = GoogleTranslator(
                source=src_lang, target="en"
            ).translate(raw_text)
            trans_vi = GoogleTranslator(
                source=src_lang, target="vi"
            ).translate(raw_text)
            formatted_msg = f"🇬🇧 {trans_en}\n\n🇨🇳 {trans_zh} ｜ 🇻🇳 {trans_vi}"
        except Exception:
            formatted_msg = f"🇬🇧 {raw_text}\n\n*(Translation Failed)*"

        data = load_data()
        if "chat_history" not in data:
            data["chat_history"] = []
        data["chat_history"].append(formatted_msg)
        if len(data["chat_history"]) > 20:
            data["chat_history"].pop(0)
        save_data(data)
        st.session_state.new_chat_val = ""


st.text_input(
    "Input text to append log:",
    key="new_chat_val",
    on_change=add_chat_cb,
    placeholder="Type message and press Enter...",
)

data = load_data()
chat_history = data.get("chat_history", [])
if chat_history:
    for chat in reversed(chat_history):  # 新訊息在最上面，比較符合工作表邏輯
        with st.container(border=True):
            st.markdown(chat)
else:
    st.info("No records found.")

st.caption("Internal Data Sheet - Confidential / For Internal Operations Only")

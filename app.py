import asyncio
import calendar
import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone

from deep_translator import GoogleTranslator
import pandas as pd
import requests
import streamlit as st
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

st.set_page_config(
    page_title="Q3_metal data.xlsx - Excel", page_icon="📗", layout="wide"
)

# 定義標準 UTC+8 時區 (台灣/北京/香港時區)
TZ_UTC8 = timezone(timedelta(hours=8))

# ============================================================
# 🎨 Excel 視覺偽裝樣式（純 CSS/HTML，不影響任何運算邏輯）
# ============================================================
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Calibri&family=Segoe+UI&display=swap');

    /* 隱藏 Streamlit 原生 Header 與 Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent;}

    html, body, [class*="css"] {
        font-family: "Segoe UI", "Calibri", "Microsoft JhengHei", sans-serif !important;
    }

    .stApp {
        background-color: #FFFFFF;
    }

    /* 側邊欄偽裝成工作窗格 */
    section[data-testid="stSidebar"] {
        background-color: #F3F2F1;
        border-right: 1px solid #D0D0D0;
    }

    /* 按鈕 Excel 化 */
    .stButton>button {
        background: linear-gradient(#FFFFFF, #F0F0F0);
        border: 1px solid #C0C0C0;
        border-radius: 2px;
        color: #217346;
        font-weight: 600;
        font-size: 13px;
    }
    .stButton>button:hover {
        background: #E6F4EA;
        border-color: #217346;
    }

    /* Metric 卡片儲存格化 */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #D0D0D0;
        border-top: 2px solid #217346;
        padding: 6px 10px 8px 10px;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 12px !important;
        color: #444444 !important;
    }
    div[data-testid="stMetricValue"] {
        font-family: "Calibri", "Segoe UI", sans-serif !important;
        color: #000000 !important;
    }

    /* ---------------------------------------------------- */
    /* 🎯 全局 Alert (st.info, st.warning, st.success) 統一色彩 */
    /* ---------------------------------------------------- */
    div[data-testid="stAlert"], .stAlert, 
    div[data-testid="stAlert"] > div,
    div[data-baseweb="notification"] {
        background-color: #E8F4F8 !important;  /* 統一淡藍色底 */
        color: #1A4958 !important;             /* 統一深藍灰文字 */
        border: 1px solid #BEE3F8 !important;   /* 統一淡藍邊框 */
        border-radius: 4px !important;
    }
    
    div[data-testid="stAlert"] p, 
    div[data-testid="stAlert"] span,
    div[data-testid="stAlert"] label {
        color: #1A4958 !important;
    }
    div[data-testid="stAlert"] svg {
        fill: #2B6CB0 !important;              /* 統一圖示顏色 */
    }

    /* Excel 儲存格網格 table 樣式 */
    .xl-grid { border-collapse: collapse; width: 100%; font-size: 13px; }
    .xl-grid th, .xl-grid td {
        border: 1px solid #D4D4D4;
        padding: 4px 8px;
        text-align: center;
    }
    .xl-colhead {
        background-color: #F3F2F1;
        color: #444444;
        font-weight: 600;
        font-size: 12px;
    }
    .xl-rowhead {
        background-color: #F3F2F1;
        color: #444444;
        font-weight: 600;
        width: 28px;
        font-size: 12px;
    }
    .xl-label { text-align: left !important; color: #333; }
    .xl-value { font-weight: 600; font-family: "Calibri", monospace; }
    .xl-green { color: #217346; }
    .xl-red { color: #C00000; }
</style>
""",
    unsafe_allow_html=True,
)

# --- 假功能區 Ribbon + 公式列 ---
st.markdown(
    """
<div style="background:#F3F2F1; border-bottom:1px solid #D0D0D0; padding:4px 10px; font-size:13px; color:#444; display:flex; gap:18px;">
    <b style="color:#217346;">檔案</b> 常用 插入 頁面配置 公式 資料 校閱 檢視 說明
</div>
<div style="background:#FFFFFF; border-bottom:1px solid #D0D0D0; padding:5px 10px; font-size:12.5px; color:#444; display:flex; align-items:center; gap:10px;">
    <span style="border:1px solid #C0C0C0; padding:1px 8px; border-radius:2px; background:#FAFAFA;">A1</span>
    <span style="color:#999;">fx</span>
    <span style="color:#666;">=老闆我是個好牛馬()</span>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    "<h2 style='margin-top:10px;'>📗 Q3_metal index"
    "<span style='font-size: 0.5em; color: grey;'> Daily Gold &amp; Silver Market Monitor</span></h2>",
    unsafe_allow_html=True,
)
st.caption(
    "數據來源：gold-api.com（現貨）10/m ＋ Frankfurter（DXY）1/3m ＋"
    " CoinGecko（RSI/5日波段）1/10m ＋"
    " jsonbin.io  10000/D"
)
st.markdown("---")

HEADERS = {"User-Agent": "Mozilla/5.0"}
DATA_FILE = "data.json"

JSONBIN_API_KEY = st.secrets.get("JSONBIN_API_KEY", None)
JSONBIN_BIN_ID = st.secrets.get("JSONBIN_BIN_ID", None)
JSONBIN_URL = (
    f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}" if JSONBIN_BIN_ID else None
)
PERSIST_ENABLED = bool(JSONBIN_URL and JSONBIN_API_KEY)

if not PERSIST_ENABLED:
    st.sidebar.warning(
        "⚠️ 尚未設定 JSONBin 雲端儲存（JSONBIN_API_KEY / JSONBIN_BIN_ID）。"
        "目前資料僅寫在容器本機，App 休眠喚醒或重新部署後會被重置為預設值。"
    )


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
    st.sidebar.error("⚠️ 尚未設定 Telegram Secrets，推播與雙向控制功能停用。")


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


async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    await update.message.reply_text(
        "🪙 *金銀戰情室控制台已連線！*\n\n"
        "指令列表：\n"
        "1. `/p 12.35` ：更新溢價\n"
        "2. `/n 筆記內容` ：新增記事本心得 (最多10則)\n"
        "3. `/t 翻譯內容` ：多語自動翻譯並寫入留言板\n"
        "4. `/get` ：查詢當前設定與近期資料",
        parse_mode="Markdown",
    )


async def tg_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ 請輸入數值，範例：`/p 12.35`", parse_mode="Markdown"
        )
        return
    try:
        raw_val = context.args[0].replace("%", "")
        val = float(raw_val)
        data = load_data()
        data["sh_premium"] = val
        save_data(data)
        await update.message.reply_text(
            f"✅ 上海銀溢價已更新為：*{val}%*", parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ 請輸入有效的數字格式！")


async def tg_set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "⚠️ 請輸入內容，範例：`/n 注意美盤開盤`", parse_mode="Markdown"
        )
        return

    data = load_data()
    if "notes_history" not in data:
        data["notes_history"] = []
    data["notes_history"].append(text)
    if len(data["notes_history"]) > 10:
        data["notes_history"].pop(0)
    save_data(data)

    await update.message.reply_text(
        f"📝 *線上記事本已新增：*\n\n`{text}`\n*(目前共存"
        f" {len(data['notes_history'])} 則，上限10則)*",
        parse_mode="Markdown",
    )


async def tg_set_trans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "⚠️ 請輸入內容，範例：`/t hawkish FED`", parse_mode="Markdown"
        )
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
        final_msg = f"🇬🇧 {text}\n\n*(⚠️ 翻譯失敗)*"

    data = load_data()
    if "chat_history" not in data:
        data["chat_history"] = []
    data["chat_history"].append(final_msg)
    if len(data["chat_history"]) > 20:
        data["chat_history"].pop(0)
    save_data(data)

    await update.message.reply_text(
        f"🌐 *新對話已同步加入留言板！*\n\n{final_msg}", parse_mode="Markdown"
    )


async def tg_get_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id).strip() != str(ALLOWED_CHAT_ID).strip():
        return
    data = load_data()

    notes = [n for n in data.get("notes_history", []) if n.strip()]
    notes_str = (
        "\n".join([f"{i+1}. {n}" for i, n in enumerate(notes)])
        if notes
        else "目前無筆記"
    )

    history = data.get("chat_history", [])
    chat_str = "\n\n---\n\n".join(history[-3:]) if history else "目前無對話"

    await update.message.reply_text(
        f"📊 *當前戰情室參數：*\n\n"
        f"🇨🇳 上海銀溢價：`{data.get('sh_premium')}%`\n\n"
        f"📝 *線上記事本 (近期筆記)：*\n{notes_str}\n\n"
        f"🌐 *最近留言板 (最後3則)：*\n{chat_str}",
        parse_mode="Markdown",
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


# --- ⏰ 時區轉換與時間處理工具函數 ---
def parse_and_convert_to_utc8(as_of_str):
    """解析 API 的 ISO UTC 時間並自動轉為本地 UTC+8 時間格式"""
    if not as_of_str:
        now_utc8 = datetime.now(TZ_UTC8)
        return now_utc8.date(), now_utc8.strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    try:
        clean_str = as_of_str.replace("Z", "")
        dt_utc = datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
        dt_utc8 = dt_utc.astimezone(TZ_UTC8)
        return dt_utc8.date(), dt_utc8.strftime("%Y-%m-%d %H:%M:%S (UTC+8)")
    except Exception:
        now_utc8 = datetime.now(TZ_UTC8)
        return now_utc8.date(), str(as_of_str)


def get_next_nfp(ref_date):
    month, year = ref_date.month, ref_date.year
    c = calendar.monthcalendar(year, month)
    first_friday_day = c[0][4] if c[0][4] != 0 else c[1][4]
    first_friday = date(year, month, first_friday_day)
    if ref_date > first_friday:
        month = 1 if month == 12 else month + 1
        year = year + 1 if month == 1 else year
        c = calendar.monthcalendar(year, month)
        first_friday_day = c[0][4] if c[0][4] != 0 else c[1][4]
        first_friday = date(year, month, first_friday_day)
    return first_friday


def get_next_cpi(ref_date):
    month, year = ref_date.month, ref_date.year
    cpi_date = date(year, month, 13)
    if cpi_date.weekday() == 5:
        cpi_date = date(year, month, 12)
    elif cpi_date.weekday() == 6:
        cpi_date = date(year, month, 14)
    if ref_date > cpi_date:
        month = 1 if month == 12 else month + 1
        year = year + 1 if month == 1 else year
        cpi_date = date(year, month, 13)
        if cpi_date.weekday() == 5:
            cpi_date = date(year, month, 12)
        elif cpi_date.weekday() == 6:
            cpi_date = date(year, month, 14)
    return cpi_date


def get_next_fomc(ref_date):
    """聯準會 FOMC 利率決策會議日程 (美東時間宣佈日，比對現貨時間)"""
    fomc_dates = [
        # 2026 年 FOMC 日程
        date(2026, 1, 28),
        date(2026, 3, 18),
        date(2026, 4, 29),
        date(2026, 6, 17),
        date(2026, 7, 29),
        date(2026, 9, 16),
        date(2026, 10, 28),
        date(2026, 12, 16),
        # 2027 年預估 FOMC 日程
        date(2027, 1, 27),
        date(2027, 3, 17),
        date(2027, 4, 28),
        date(2027, 6, 16),
        date(2027, 7, 28),
        date(2027, 9, 22),
        date(2027, 10, 27),
        date(2027, 12, 15),
    ]
    for d in fomc_dates:
        if d >= ref_date:
            return d
    return fomc_dates[-1]


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
    "今日上海銀溢價 Premium (%)",
    step=0.1,
    key="sh_premium_val",
    on_change=update_premium_cb,
)
st.sidebar.markdown(
    "👉 **[ Ai即時溢價premium](https://goldsilver.ai/metal-prices/shanghai-silver-price)**"
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 警示門檻微調")
gsr_upper = st.sidebar.slider(
    "GSR 高估門檻 (賣金買銀)", 65.0, 95.0, 80.0, 0.5, key="gsr_upper_val"
)
gsr_lower = st.sidebar.slider(
    "GSR 低估門檻 (賣銀買金)", 40.0, 65.0, 50.0, 0.5, key="gsr_lower_val"
)
premium_upper = st.sidebar.slider(
    "溢價極端門檻 (%)", 15.0, 30.0, 20.0, 0.5, key="premium_upper_val"
)
premium_lower = st.sidebar.slider(
    "溢價收斂門檻 (%)", 0.0, 15.0, 10.0, 0.5, key="premium_lower_val"
)

st.sidebar.markdown("---")
st.sidebar.header("🛠️ 工具與線上記事本")

with st.sidebar.expander("📝 心得牆", expanded=True):
    st.markdown("**【線上記事本 (上限10則)】**")

    current_data = load_data()
    notes = [n for n in current_data.get("notes_history", []) if n.strip()]
    if notes:
        for idx, note_text in enumerate(notes, 1):
            clean_text = re.sub(r"^\d+[\.\、]\s*", "", note_text)
            st.markdown(f"**{idx}.** {clean_text}")
    else:
        st.caption("目前尚無記事紀錄")

    st.markdown("---")
    st.text_input(
        "✍️ 新增臨時心得(10000/D)：",
        key="trading_note_val",
        on_change=update_note_cb,
        placeholder="輸入後按 Enter 儲存...",
    )

st.sidebar.markdown("---")
st.sidebar.header("📱 Telegram 測試與連線")
if st.sidebar.button("發送測試訊息至 Telegram"):
    if send_telegram_alert("🪙 金銀戰情室：手動測試連線成功！"):
        st.sidebar.success("✅ 發送成功！請檢查您的 Telegram。")
    else:
        st.sidebar.error("❌ 發送失敗，請確認 Secrets 設定。")

market_data, fetch_errors = fetch_market_data()

if fetch_errors and market_data is None:
    st.error("⚠️ 資料抓取失敗：")
    for e in fetch_errors:
        st.code(e)

if market_data:
    # 頂部 checked time 使用標準 UTC+8 時間
    now_utc8_str = datetime.now(TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")
    st.caption(f"checked time：{now_utc8_str}")
    st.markdown("### 📍 Daily data")

    dxy_disp = market_data["dxy"] if market_data["dxy"] is not None else "N/A"
    rsi_disp = market_data["rsi"] if market_data["rsi"] is not None else "N/A"

    st.markdown(
        f"""
    <table class="xl-grid">
      <tr>
        <th class="xl-colhead"></th>
        <th class="xl-colhead">A</th>
        <th class="xl-colhead">B</th>
        <th class="xl-colhead">C</th>
        <th class="xl-colhead">D</th>
        <th class="xl-colhead">E</th>
        <th class="xl-colhead">F</th>
      </tr>
      <tr>
        <td class="xl-rowhead">1</td>
        <td class="xl-label">現貨銀 Silver</td>
        <td class="xl-label">現貨金 Gold</td>
        <td class="xl-label">合成 DXY</td>
        <td class="xl-label">金銀比 GSR</td>
        <td class="xl-label">白銀 RSI(14)</td>
        <td class="xl-label">銀溢價 Premium</td>
      </tr>
      <tr>
        <td class="xl-rowhead">2</td>
        <td class="xl-value xl-green">${market_data['spot_silver']}</td>
        <td class="xl-value xl-green">${market_data['spot_gold']}</td>
        <td class="xl-value">{dxy_disp}</td>
        <td class="xl-value">{market_data['gsr']}</td>
        <td class="xl-value">{rsi_disp}</td>
        <td class="xl-value">{st.session_state.sh_premium_val}%</td>
      </tr>
    </table>
    """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### 🚨 Daily comments")

    # 將現貨時間自動轉為 UTC+8 當地時間
    ref_date, local_as_of_str = parse_and_convert_to_utc8(market_data["as_of"])

    next_fomc = get_next_fomc(ref_date)
    next_nfp = get_next_nfp(ref_date)
    next_cpi = get_next_cpi(ref_date)

    st.info(
        f"⏱️ **現貨資料時間：** `{local_as_of_str}`\n\n"
        f"📅 **下次重大數據：** FED利率會議 `{next_fomc}` ｜ 非農 `{next_nfp}` ｜ CPI 預測 `{next_cpi}`"
    )

    # --- ⚖️ 1. 金銀比 (GSR) 與上海銀套利動態建議 ---
    current_gsr = market_data.get("gsr")
    current_prem = st.session_state.sh_premium_val

    st.markdown("#### ⚖️ GSR Strategy")

    c_gsr_strat, c_prem_strat = st.columns(2)

    with c_gsr_strat:
        st.markdown("**📊 GSR metal comments**")
        if current_gsr:
            if current_gsr >= gsr_upper:
                st.info(
                    f"🚨 **GSR 目前為 {current_gsr}（≥ 門檻 {gsr_upper}）**：\n"
                    "白銀相對黃金**嚴重低估**！操作建議：**【賣金買銀 /"
                    " 多銀空金】**，博取金銀比均值回歸。"
                )
            elif current_gsr <= gsr_lower:
                st.info(
                    f"🚨 **GSR 目前為 {current_gsr}（≤ 門檻 {gsr_lower}）**：\n"
                    "白銀相對黃金**顯著高估**！操作建議：**【賣銀買金 /"
                    " 多金空銀】**，防範白銀補跌風險。"
                )
            else:
                st.info(
                    f"☑️ **GSR 目前為 {current_gsr}**（介於設定門檻 {gsr_lower} ~"
                    f" {gsr_upper} 之間）：\n"
                    "金銀比處於**合理中性區間**，建議保持不動，觀察波段趨勢。"
                )
        else:
            st.caption("GSR 資料計算中...")

    with c_prem_strat:
        st.markdown("**🇨🇳 上海銀 Premium 溢價建議**")
        if current_prem >= premium_upper:
            st.info(
                f"🚨 **上海銀溢價達 {current_prem}%（≥ 門檻"
                f" {premium_upper}%）**：\n"
                "國內需求極度高企或流動性緊縮，極端溢價警示，留意回吐修正。"
            )
        elif current_prem <= premium_lower:
            st.info(
                f"💡 **上海銀溢價為 {current_prem}%（≤ 門檻"
                f" {premium_lower}%）**：\n"
                "國內外價差收斂，市場情緒平穩，適合佈局長線價差套利。"
            )
        else:
            st.info(
                f"☑️ **上海銀溢價為 {current_prem}%**：處於正常溢價區間"
                f"（{premium_lower}% ~ {premium_upper}%）。"
            )

    st.markdown("---")

    # --- 📐 2. 0.618 費波那契波段分析 ---
    st.markdown("#### 📐 Swing and the 0.618 Fibonacci extension level")

    col_ag, col_au = st.columns(2)

    # 白銀 0.618 計算
    ag_spot = market_data.get("spot_silver")
    ag_high = market_data.get("silver_high")
    ag_low = market_data.get("silver_low")

    with col_ag:
        st.markdown("**🥈 Silver 5-day range and 0.618**")
        if ag_spot and ag_high and ag_low and ag_high > ag_low:
            ag_diff = ag_high - ag_low
            ag_fib_sup = round(ag_high - (ag_diff * 0.618), 2)
            ag_fib_res = round(ag_low + (ag_diff * 0.618), 2)

            st.write(f"• **5日高低區間：** `${ag_low}` - `${ag_high}`")
            st.write(f"• **0.618 關鍵支撐：** `${ag_fib_sup}`")
            st.write(f"• **0.618 關鍵壓力：** `${ag_fib_res}`")

            if ag_spot <= ag_fib_sup:
                st.info(
                    "⚠️ 現價低於 0.618 支撐位：短線有超跌反彈機會，可留意多頭套利。"
                )
            elif ag_spot >= ag_fib_res:
                st.info(
                    "⚠️ 現價高於 0.618"
                    " 壓力位：短線進入強勢衝高區，注意上方獲利回吐賣壓。"
                )
            else:
                st.info("☑️ 現價處於 0.618 費波那契合理波段區間。")
        else:
            st.caption("白銀 5日波段歷史資料計算中...")

    # 黃金 0.618 計算
    au_spot = market_data.get("spot_gold")
    au_high = market_data.get("gold_high")
    au_low = market_data.get("gold_low")

    with col_au:
        st.markdown("**🥇 Gold 5-day range and 0.618**")
        if au_spot and au_high and au_low and au_high > au_low:
            au_diff = au_high - au_low
            au_fib_sup = round(au_high - (au_diff * 0.618), 1)
            au_fib_res = round(au_low + (au_diff * 0.618), 1)

            st.write(f"• **5日高低區間：** `${au_low}` - `${au_high}`")
            st.write(f"• **0.618 關鍵支撐：** `${au_fib_sup}`")
            st.write(f"• **0.618 關鍵壓力：** `${au_fib_res}`")

            if au_spot <= au_fib_sup:
                st.info(
                    "⚠️ 現價低於 0.618 支撐位：黃金短線回檔至黃金分割低位。"
                )
            elif au_spot >= au_fib_res:
                st.info(
                    "⚠️ 現價高於 0.618 壓力位：黃金短線逼近波段壓力位。"
                )
            else:
                st.info("☑️ 現價處於 0.618 費波那契合理波段區間。")
        else:
            st.caption("黃金 5日波段歷史資料計算中...")

# --- 放在主畫面最下方的「多語言留言板+翻譯」 ---
st.markdown("---")
st.markdown("### 📋 綜合留言板 (Multilingual Message Board)")
st.caption(
    "在此輸入訊息，系統將自動翻譯並記錄最近 20 則留言。可透過 Telegram"
    " 隨時發送與查詢最新留言。"
)


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
            formatted_msg = f"🇬🇧 {raw_text}\n\n*(⚠️ 翻譯失敗)*"

        data = load_data()
        if "chat_history" not in data:
            data["chat_history"] = []
        data["chat_history"].append(formatted_msg)
        if len(data["chat_history"]) > 20:
            data["chat_history"].pop(0)
        save_data(data)
        st.session_state.new_chat_val = ""


st.text_input(
    "✍️ 新增留言與多語翻譯(10000/D by jsonbin.io/)：",
    key="new_chat_val",
    on_change=add_chat_cb,
    placeholder="輸入內容後按 Enter 提交...",
)

data = load_data()
chat_history = data.get("chat_history", [])
if chat_history:
    for chat in chat_history:
        with st.container(border=True):
            st.markdown(chat)
else:
    st.info("目前尚無留言紀錄，趕快在上方留下第一則訊息吧！")

st.divider()
st.caption("以上僅供研究參考，不構成投資建議，各人造業各人擔。")

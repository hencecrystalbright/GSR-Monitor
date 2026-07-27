import logging
import json
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8850511159:AAFygXc9GaX6Mhjry4y_57tfKXA13t5IilU"
ALLOWED_CHAT_ID = "5259644398"  # 權限驗證：只回應您的 Chat ID
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

# 指令 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != ALLOWED_CHAT_ID:
        return
    await update.message.reply_text(
        "🪙 *金銀戰情室遠端控制台已上線！*\n\n"
        "可用指令：\n"
        "1. `/p 12.35` ：更新上海銀溢價\n"
        "2. `/note 你的筆記` ：更新戰術筆記\n"
        "3. `/get` ：查看當前設定",
        parse_mode="Markdown"
    )

# 指令 /p 或 /premium (例: /p 12.35)
async def set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != ALLOWED_CHAT_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ 請輸入數值，範例：`/p 12.35`", parse_mode="Markdown")
        return
    try:
        val = float(context.args[0])
        data = load_data()
        data["sh_premium"] = val
        save_data(data)
        await update.message.reply_text(f"✅ 上海銀溢價已更新為：*{val}%*", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ 請輸入有效的數字格式！")

# 指令 /note (例: /note 今晚美盤注意 CPI)
async def set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != ALLOWED_CHAT_ID:
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("⚠️ 請輸入內容，範例：`/note 注意 CPI 數據`", parse_mode="Markdown")
        return
    data = load_data()
    data["trading_note"] = text
    save_data(data)
    await update.message.reply_text(f"📝 戰術筆記已更新：\n\n`{text}`", parse_mode="Markdown")

# 指令 /get (查詢當前狀態)
async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != ALLOWED_CHAT_ID:
        return
    data = load_data()
    await update.message.reply_text(
        f"📊 *當前戰情室參數：*\n\n"
        f"🇨🇳 上海銀溢價：`{data.get('sh_premium')}%`\n"
        f"📝 交易筆記：\n`{data.get('trading_note')}`",
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["p", "premium"], set_premium))
    app.add_handler(CommandHandler("note", set_note))
    app.add_handler(CommandHandler("get", get_status))
    app.run_polling()

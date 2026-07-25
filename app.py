import pandas as pd
import streamlit as st

# 1. 頁面標題與配置
st.set_page_config(
    page_title="金銀市場與套利監測儀表板", page_icon="🪙", layout="centered"
)

st.title("🪙 每日金銀市場與套利監測")
st.caption("數據來源已錨定指定 4 大官方管道")
st.markdown("---")

# 2. 定義指定數據來源 URL
TARGET_SOURCES = {
    "現貨銀價 (Spot)": "https://www.truney.com/en/gold-chart",
    "金銀比 & 上海銀溢價": (
        "https://goldsilver.ai/metal-prices/shanghai-silver-price"
    ),
    "COMEX 期銀主力": (
        "https://www.cmegroup.com/markets/metals/precious/silver.volume.html"
    ),
    "DXY 美元指數": (
        "https://www.tradingview.com/symbols/TVC-DXY/?matchtype=e&timeframe=5D"
    ),
}

# 3. 側邊欄：來源連結與數據校驗
st.sidebar.header("📌 數據來源與每日校正")

st.sidebar.markdown("### 🔗 點擊檢視原始數據來源")
for name, url in TARGET_SOURCES.items():
    st.sidebar.markdown(f"- **{name}**：[前往來源網頁]({url})")

st.sidebar.markdown("---")
st.sidebar.markdown("### ✍️ 今日數據校正 / 手動調整")

# 可透過側邊欄快速輸入當天從上述網址看到的精確數字
spot_silver = st.sidebar.number_input(
    "1. 現貨銀價 ($)",
    value=58.22,
    step=0.01,
    help="來源：TRUNEY Gold Chart",
)
comex_silver = st.sidebar.number_input(
    "2. COMEX 期銀 ($)",
    value=58.65,
    step=0.01,
    help="來源：CME Group",
)
dxy_index = st.sidebar.number_input(
    "3. DXY 美元指數",
    value=101.46,
    step=0.01,
    help="來源：TradingView",
)
gsr_ratio = st.sidebar.number_input(
    "4. 金銀比 (GSR)",
    value=69.7,
    step=0.1,
    help="來源：GoldSilver.ai",
)
sh_premium = st.sidebar.number_input(
    "5. 上海銀溢價 (%)",
    value=5.5,
    step=0.1,
    help="來源：GoldSilver.ai",
)

# 4. 主畫面：顯示當日關鍵指標卡片
st.markdown("### 📍 當日核心市場數據")

col1, col2, col3 = st.columns(3)
col1.metric("現貨銀價 (Spot)", f"${spot_silver}")
col2.metric("COMEX 期銀", f"${comex_silver}")
col3.metric("DXY 美元指數", f"{dxy_index}")

col4, col5 = st.columns(2)
col4.metric("金銀比 (GSR)", f"{gsr_ratio}")
col5.metric("上海銀溢價", f"{sh_premium}%")

st.markdown("---")

# 5. 圖表視覺化 (歷史走勢)
st.markdown("### 📊 歷史趨勢與走勢圖")

# 模擬近 5 日數據紀錄 (可手動擴充或連動資料庫)
history_data = {
    "日期": [
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
        "2026-07-25",
    ],
    "GSR金銀比": [70.2, 70.0, 69.8, 69.9, gsr_ratio],
    "現貨銀價": [57.5, 57.8, 58.0, 58.1, spot_silver],
    "上海銀溢價(%)": [5.2, 5.5, 5.0, 5.3, sh_premium],
}
df = pd.DataFrame(history_data)

tab1, tab2, tab3 = st.tabs(["GSR 金銀比", "現貨銀價", "上海銀溢價"])

with tab1:
    st.subheader("金銀比 (GSR) 走勢")
    st.line_chart(df.set_index("日期")["GSR金銀比"])

with tab2:
    st.subheader("現貨銀價 ($) 走勢")
    st.area_chart(df.set_index("日期")["現貨銀價"])

with tab3:
    st.subheader("上海銀溢價 (%) 走勢")
    st.line_chart(df.set_index("日期")["上海銀溢價(%)"])

# 6. 邏輯判斷與套利建議
st.markdown("---")
st.markdown("### 🚨 當日套利與轉置建議")

# GSR 轉置邏輯
if gsr_ratio >= 80:
    st.error(
        f"【GSR 警示】金銀比達 {gsr_ratio} (>=80)。白銀相對黃金嚴重低估，建議執行「賣金買銀」轉置策略。"
    )
elif gsr_ratio <= 50:
    st.warning(
        f"【GSR 警示】金銀比達 {gsr_ratio} (<=50)。白銀相對昂貴，建議「賣銀買金」。"
    )
else:
    st.info(
        f"【GSR 狀態】金銀比為 {gsr_ratio}，目前位於中性區間 (50 ~ 80)，無極端轉置訊號。"
    )

# 上海銀溢價套利邏輯
if sh_premium >= 20:
    st.error(
        f"【溢價警示】上海銀溢價達 {sh_premium}% (>=20%)！中國實體需求極強，建議避開 COMEX 空單，尋求跨市套利管道。"
    )
elif sh_premium <= 10:
    st.success(
        f"【溢價狀態】上海銀溢價為 {sh_premium}% (<=10%)。東西方市場定價收斂，無顯著跨市套利空間。"
    )
else:
    st.warning(
        f"【溢價狀態】上海銀溢價為 {sh_premium}%，處於過渡區間。"
    )

# 7. 頁尾來源清單
st.markdown("---")
with st.expander("ℹ️ 檢視數據來源對照表"):
    st.write(
        "1. **現貨銀價**："
        f" [{TARGET_SOURCES['現貨銀價 (Spot)']}]({TARGET_SOURCES['現貨銀價 (Spot)']})"
    )
    st.write(
        "2. **GSR & 上海銀溢價**："
        f" [{TARGET_SOURCES['金銀比 & 上海銀溢價']}]({TARGET_SOURCES['金銀比 & 上海銀溢價']})"
    )
    st.write(
        "3. **COMEX 期銀**："
        f" [{TARGET_SOURCES['COMEX 期銀主力']}]({TARGET_SOURCES['COMEX 期銀主力']})"
    )
    st.write(
        "4. **DXY 美元指數**："
        f" [{TARGET_SOURCES['DXY 美元指數']}]({TARGET_SOURCES['DXY 美元指數']})"
    )

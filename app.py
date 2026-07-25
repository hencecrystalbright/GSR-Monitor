import streamlit as st
import yfinance as yf
import pandas as pd

# 1. 頁面標題與配置
st.set_page_config(
    page_title="金銀市場與套利監測 (自動化版)", page_icon="🪙", layout="centered"
)

st.title("🪙 每日金銀市場與套利監測")
st.caption("數據來源：Yahoo Finance API (自動抓取) + GoldSilver.ai (手動校正)")
st.markdown("---")

# 2. 定義自動抓取函數 (並設定快取避免過度頻繁請求)
@st.cache_data(ttl=1800) # 30分鐘快取
def fetch_market_data():
    try:
        # XAGUSD=X(現貨銀), XAUUSD=X(現貨金), SI=F(期銀), DX-Y.NYB(美元指數)
        tickers = ["XAGUSD=X", "XAUUSD=X", "SI=F", "DX-Y.NYB"]
        data = yf.download(tickers, period="1mo", progress=False)['Close']
        
        # 【關鍵修正】：先向下填補(拿昨天的價格補今天)，再向上填補，絕不刪除整行資料
        data = data.ffill().bfill()
        
        # 獲取最新一筆報價
        latest = data.iloc[-1]
        
        # 歷史資料 (用於畫圖)
        hist_spot_silver = data["XAGUSD=X"]
        hist_gsr = data["XAUUSD=X"] / data["XAGUSD=X"]
        
        return {
            "spot_silver": round(latest["XAGUSD=X"], 2),
            "spot_gold": round(latest["XAUUSD=X"], 2),
            "comex_silver": round(latest["SI=F"], 2),
            "dxy": round(latest["DX-Y.NYB"], 2),
            "gsr": round(latest["XAUUSD=X"] / latest["XAGUSD=X"], 2),
            "hist_spot_silver": hist_spot_silver,
            "hist_gsr": hist_gsr
        }
    except Exception as e:
        st.error(f"連網抓取數據失敗，請稍後重試。錯誤訊息: {e}")
        return None

# 執行抓取
market_data = fetch_market_data()

# 3. 側邊欄：唯一的手動輸入區
st.sidebar.header("📌 上海銀溢價輸入區")

# 輸入框
sh_premium = st.sidebar.number_input(
    "今日上海銀溢價 (%)",
    value=12.22,
    step=0.1,
    help="請輸入今日最新的真實溢價數據"
)

# 放置於輸入框正下方的醒目連結
st.sidebar.markdown("👉 **[點此查看 GoldSilver.ai 即時溢價](https://goldsilver.ai/metal-prices/shanghai-silver-price)**")

# 4. 主畫面：數據展示與邏輯判斷
if market_data:
    st.markdown("### 📍 當日核心市場數據 (即時自動更新)")

    col1, col2, col3 = st.columns(3)
    col1.metric("現貨銀價 (Spot)", f"${market_data['spot_silver']}")
    col2.metric("COMEX 期銀", f"${market_data['comex_silver']}")
    col3.metric("DXY 美元指數", f"{market_data['dxy']}")

    col4, col5 = st.columns(2)
    col4.metric("金銀比 (GSR)", f"{market_data['gsr']}")
    col5.metric("上海銀溢價 (手動)", f"{sh_premium}%")
    
    # 主畫面板塊右下角快捷連結
    st.markdown("<div style='text-align: right;'><a href='https://goldsilver.ai/metal-prices/shanghai-silver-price' target='_blank'>🔗 前往確認上海銀真實溢價</a></div>", unsafe_allow_html=True)

    st.markdown("---")
    
    # 5. 邏輯判斷與套利建議
    st.markdown("### 🚨 當日套利與轉置建議")
    
    # GSR 轉置邏輯
    if market_data['gsr'] >= 80:
        st.error(f"【GSR 警示】金銀比達 {market_data['gsr']} (>=80)。白銀相對嚴重低估，建議考慮「賣金買銀」。")
    elif market_data['gsr'] <= 50:
        st.warning(f"【GSR 警示】金銀比達 {market_data['gsr']} (<=50)。白銀相對昂貴，建議「賣銀買金」。")
    else:
        st.info(f"【GSR 狀態】金銀比為 {market_data['gsr']}，目前位於中性區間。")

    # 上海銀溢價套利邏輯
    if sh_premium >= 20:
        st.error(f"【溢價警示】上海銀溢價達 {sh_premium}%！中國實體需求極強，建議避開 COMEX 空單。")
    elif sh_premium <= 10:
        st.success(f"【溢價狀態】上海銀溢價為 {sh_premium}%。東西方定價收斂，無顯著跨市套利空間。")
    else:
        st.warning(f"【溢價狀態】上海銀溢價為 {sh_premium}%，處於過渡區間。")

    st.markdown("---")
    
    # 6. 真實歷史趨勢圖
    st.markdown("### 📊 近一個月真實走勢圖")
    tab1, tab2 = st.tabs(["GSR 金銀比走勢", "現貨銀價走勢"])
    
    with tab1:
        st.line_chart(market_data['hist_gsr'])
    with tab2:
        st.area_chart(market_data['hist_spot_silver'])

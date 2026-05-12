import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import os

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Debug Mode - Verifying Polygon Data**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# ==================== SIDEBAR ====================
st.sidebar.subheader("🔑 Polygon.io API Key")
api_key = st.sidebar.text_input("API Key", type="password", value=os.getenv("POLYGON_API_KEY", ""))
if not api_key:
    st.sidebar.error("Please enter your Polygon.io API key")
    st.stop()

client = RESTClient(api_key=api_key)

st.sidebar.subheader("💰 Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

st.sidebar.subheader("⚙️ Settings")
profit_threshold = st.sidebar.slider("Min Profit % Threshold", 0.1, 5.0, 0.8, 0.1)
show_debug = st.sidebar.checkbox("Show Full Debug Info", value=True)

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        st.subheader(f"🔍 Analyzing {ticker}")

        # === STOCK DATA ===
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            from_date = (target_dt - timedelta(days=7)).date()
            to_date = (target_dt + timedelta(days=2)).date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))
        else:
            from_date = (datetime.now() - timedelta(days=2)).date()
            to_date = datetime.now().date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))

        if len(aggs) < 10:
            st.error("❌ Not enough stock data from Polygon")
            return [], []

        df = pd.DataFrame([{'timestamp': pd.to_datetime(a.timestamp, unit='ms'), 'close': a.close} for a in aggs])
        df.set_index('timestamp', inplace=True)

        if dummy_mode:
            time_diffs = (df.index - target_dt).map(abs)
            closest_idx = time_diffs.argmin()
            current_price = float(df['close'].iloc[closest_idx])
            later_idx = min(closest_idx + 12, len(df)-1)
            price_later = float(df['close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
        else:
            current_price = float(df['close'].iloc[-1])
            price_ago = float(df['close'].iloc[-13] if len(df) >= 13 else df['close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        st.success(f"✅ Stock Data: ${current_price:.2f} | Move: {move_pct:+.1f}%")

        # === OPTIONS CHAIN ===
        today = datetime.now().date()
        opportunities = []
        samples = []

        params = {
            "expiration_date.gte": (today + timedelta(days=180)).strftime("%Y-%m-%d"),
            "expiration_date.lte": (today + timedelta(days=730)).strftime("%Y-%m-%d"),
            "contract_type": "call",
        }

        chain = list(client.list_snapshot_options_chain(ticker, params=params))
        st.info(f"🔍 Polygon returned **{len(chain)}** long-dated LEAP calls")

        for i, opt in enumerate(chain[:15]):  # Show first 15 for debug
            strike = float(opt.details.strike_price)
            expiry = opt.details.expiration_date

            last_price = 0.0
            if hasattr(opt, 'last_trade') and opt.last_trade and opt.last_trade.price:
                last_price = float(opt.last_trade.price)
            elif hasattr(opt, 'day') and opt.day and opt.day.close:
                last_price = float(opt.day.close)

            oi = getattr(opt, 'open_interest', 0)
            vol = getattr(getattr(opt, 'day', None), 'volume', 0)

            samples.append({
                "strike": strike,
                "expiry": expiry,
                "price": last_price,
                "oi": oi,
                "vol": vol
            })

            if not (current_price * 0.75 <= strike <= current_price * 1.40):
                continue
            if last_price < 0.05:
                continue

            expected_catch = abs(move_pct) * 0.7 * (current_price * 0.015)
            predicted_sell = last_price + expected_catch
            profit_pct = ((predicted_sell - last_price) / last_price) * 100

            if profit_pct > profit_threshold:
                opportunities.append({
                    "expiry": expiry,
                    "strike": round(strike, 2),
                    "buy_target": round(last_price * 0.96, 2),
                    "sell_target": round(predicted_sell, 2),
                    "profit_pct": round(profit_pct, 1),
                    "move_pct": round(move_pct, 2),
                    "oi": oi,
                    "vol": vol,
                    "reason": f"Stock moved **{move_pct:.1f}%**. LEAP lagging.",
                })

        # Show sample data
        if show_debug and samples:
            st.subheader("📋 Sample LEAPs from Polygon")
            sample_df = pd.DataFrame(samples)
            st.dataframe(sample_df, use_container_width=True)

        opportunities = sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        st.success(f"✅ **{len(opportunities)}** opportunities found above {profit_threshold}% threshold")

        return opportunities, []

    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return [], []

# ==================== UI ====================
mode = st.sidebar.radio("Mode", ["Live", "Dummy (Backtest)"], horizontal=True)

st.sidebar.subheader("Add Ticker")
new_ticker = st.sidebar.text_input("Ticker", "").upper().strip()
if st.sidebar.button("Add Ticker") and new_ticker:
    if new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.rerun()

dummy_date = dummy_time = None
if mode == "Dummy (Backtest)":
    st.sidebar.subheader("Backtest Settings")
    dummy_date = st.sidebar.date_input("Date", datetime.now().date() - timedelta(days=1))
    dummy_time = st.sidebar.time_input("Time", datetime.strptime("11:00", "%H:%M").time())

for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    
    if st.button(f"🔍 Scan {ticker}", key=f"scan_{ticker}"):
        with st.spinner(f"Scanning {ticker}..."):
            opps, _ = analyze_leap_lag(
                ticker, 
                dummy_mode=(mode == "Dummy (Backtest)"),
                dummy_date=dummy_date,
                dummy_time=dummy_time
            )
            st.session_state.opportunities[ticker] = {"opps": opps}
            st.rerun()
    
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker].get("opps", [])
        if opps:
            st.success(f"**Opportunities for {ticker}**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Buy Target", f"${opp['buy_target']}")
                        st.metric("Sell Target", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
        else:
            st.warning("No opportunities found above threshold.")

st.caption("LEAPs Lag Hunter • Polygon.io Debug Mode")

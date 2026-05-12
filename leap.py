import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import os

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**MAXIMUM DEBUG MODE** — Polygon Data Verification")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# ==================== SIDEBAR ====================
st.sidebar.subheader("🔑 Polygon.io API Key")
api_key = st.sidebar.text_input("API Key", type="password", value=os.getenv("POLYGON_API_KEY", ""))
if not api_key:
    st.sidebar.error("API Key missing")
    st.stop()

client = RESTClient(api_key=api_key)

st.sidebar.subheader("💰 Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

st.sidebar.subheader("⚙️ Settings")
profit_threshold = st.sidebar.slider("Min Profit %", 0.01, 5.0, 0.1, 0.05)
aggressive = st.sidebar.checkbox("Aggressive Mode (5x expected move)", value=True)
show_table = st.sidebar.checkbox("Always Show Full LEAPs Table", value=True)

# ==================== ANALYSIS ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        st.subheader(f"🔍 {ticker} Analysis")

        # Stock Data
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            from_date = (target_dt - timedelta(days=7)).date()
            to_date = (target_dt + timedelta(days=2)).date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))
        else:
            from_date = (datetime.now() - timedelta(days=2)).date()
            to_date = datetime.now().date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))

        if len(aggs) < 5:
            st.error("No stock data")
            return []

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

        st.success(f"✅ Polygon Stock: **${current_price:.2f}** | Move: **{move_pct:+.1f}%**")

        # Options
        today = datetime.now().date()
        candidates = []

        params = {
            "expiration_date.gte": (today + timedelta(days=180)).strftime("%Y-%m-%d"),
            "expiration_date.lte": (today + timedelta(days=730)).strftime("%Y-%m-%d"),
            "contract_type": "call",
        }

        chain = list(client.list_snapshot_options_chain(ticker, params=params))
        st.info(f"✅ **{len(chain)} LEAP calls returned by Polygon**")

        mult = 5.0 if aggressive else 1.0

        for opt in chain:
            strike = float(opt.details.strike_price)
            if not (current_price * 0.70 <= strike <= current_price * 1.50):
                continue

            last_price = 0.0
            if hasattr(opt, 'last_trade') and opt.last_trade and opt.last_trade.price:
                last_price = float(opt.last_trade.price)
            elif hasattr(opt, 'day') and opt.day and opt.day.close:
                last_price = float(opt.day.close)

            if last_price < 0.05:
                continue

            expected_catch = abs(move_pct) * 0.7 * (current_price * 0.02) * mult
            predicted_sell = last_price + expected_catch
            profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0

            candidates.append({
                "Expiry": opt.details.expiration_date,
                "Strike": round(strike, 2),
                "Last Price": round(last_price, 2),
                "Profit %": round(profit_pct, 2),
                "OI": getattr(opt, 'open_interest', 0),
                "Vol": getattr(getattr(opt, 'day', None), 'volume', 0)
            })

        if show_table and candidates:
            st.subheader("📊 All Candidate LEAPs from Polygon (Sorted by Profit)")
            df_cand = pd.DataFrame(candidates)
            df_cand = df_cand.sort_values(by="Profit %", ascending=False)
            st.dataframe(df_cand.head(30), use_container_width=True)

        # Opportunities (very low threshold)
        opps = [c for c in candidates if c["Profit %"] > profit_threshold]
        st.success(f"**{len(opps)} opportunities** above {profit_threshold}% threshold")

        return opps

    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []

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
        with st.spinner("Pulling data from Polygon..."):
            opps = analyze_leap_lag(
                ticker, 
                dummy_mode=(mode == "Dummy (Backtest)"),
                dummy_date=dummy_date,
                dummy_time=dummy_time
            )
            st.session_state.opportunities[ticker] = opps
            st.rerun()
    
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            st.success(f"**Opportunities for {ticker}**")
            for opp in opps[:5]:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["Expiry"])
                        st.metric("Strike", f"${opp['Strike']}")
                    with c2:
                        st.metric("Buy", f"${opp['Last Price']}")
                    with c3:
                        st.metric("Profit", f"{opp['Profit %']}%", delta=f"{opp['Profit %']}%")
        else:
            st.warning("No opportunities above threshold (check table above)")

st.caption("Polygon.io is now fully connected — look at the big table!")

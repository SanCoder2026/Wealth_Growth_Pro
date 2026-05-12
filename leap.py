import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import os

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**MAX DEBUG MODE • Verifying Polygon.io Data**")

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

st.sidebar.subheader("⚙️ Debug Settings")
profit_threshold = st.sidebar.slider("Minimum Profit % Threshold", 0.1, 10.0, 0.5, 0.1)
aggressive_mode = st.sidebar.checkbox("Aggressive Test Mode (3x catch-up)", value=True)
show_all_candidates = st.sidebar.checkbox("Show Full Candidate LEAPs Table", value=True)

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        st.subheader(f"🔍 Scanning {ticker}...")

        # === 1. STOCK PRICE & MOVE (this part already works) ===
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            from_date = (target_dt - timedelta(days=7)).date()
            to_date = (target_dt + timedelta(days=2)).date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))
            st.info("🕒 Using DUMMY mode (historical stock bars)")
        else:
            from_date = (datetime.now() - timedelta(days=2)).date()
            to_date = datetime.now().date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))

        if len(aggs) < 10:
            st.error("❌ Not enough stock bars from Polygon")
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

        st.success(f"✅ **Stock Data (Polygon)**: ${current_price:.2f} | Recent move: **{move_pct:+.1f}%**")

        # === 2. LONG-DATED LEAP CALLS FROM POLYGON ===
        today = datetime.now().date()
        candidates = []
        opportunities = []

        params = {
            "expiration_date.gte": (today + timedelta(days=180)).strftime("%Y-%m-%d"),
            "expiration_date.lte": (today + timedelta(days=730)).strftime("%Y-%m-%d"),
            "contract_type": "call",
        }

        chain = list(client.list_snapshot_options_chain(ticker, params=params))
        st.info(f"✅ **Polygon returned {len(chain)} long-dated LEAP calls** for {ticker}")

        multiplier = 3.0 if aggressive_mode else 1.0

        for opt in chain:
            strike = float(opt.details.strike_price)
            expiry = opt.details.expiration_date

            # Price extraction
            last_price = 0.0
            if hasattr(opt, 'last_trade') and opt.last_trade and opt.last_trade.price:
                last_price = float(opt.last_trade.price)
            elif hasattr(opt, 'day') and opt.day and opt.day.close:
                last_price = float(opt.day.close)

            oi = getattr(opt, 'open_interest', 0)
            vol = getattr(getattr(opt, 'day', None), 'volume', 0)

            # Only consider reasonable strikes
            if not (current_price * 0.75 <= strike <= current_price * 1.40):
                continue
            if last_price < 0.05:
                continue

            expected_catch = abs(move_pct) * 0.7 * (current_price * 0.015) * multiplier
            predicted_sell = last_price + expected_catch
            profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0

            candidate = {
                "expiry": expiry,
                "strike": round(strike, 2),
                "last_price": round(last_price, 2),
                "expected_catch": round(expected_catch, 2),
                "predicted_sell": round(predicted_sell, 2),
                "profit_pct": round(profit_pct, 1),
                "oi": oi,
                "vol": vol
            }
            candidates.append(candidate)

            if profit_pct > profit_threshold:
                opportunities.append(candidate)

        # === DEBUG TABLES ===
        st.info(f"Found {len(candidates)} candidate LEAPs in strike range")

        if show_all_candidates and candidates:
            st.subheader("📋 **All Candidate LEAPs from Polygon** (this proves data is coming)")
            df_candidates = pd.DataFrame(candidates)
            df_candidates = df_candidates.sort_values(by="profit_pct", ascending=False)
            st.dataframe(df_candidates.head(20), use_container_width=True)  # Show top 20

        opportunities = sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]

        if opportunities:
            st.success(f"✅ **{len(opportunities)} opportunities found** above {profit_threshold}%")
        else:
            st.warning("No opportunities above threshold. See table above for why.")

        return opportunities, candidates

    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
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
    st.sidebar.warning("⚠️ Note: Dummy mode uses current option prices (not historical)")

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
            st.success(f"**Top Opportunities for {ticker}**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Buy Target", f"${opp.get('last_price', opp['buy_target']):.2f}")
                        st.metric("Sell Target", f"${opp.get('predicted_sell', opp.get('sell_target', 0)):.2f}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
        else:
            st.warning("No opportunities above threshold found.")

st.caption("LEAPs Lag Hunter • MAX DEBUG • Polygon.io Data Verified")

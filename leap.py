import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import os

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter - FINAL DIAGNOSTIC")
st.markdown("**Your API Key is now hardcoded**")

# ==================== HARD CODED API KEY ====================
POLYGON_API_KEY = "uAtvNOthTdL4_e14lb70lFm7EGZhjvqQ"
client = RESTClient(api_key=POLYGON_API_KEY)

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# Sidebar
st.sidebar.subheader("💰 Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

st.sidebar.subheader("⚙️ Settings")
profit_threshold = st.sidebar.slider("Min Profit % Threshold", 0.01, 5.0, 0.3, 0.05)
use_fallback = st.sidebar.checkbox("Use Fallback Method", value=True)
aggressive = st.sidebar.checkbox("Aggressive Mode (Bigger Expected Catch)", value=True)

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

        if len(aggs) < 5:
            st.error("❌ Not enough stock data")
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

        st.success(f"✅ Polygon Stock Price: **${current_price:.2f}** | Move: **{move_pct:+.1f}%**")

        # === OPTIONS DATA ===
        today = datetime.now().date()
        candidates = []
        opportunities = []

        mult = 5.0 if aggressive else 1.0

        # Try Snapshot Chain first
        try:
            params = {
                "expiration_date.gte": (today + timedelta(days=100)).strftime("%Y-%m-%d"),
                "contract_type": "call",
            }
            chain = list(client.list_snapshot_options_chain(ticker, params=params))
            st.info(f"✅ Snapshot Chain: {len(chain)} LEAPs found")
        except:
            chain = []
            st.warning("Snapshot failed, trying fallback...")

        if len(chain) == 0 and use_fallback:
            # Fallback method
            contracts = list(client.list_options_contracts(
                underlying_ticker=ticker,
                expiration_date_gte=(today + timedelta(days=100)).strftime("%Y-%m-%d"),
                contract_type="call",
                limit=1000
            ))
            st.info(f"✅ Fallback found {len(contracts)} contracts")

            for contract in contracts[:300]:   # Limit requests
                try:
                    snap = client.get_snapshot_option(contract.ticker)
                    last_price = 0.0
                    if hasattr(snap, 'last_trade') and snap.last_trade and snap.last_trade.price:
                        last_price = float(snap.last_trade.price)
                    elif hasattr(snap, 'day') and snap.day and snap.day.close:
                        last_price = float(snap.day.close)

                    strike = float(contract.strike_price)
                    if not (current_price * 0.7 <= strike <= current_price * 1.5):
                        continue
                    if last_price < 0.05:
                        continue

                    expected_catch = abs(move_pct) * 0.8 * current_price * 0.025 * mult
                    predicted_sell = last_price + expected_catch
                    profit_pct = ((predicted_sell - last_price) / last_price) * 100

                    candidates.append({
                        "Expiry": contract.expiration_date,
                        "Strike": round(strike, 2),
                        "Last Price": round(last_price, 2),
                        "Profit %": round(profit_pct, 2),
                        "OI": getattr(snap, 'open_interest', 0)
                    })

                    if profit_pct > profit_threshold:
                        opportunities.append(candidates[-1])
                except:
                    continue
        else:
            # Use snapshot chain
            for opt in chain:
                strike = float(opt.details.strike_price)
                if not (current_price * 0.7 <= strike <= current_price * 1.5):
                    continue

                last_price = 0.0
                if hasattr(opt, 'last_trade') and opt.last_trade and opt.last_trade.price:
                    last_price = float(opt.last_trade.price)
                elif hasattr(opt, 'day') and opt.day and opt.day.close:
                    last_price = float(opt.day.close)

                if last_price < 0.05:
                    continue

                expected_catch = abs(move_pct) * 0.8 * current_price * 0.025 * mult
                predicted_sell = last_price + expected_catch
                profit_pct = ((predicted_sell - last_price) / last_price) * 100

                candidates.append({
                    "Expiry": opt.details.expiration_date,
                    "Strike": round(strike, 2),
                    "Last Price": round(last_price, 2),
                    "Profit %": round(profit_pct, 2),
                    "OI": getattr(opt, 'open_interest', 0)
                })

                if profit_pct > profit_threshold:
                    opportunities.append(candidates[-1])

        # Show results
        if candidates:
            st.subheader("📊 All Candidate LEAPs (Sorted by Profit %)")
            df = pd.DataFrame(candidates)
            df = df.sort_values(by="Profit %", ascending=False)
            st.dataframe(df.head(30), use_container_width=True)

        st.success(f"**{len(opportunities)} opportunities** found above {profit_threshold}%")

        return opportunities[:5]

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
        with st.spinner("Fetching from Polygon.io..."):
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
            st.success(f"**Found Opportunities for {ticker}**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["Expiry"])
                        st.metric("Strike", f"${opp['Strike']}")
                    with c2:
                        st.metric("Buy Target", f"${opp['Last Price']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['Profit %']}%", delta=f"{opp['Profit %']}%")
        else:
            st.warning("No opportunities above threshold (check table above)")

st.caption("Your API key is hardcoded. Look for the big data table after scanning.")

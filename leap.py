import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Detect pricing lag in long-dated options during fast moves**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]

if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        tk = yf.Ticker(ticker)
        
        if dummy_mode and dummy_date and dummy_time:
            # === DUMMY / BACKTEST MODE ===
            target_dt = datetime.combine(dummy_date, dummy_time)
            hist = tk.history(start=target_dt - timedelta(days=5), 
                            end=target_dt + timedelta(days=2), 
                            interval="5m")
            
            # Find closest timestamp
            hist.index = hist.index.tz_localize(None)
            closest = hist.index.get_indexer([target_dt], method='nearest')[0]
            if closest < 0 or closest >= len(hist):
                return []
            
            current_price = hist['Close'].iloc[closest]
            # Simulate 1 hour later price
            one_hour_later_idx = min(closest + 12, len(hist)-1)
            price_1h_later = hist['Close'].iloc[one_hour_later_idx]
            move_1h_pct = (price_1h_later - current_price) / current_price * 100
        else:
            # === LIVE MODE ===
            hist = tk.history(period="2d", interval="5m")
            if len(hist) < 12:
                return []
            current_price = hist['Close'].iloc[-1]
            price_1h_ago = hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0]
            move_1h_pct = (current_price - price_1h_ago) / price_1h_ago * 100

        if abs(move_1h_pct) < 0.7:
            return []

        # Get long-dated expirations (6 months to 2 years)
        expirations = tk.options
        long_exps = [exp for exp in expirations 
                     if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:12]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            relevant = calls[calls['strike'].between(current_price * 0.88, current_price * 1.18)]
            
            for _, row in relevant.iterrows():
                strike = row['strike']
                last_price = row['lastPrice']
                if last_price < 0.25:
                    continue
                
                intrinsic = max(0, current_price - strike)
                extrinsic = last_price - intrinsic
                
                expected_catch = abs(move_1h_pct) * 0.45 * (current_price * 0.009)
                predicted_sell = last_price + expected_catch
                profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0
                
                if profit_pct > 9:
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.96, 2),
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_1h": round(move_1h_pct, 2)
                    })
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:3]
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []

# ==================== SIDEBAR ====================
mode = st.sidebar.radio("Mode", ["Live", "Dummy (Backtest)"], horizontal=True)

st.sidebar.subheader("Tickers")
new_ticker = st.sidebar.text_input("Add Ticker", placeholder="SOXL").upper().strip()
if st.sidebar.button("Add Ticker") and new_ticker:
    if new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.rerun()

# Dummy Mode Controls
dummy_date = dummy_time = None
if mode == "Dummy (Backtest)":
    st.sidebar.subheader("Backtest Settings")
    dummy_date = st.sidebar.date_input("Date", value=datetime.now().date() - timedelta(days=5))
    dummy_time = st.sidebar.time_input("Time (approx)", value=datetime.strptime("10:30", "%H:%M").time())

# ==================== MAIN UI ====================
for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button(f"🔍 Scan {ticker}", key=f"scan_{ticker}"):
            with st.spinner(f"Analyzing {ticker}..."):
                result = analyze_leap_lag(
                    ticker, 
                    dummy_mode=(mode == "Dummy (Backtest)"),
                    dummy_date=dummy_date,
                    dummy_time=dummy_time
                )
                st.session_state.opportunities[ticker] = result
                st.rerun()
    
    # Display Results
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            move = opps[0].get('move_1h', 0)
            st.success(f"**Top Opportunities** (Simulated 1h move: {move}%)")
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
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", 
                                 delta=f"{opp['profit_pct']}%")
        else:
            st.info("No strong opportunities found for the selected time.")
    else:
        st.info(f"Click **Scan {ticker}** to analyze")

st.caption("LEAPs Lag Hunter • Dummy mode uses historical price data for backtesting")

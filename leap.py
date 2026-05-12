import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Dummy Mode Note: Option prices are current (not historical)**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

st.sidebar.subheader("💰 Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        tk = yf.Ticker(ticker)
        
        # Stock Move
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            hist = tk.history(start=target_dt - timedelta(days=10), 
                            end=target_dt + timedelta(days=3), interval="5m")
            if hist.empty:
                return []
            hist.index = hist.index.tz_localize(None)
            closest_idx = (hist.index - target_dt).map(abs).argmin()
            current_price = float(hist['Close'].iloc[closest_idx])
            later_idx = min(closest_idx + 12, len(hist)-1)
            price_later = float(hist['Close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
            st.info(f"📍 Dummy: Stock price at {hist.index[closest_idx].strftime('%H:%M')} = ${current_price:.2f}")
        else:
            hist = tk.history(period="2d", interval="5m")
            current_price = float(hist['Close'].iloc[-1])
            price_ago = float(hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        st.success(f"**{ticker}** ≈ ${current_price:.2f} | Move: **{move_pct:+.1f}%**")

        # Options (Always current chain)
        expirations = tk.options
        long_exps = [exp for exp in expirations if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        for exp in long_exps[:15]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            relevant = calls[calls['strike'].between(current_price * 0.70, current_price * 1.45)]
            
            for _, row in relevant.iterrows():
                strike = float(row['strike'])
                last_price = float(row['lastPrice'])
                if last_price < 0.10:
                    continue
                
                expected_catch = abs(move_pct) * 0.68 * current_price * 0.018
                predicted_sell = last_price + expected_catch
                profit_pct = ((predicted_sell - last_price) / last_price) * 100
                
                if profit_pct > 1.5:
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.965, 2),
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2),
                        "reason": f"Stock moved **{move_pct:.1f}%**. LEAP lagging.",
                    })

        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]

    except Exception as e:
        st.error(str(e))
        return []

# UI remains same as before...
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
    dummy_time = st.sidebar.time_input("Time", datetime.strptime("11:30", "%H:%M").time())

# ... (rest of your UI code - you can keep the same as last version)
for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    if st.button(f"🔍 Scan {ticker}", key=f"scan_{ticker}"):
        with st.spinner(f"Scanning {ticker}..."):
            result = analyze_leap_lag(ticker, mode == "Dummy (Backtest)", dummy_date, dummy_time)
            st.session_state.opportunities[ticker] = result
            st.rerun()
    
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            st.success(f"**Top Opportunities for {ticker}**")
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
                    st.write(opp.get("reason", ""))
        else:
            st.warning("No opportunities found.")

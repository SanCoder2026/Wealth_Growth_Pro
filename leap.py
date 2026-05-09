import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter - Live Mode")
st.markdown("**Real-time scanning • Top 5 Opportunities**")

if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]

if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

st.sidebar.subheader("💰 Your Trading Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

def analyze_leap_lag(ticker):
    try:
        tk = yf.Ticker(ticker)
        
        # Real-time price + last 1 hour
        hist = tk.history(period="1d", interval="5m")
        if len(hist) < 10:
            st.error("Not enough data yet. Try during market hours.")
            return []
        
        current_price = float(hist['Close'].iloc[-1])
        price_1h_ago = float(hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0])
        move_pct = (current_price - price_1h_ago) / price_1h_ago * 100

        # Get long-dated options
        expirations = tk.options
        long_exps = [exp for exp in expirations 
                     if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:12]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            
            # Wide range to catch more opportunities
            relevant = calls[calls['strike'].between(current_price * 0.70, current_price * 1.45)]
            
            for _, row in relevant.iterrows():
                strike = float(row['strike'])
                last_price = float(row['lastPrice'])
                if last_price < 0.15:
                    continue
                
                expected_catch = abs(move_pct) * 0.75 * (current_price * 0.018)   # More aggressive
                predicted_sell = last_price + expected_catch
                profit_pct = ((predicted_sell - last_price) / last_price) * 100
                
                if profit_pct > 2.0:
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.97, 2),
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2),
                        "reason": f"Stock moved **{move_pct:.1f}%** in last ~1 hour. Long-dated option lagging."
                    })
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []

# UI
mode = st.sidebar.radio("Mode", ["Live", "Dummy (Backtest)"], horizontal=True)

st.sidebar.subheader("Add Ticker")
new_ticker = st.sidebar.text_input("Ticker", "").upper().strip()
if st.sidebar.button("Add Ticker") and new_ticker:
    if new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.rerun()

for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    
    if st.button(f"🔍 Scan {ticker} Now", key=f"scan_{ticker}"):
        with st.spinner(f"Fetching real-time data for {ticker}..."):
            result = analyze_leap_lag(ticker)
            st.session_state.opportunities[ticker] = result
            st.rerun()
    
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            st.success(f"**Top 5 Live Opportunities for {ticker}**")
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
                    st.write(opp["reason"])
        else:
            st.info("No opportunities above 2% found in current move.")

st.caption("Live mode uses real-time yfinance data • Works best during US market hours (9:30 AM - 4:00 PM ET)")

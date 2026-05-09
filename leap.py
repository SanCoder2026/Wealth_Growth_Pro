import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Find short-term pricing lag in long-dated options during fast moves**")

# Session state
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]

if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# ==================== CORE ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker):
    try:
        tk = yf.Ticker(ticker)
        
        # Get recent price data (last 1 hour+)
        hist = tk.history(period="2d", interval="5m")
        if len(hist) < 12:
            return []
        
        current_price = hist['Close'].iloc[-1]
        price_1h_ago = hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0]
        move_1h_pct = (current_price - price_1h_ago) / price_1h_ago * 100
        
        if abs(move_1h_pct) < 0.8:   # Need decent move
            return []
        
        # Get option expirations (up to 2 years, min 6 months)
        expirations = tk.options
        long_exps = [
            exp for exp in expirations 
            if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730
        ]
        
        opportunities = []
        
        for exp in long_exps[:15]:   # Scan reasonable number
            chain = tk.option_chain(exp)
            calls = chain.calls
            
            # Focus on near ATM calls
            relevant = calls[calls['strike'].between(current_price * 0.88, current_price * 1.18)]
            
            for _, row in relevant.iterrows():
                strike = row['strike']
                last_price = row['lastPrice']
                if last_price < 0.20:
                    continue
                
                intrinsic = max(0, current_price - strike)
                extrinsic = last_price - intrinsic
                
                # Predict catch-up
                expected_catch = abs(move_1h_pct) * 0.45 * (current_price * 0.008)  # conservative estimate
                predicted_sell = last_price + expected_catch
                
                profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0
                
                if profit_pct > 10:   # Only good opportunities
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.97, 2),   # slight discount
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_1h": round(move_1h_pct, 2)
                    })
        
        # Return top 3
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:3]
        
    except Exception as e:
        st.error(f"Error analyzing {ticker}: {str(e)}")
        return []

# ==================== SIDEBAR ====================
st.sidebar.subheader("Add New Ticker")
new_ticker = st.sidebar.text_input("Ticker Symbol", placeholder="SOXL, TQQQ, IBIT...").upper().strip()

if st.sidebar.button("➕ Add Ticker") and new_ticker:
    if new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.success(f"✅ Added {new_ticker}")
        st.rerun()
    else:
        st.warning("Ticker already exists")

# ==================== MAIN DISPLAY ====================
for ticker in st.session_state.tickers[:]:
    st.subheader(f"📌 {ticker}")
    
    col_btn, col_status = st.columns([1, 5])
    with col_btn:
        if st.button(f"🔍 Scan {ticker}", key=f"scan_{ticker}"):
            with st.spinner(f"Analyzing {ticker}..."):
                result = analyze_leap_lag(ticker)
                st.session_state.opportunities[ticker] = result
                st.rerun()
    
    # Display opportunities
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            st.success(f"**Top 3 Opportunities for {ticker}** (Last 1h move: {opps[0].get('move_1h', 0)}%)")
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
            st.info(f"No strong lag opportunities detected for {ticker} in the last 1 hour.")
    else:
        st.info(f"Click **Scan {ticker}** to find opportunities.")

st.caption("LEAPs Lag Hunter • Scans long-dated options (6 months – 2 years) for pricing lag")

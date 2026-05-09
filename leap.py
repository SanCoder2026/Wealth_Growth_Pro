import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Find short-term pricing lag in long-dated options during fast moves**")

# Session state for tickers and opportunities
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]  # Default

if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# Sidebar
st.sidebar.subheader("Add Ticker")
new_ticker = st.sidebar.text_input("Ticker Symbol", placeholder="e.g. SOXL, TQQQ, IBIT").upper().strip()

if st.sidebar.button("Add Ticker") and new_ticker:
    if new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.success(f"Added {new_ticker}")
        st.rerun()
    else:
        st.warning("Ticker already added")

# Main UI
for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button(f"🔍 Find Top 3 Opportunities", key=f"btn_{ticker}"):
            with st.spinner(f"Scanning {ticker}..."):
                result = analyze_leap_lag(ticker)
                st.session_state.opportunities[ticker] = result
                st.rerun()
    
    # Show opportunities box
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            st.success(f"**Top Opportunities for {ticker}** (based on last 1h move)")
            for opp in opps:
                with st.container(border=True):
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']:.2f}")
                    with col_b:
                        st.metric("Buy Target", f"${opp['buy_target']:.2f}")
                        st.metric("Predicted Sell", f"${opp['sell_target']:.2f}")
                    with col_c:
                        profit_pct = opp['profit_pct']
                        st.metric("Possible Profit", f"{profit_pct:.1f}%", 
                                 delta=f"{profit_pct:.1f}%" if profit_pct > 0 else None,
                                 delta_color="normal")
        else:
            st.info("No strong lag opportunities found in last 1 hour.")
    else:
        st.info("Click the button above to scan for opportunities.")

# ==================== CORE ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker):
    try:
        tk = yf.Ticker(ticker)
        
        # Get current price and last 1-hour change
        hist = tk.history(period="5d", interval="5m")
        if len(hist) < 12:  # Need at least ~1 hour data
            return []
        
        current_price = hist['Close'].iloc[-1]
        price_1h_ago = hist['Close'].iloc[-12] if len(hist) >= 12 else hist['Close'].iloc[0]
        move_1h = (current_price - price_1h_ago) / price_1h_ago * 100
        
        if abs(move_1h) < 0.8:  # Only look for meaningful moves
            return []
        
        # Get option expirations (next 2 years)
        expirations = tk.options
        long_exps = [exp for exp in expirations if 
                     (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730 and
                     (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days >= 180]
        
        opportunities = []
        
        for exp in long_exps[:12]:  # Limit scan
            chain = tk.option_chain(exp)
            calls = chain.calls
            
            # Focus on slightly OTM to ATM calls
            relevant_calls = calls[calls['strike'].between(current_price * 0.90, current_price * 1.15)]
            
            for _, row in relevant_calls.iterrows():
                strike = row['strike']
                last_price = row['lastPrice']
                if last_price <= 0.10:
                    continue
                
                intrinsic = max(0, current_price - strike)
                extrinsic = last_price - intrinsic
                
                # Simple prediction: assume 40-60% of the move catches up in long-dated
                expected_catch = abs(move_1h) * 0.5 * (current_price * 0.01)  # rough gamma effect
                predicted_sell = last_price + expected_catch
                
                profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0
                
                if profit_pct > 8:  # Only show decent opportunities
                    opportunities.append({
                        "expiry": exp,
                        "strike": strike,
                        "buy_target": round(last_price * 0.98, 2),   # Buy slightly below last
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": profit_pct
                    })
        
        # Return top 3 by profit potential
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:3]
        
    except Exception as e:
        st.error(f"Error scanning {ticker}: {str(e)}")
        return []

st.caption("LEAPs Lag Hunter — Scans for pricing lag in long-dated calls during fast moves")
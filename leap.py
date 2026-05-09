import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Detect pricing lag in long-dated options**")

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
            # Dummy / Backtest Mode
            target_dt = datetime.combine(dummy_date, dummy_time)
            # Get more history for better matching
            hist = tk.history(start=target_dt - timedelta(days=7), 
                            end=target_dt + timedelta(days=1), 
                            interval="5m")
            if hist.empty:
                return []
            
            hist.index = hist.index.tz_localize(None)
            
            # Find closest timestamp
            closest_idx = (hist.index - target_dt).abs().argmin()
            current_price = hist['Close'].iloc[closest_idx]
            
            # Look 30–60 minutes ahead for move
            later_idx = min(closest_idx + 12, len(hist)-1)
            price_later = hist['Close'].iloc[later_idx]
            move_pct = (price_later - current_price) / current_price * 100
        else:
            # Live Mode
            hist = tk.history(period="2d", interval="5m")
            if len(hist) < 10:
                return []
            current_price = hist['Close'].iloc[-1]
            price_1h_ago = hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0]
            move_pct = (current_price - price_1h_ago) / price_1h_ago * 100

        if abs(move_pct) < 0.5:   # Lower threshold for testing
            return []

        # Get long-dated options (6 months to 2 years)
        expirations = tk.options
        long_exps = [exp for exp in expirations 
                     if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:15]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            
            # Wider range for more candidates
            relevant = calls[calls['strike'].between(current_price * 0.85, current_price * 1.25)]
            
            for _, row in relevant.iterrows():
                strike = row['strike']
                last_price = row['lastPrice']
                if last_price < 0.15:
                    continue
                
                intrinsic = max(0, current_price - strike)
                extrinsic = last_price - intrinsic
                
                # More aggressive catch-up assumption for testing
                expected_catch = abs(move_pct) * 0.55 * (current_price * 0.01)
                predicted_sell = last_price + expected_catch
                
                profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0
                
                if profit_pct > 6:   # Lowered threshold
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.97, 2),
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2)
                    })
        
        # Return top 5 for better visibility in testing
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        
    except Exception as e:
        st.error(f"Error analyzing {ticker}: {str(e)}")
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
    dummy_date = st.sidebar.date_input("Date", datetime.now().date())
    dummy_time = st.sidebar.time_input("Time", datetime.strptime("11:00", "%H:%M").time())

for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    
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
    
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            move = opps[0].get('move_pct', 0)
            st.success(f"**Found Opportunities** (Move: {move}%)")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Recommended Buy", f"${opp['buy_target']}")
                        st.metric("Target Sell", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
        else:
            st.warning("No opportunities found with current settings.")
    else:
        st.info(f"Click **Scan {ticker}** to start analysis.")

st.caption("Tip: In Dummy mode, try different times around big SOXL moves (e.g. 9:30–11:00 AM)")

import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Up & Down Market Support • Top 5 Opportunities**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

st.sidebar.subheader("💰 Your Trading Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

# ==================== ANALYSIS FUNCTION (Up + Down) ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        tk = yf.Ticker(ticker)
        
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            hist = tk.history(start=target_dt - timedelta(days=10), end=target_dt + timedelta(days=2), interval="5m")
            if hist.empty:
                return []
            hist.index = hist.index.tz_localize(None)
            time_diffs = (hist.index - target_dt).map(abs)
            closest_idx = time_diffs.argmin()
            current_price = float(hist['Close'].iloc[closest_idx])
            later_idx = min(closest_idx + 12, len(hist)-1)
            price_later = float(hist['Close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
        else:
            hist = tk.history(period="2d", interval="5m")
            if len(hist) < 12:
                return []
            current_price = float(hist['Close'].iloc[-1])
            price_ago = float(hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        direction = "UP" if move_pct > 0 else "DOWN"
        abs_move = abs(move_pct)

        expirations = tk.options
        long_exps = [exp for exp in expirations if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:12]:
            try:
                chain = tk.option_chain(exp)
                
                if direction == "UP":
                    # Look for lagging Calls
                    relevant = chain.calls[chain.calls['strike'].between(current_price * 0.75, current_price * 1.45)]
                    option_type = "Call"
                else:
                    # Look for lagging Puts in down market
                    relevant = chain.puts[chain.puts['strike'].between(current_price * 0.60, current_price * 1.25)]
                    option_type = "Put"
                
                for _, row in relevant.iterrows():
                    strike = float(row['strike'])
                    last_price = float(row['lastPrice'])
                    if last_price < 0.10:
                        continue
                    
                    expected_catch = abs_move * 0.75 * (current_price * 0.016)
                    predicted_sell = last_price + expected_catch
                    profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0
                    
                    if profit_pct > 2.0:
                        opportunities.append({
                            "type": option_type,
                            "expiry": exp,
                            "strike": round(strike, 2),
                            "buy_target": round(last_price * 0.96, 2),
                            "sell_target": round(predicted_sell, 2),
                            "profit_pct": round(profit_pct, 1),
                            "move_pct": round(move_pct, 2),
                            "reason": f"Strong {direction} move ({move_pct:.1f}%). Long-dated {option_type} showing lag.",
                            "target_reason": f"Buy near current price. Expected quick adjustment in {exp}."
                        })
            except:
                continue
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []

# ==================== UI ====================
mode = st.sidebar.radio("Mode", ["Live", "Dummy (Backtest)"], horizontal=True)

if mode == "Dummy (Backtest)":
    st.sidebar.subheader("Backtest Settings")
    dummy_date = st.sidebar.date_input("Date", datetime.now().date() - timedelta(days=1))
    dummy_time = st.sidebar.time_input("Time", datetime.strptime("11:00", "%H:%M").time())
else:
    dummy_date = dummy_time = None

st.sidebar.subheader("Add Ticker")
new_ticker = st.sidebar.text_input("Ticker", "").upper().strip()
if st.sidebar.button("Add Ticker") and new_ticker:
    if new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.rerun()

for ticker in st.session_state.tickers:
    st.subheader(f"📌 {ticker}")
    
    if st.button(f"🔍 Scan {ticker}", key=f"scan_{ticker}"):
        with st.spinner(f"Scanning {ticker}..."):
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
            st.success(f"**Top 5 Opportunities for {ticker}**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Type", opp["type"])
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Buy Target", f"${opp['buy_target']}")
                        st.metric("Sell Target", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
                    
                    st.markdown("**Why this?**")
                    st.write(opp["reason"])
                    st.write(opp["target_reason"])
        else:
            st.warning("No opportunities > 2% found.")

st.caption("Now supports both Up and Down markets • Puts in down moves, Calls in up moves")

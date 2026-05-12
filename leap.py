import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Fixed: Using Bid-Ask Midpoint for Accurate Pricing**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

st.sidebar.subheader("💰 Your Trading Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

# ==================== ANALYSIS FUNCTION (FIXED) ====================
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
        else:
            hist = tk.history(period="2d", interval="5m")
            current_price = float(hist['Close'].iloc[-1])
            price_ago = float(hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        st.success(f"**{ticker}** ≈ ${current_price:.2f} | Move: **{move_pct:+.1f}%**")

        # Long LEAPs
        expirations = tk.options
        long_exps = [exp for exp in expirations if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:20]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            
            relevant = calls[calls['strike'].between(current_price * 0.70, current_price * 1.45)]
            
            for _, row in relevant.iterrows():
                strike = float(row['strike'])
                
                # === FIXED PRICE EXTRACTION ===
                bid = float(row.get('bid', 0))
                ask = float(row.get('ask', 0))
                last = float(row.get('lastPrice', 0))
                
                # Use midpoint if bid/ask available, else fallback to lastPrice
                if bid > 0 and ask > 0:
                    mid_price = (bid + ask) / 2
                    price_used = mid_price
                    price_source = "Bid-Ask Mid"
                else:
                    price_used = last
                    price_source = "Last Price"
                
                if price_used < 0.10:
                    continue
                
                expected_catch = abs(move_pct) * 0.65 * current_price * 0.018
                predicted_sell = price_used + expected_catch
                profit_pct = ((predicted_sell - price_used) / price_used) * 100
                
                if profit_pct > 1.8:
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(price_used * 0.97, 2),   # Slight discount
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2),
                        "price_source": price_source,
                        "reason": f"Stock moved **{move_pct:.1f}%**. Using {price_source}.",
                    })

        sorted_opps = sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        return sorted_opps
        
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []

# ==================== UI (unchanged) ====================
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
                    
                    st.info(f"Price Source: {opp.get('price_source', 'Unknown')}")
                    st.write(opp.get("reason", ""))
        else:
            st.warning("No opportunities found.")

st.caption("Fixed: Now using Bid-Ask Midpoint for LEAP pricing")

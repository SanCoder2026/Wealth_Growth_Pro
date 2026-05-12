import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Realistic Mode: Using Ask for Buy & Bid for Sell**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL", "URA"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

st.sidebar.subheader("💰 Your Trading Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        tk = yf.Ticker(ticker)
        
        # Stock Move
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            hist = tk.history(start=target_dt - timedelta(days=10), end=target_dt + timedelta(days=3), interval="5m")
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

        expirations = tk.options
        long_exps = [exp for exp in expirations if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:20]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            relevant = calls[calls['strike'].between(current_price * 0.70, current_price * 1.45)]
            
            for _, row in relevant.iterrows():
                strike = float(row['strike'])
                
                bid = float(row.get('bid', 0))
                ask = float(row.get('ask', 0))
                last = float(row.get('lastPrice', 0))
                
                # Realistic pricing
                buy_price = ask if ask > 0 else last * 1.02   # Pay Ask or slight premium
                sell_price_estimate = bid if bid > 0 else last * 0.98  # Sell at Bid or slight discount
                
                if buy_price < 0.15 or buy_price > 200:   # Filter unrealistic prices
                    continue
                
                expected_catch = abs(move_pct) * 0.60 * current_price * 0.017   # More conservative
                predicted_sell = sell_price_estimate + expected_catch
                
                profit_pct = ((predicted_sell - buy_price) / buy_price) * 100
                
                if profit_pct > 2.0:   # Higher threshold due to spread
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(buy_price, 2),        # What you actually pay
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2),
                        "bid": round(bid, 2),
                        "ask": round(ask, 2),
                        "reason": f"Stock moved **{move_pct:.1f}%**. Using realistic Bid/Ask.",
                    })

        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        
    except Exception as e:
        st.error(f"Error with {ticker}: {str(e)}")
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
            st.success(f"**Top 5 Opportunities for {ticker}**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Buy Target (Ask)", f"${opp['buy_target']}")
                        st.metric("Sell Target (Bid+)", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
                    
                    st.caption(f"Bid: ${opp['bid']} | Ask: ${opp['ask']}")
                    st.write(opp["reason"])
        else:
            st.warning("No opportunities with realistic spread found.")

    # Best for Budget (unchanged logic)
    if ticker in st.session_state.opportunities and st.session_state.opportunities[ticker]:
        best = max(st.session_state.opportunities[ticker], 
                   key=lambda x: (budget // (x['buy_target'] * 100)) * (x['sell_target'] - x['buy_target']) * 100)
        
        option_cost = best['buy_target'] * 100
        max_contracts = int(budget // option_cost)
        
        st.subheader(f"💎 Best for Your ${budget:,.0f} Budget")
        with st.container(border=True):
            st.success(f"**Recommended: {ticker} {best['expiry']} ${best['strike']} Call**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Contracts", max_contracts)
                st.metric("Total Cost", f"${max_contracts * option_cost:,.0f}")
            with col2:
                st.metric("Buy @ Ask", f"${best['buy_target']:.2f}")
                st.metric("Target Sell", f"${best['sell_target']:.2f}")
            with col3:
                est_profit = max_contracts * (best['sell_target'] - best['buy_target']) * 100
                st.metric("Expected Profit", f"${est_profit:,.0f}", delta=f"{best['profit_pct']}%")

st.caption("Realistic Mode: Buy at Ask • Sell at Bid • Conservative Profit")

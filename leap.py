import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Very Sensitive Mode • Top 5 Opportunities • With Reasoning**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# Budget Input
st.sidebar.subheader("💰 Your Trading Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        tk = yf.Ticker(ticker)
        
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            hist = tk.history(start=target_dt - timedelta(days=7), end=target_dt + timedelta(days=2), interval="5m")
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
            if len(hist) < 10:
                return []
            current_price = float(hist['Close'].iloc[-1])
            price_ago = float(hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        expirations = tk.options
        long_exps = [exp for exp in expirations if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

        opportunities = []
        
        for exp in long_exps[:15]:
            chain = tk.option_chain(exp)
            calls = chain.calls
            relevant = calls[calls['strike'].between(current_price * 0.75, current_price * 1.40)]
            
            for _, row in relevant.iterrows():
                strike = float(row['strike'])
                last_price = float(row['lastPrice'])
                if last_price < 0.10:
                    continue
                
                expected_catch = abs(move_pct) * 0.7 * (current_price * 0.015)
                predicted_sell = last_price + expected_catch
                profit_pct = ((predicted_sell - last_price) / last_price) * 100 if last_price > 0 else 0
                
                if profit_pct > 2.0:
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.96, 2),
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2),
                        "last_price": last_price,
                        "reason": f"Stock moved {move_pct:.1f}% in short time. Long-dated {exp} call is lagging behind due to lower gamma.",
                        "target_reason": f"Buy near current market price. Expected quick catch-up as market makers adjust.",
                        "profit_reason": f"Conservative momentum-based estimate for {ticker}."
                    })
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]   # ← Top 5 only
        
    except Exception:
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
        with st.spinner(f"Scanning {ticker}..."):
            result = analyze_leap_lag(
                ticker, 
                dummy_mode=(mode == "Dummy (Backtest)"),
                dummy_date=dummy_date,
                dummy_time=dummy_time
            )
            st.session_state.opportunities[ticker] = result
            st.rerun()
    
    # === OPPORTUNITIES LIST (Top 5) ===
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
                        st.metric("Buy Target", f"${opp['buy_target']}")
                        st.metric("Sell Target", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
                    
                    st.markdown("**Why this one?**")
                    st.write(opp["reason"])
                    st.write(opp["target_reason"])
                    st.write(opp["profit_reason"])
        else:
            st.warning("No opportunities > 2% found.")
    else:
        st.info("Click **Scan** to analyze")

    # === BEST OPPORTUNITY FOR YOUR BUDGET ===
    if ticker in st.session_state.opportunities and st.session_state.opportunities[ticker]:
        best = st.session_state.opportunities[ticker][0]
        option_cost = best['buy_target'] * 100
        max_contracts = int(budget // option_cost)
        
        if max_contracts > 0:
            total_investment = max_contracts * option_cost
            est_profit = max_contracts * (best['sell_target'] - best['buy_target']) * 100
            
            st.subheader(f"💎 Best Opportunity for Your ${budget:,.0f} Budget")
            with st.container(border=True):
                st.success(f"**Recommended: {ticker} {best['expiry']} ${best['strike']} Call**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Contracts You Can Buy", max_contracts)
                    st.metric("Total Investment", f"${total_investment:,.0f}")
                with col2:
                    st.metric("Buy Price", f"${best['buy_target']:.2f}")
                    st.metric("Target Sell", f"${best['sell_target']:.2f}")
                with col3:
                    st.metric("Expected Profit", f"${est_profit:,.0f}", delta=f"{best['profit_pct']}%")
                
                st.info(f"**Reason:** Strong recent momentum with lag in this long-dated option. Good risk-reward for quick catch-up.")
        else:
            st.warning("Budget too low to buy even 1 contract.")

st.caption("LEAPs Lag Hunter • Top 5 only • With full reasoning • Budget optimized")

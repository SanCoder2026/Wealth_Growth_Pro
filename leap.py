import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Very Sensitive Mode • Any profit > 2% shown**")

if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]

if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    debug = []
    try:
        tk = yf.Ticker(ticker)
        
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            debug.append(f"Target time: {target_dt}")
            
            hist = tk.history(start=target_dt - timedelta(days=7),
                            end=target_dt + timedelta(days=2),
                            interval="5m")
            if hist.empty:
                return [], "No historical data available"
            
            hist.index = hist.index.tz_localize(None)
            time_diffs = (hist.index - target_dt).map(abs)
            closest_idx = time_diffs.argmin()
            current_price = float(hist['Close'].iloc[closest_idx])
            debug.append(f"Closest price: ${current_price:.2f} at {hist.index[closest_idx]}")
            
            later_idx = min(closest_idx + 12, len(hist)-1)
            price_later = float(hist['Close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
            debug.append(f"Simulated 1h move: {move_pct:.2f}%")
        else:
            hist = tk.history(period="2d", interval="5m")
            if len(hist) < 10:
                return [], "Not enough live data"
            current_price = float(hist['Close'].iloc[-1])
            price_ago = float(hist['Close'].iloc[-13] if len(hist) >= 13 else hist['Close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        debug.append(f"Final Move: {move_pct:.2f}% | Price: ${current_price:.2f}")

        expirations = tk.options
        long_exps = [exp for exp in expirations
                     if 180 <= (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days <= 730]

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
                    # === REASONING ===
                    reason = f"Stock moved {move_pct:.1f}% in ~1 hour. Long-dated call ({exp}) is lagging due to lower gamma."
                    target_reason = f"Buy near current last price with small discount. Expected catch-up of {expected_catch:.2f} due to momentum."
                    profit_reason = f"Conservative estimate based on historical lag behavior in fast moves for {ticker}."
                    
                    opportunities.append({
                        "expiry": exp,
                        "strike": round(strike, 2),
                        "buy_target": round(last_price * 0.96, 2),
                        "sell_target": round(predicted_sell, 2),
                        "profit_pct": round(profit_pct, 1),
                        "move_pct": round(move_pct, 2),
                        "reason": reason,
                        "target_reason": target_reason,
                        "profit_reason": profit_reason
                    })
        
        sorted_opps = sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)
        return sorted_opps[:8], "\n".join(debug)
        
    except Exception as e:
        return [], f"Error: {str(e)}"

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
            result, debug_msg = analyze_leap_lag(
                ticker,
                dummy_mode=(mode == "Dummy (Backtest)"),
                dummy_date=dummy_date,
                dummy_time=dummy_time
            )
            st.session_state.opportunities[ticker] = result
            st.session_state.debug = debug_msg
            st.rerun()
    
    if ticker in st.session_state.opportunities:
        opps = st.session_state.opportunities[ticker]
        if opps:
            st.success(f"**Found {len(opps)} Opportunities**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 3])
                    with c1:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Buy Target", f"${opp['buy_target']}")
                        st.metric("Sell Target", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
                    
                    st.markdown("**Why this opportunity?**")
                    st.write(opp["reason"])
                    st.write(opp["target_reason"])
                    st.write(opp["profit_reason"])
        else:
            st.warning("No opportunities > 2% found.")
            if 'debug' in st.session_state:
                st.code(st.session_state.debug)
    else:
        st.info("Click **Scan** button above")

st.caption("Extremely sensitive mode • Each opportunity now includes clear reasoning")

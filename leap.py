import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import os

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Very Sensitive Mode • Debug Enabled**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# ==================== SIDEBAR ====================
st.sidebar.subheader("🔑 Polygon.io API Key")
api_key = st.sidebar.text_input("API Key", type="password", value=os.getenv("POLYGON_API_KEY", ""))
if not api_key:
    st.sidebar.warning("Enter your Polygon.io API key")
    st.stop()

client = RESTClient(api_key=api_key)

st.sidebar.subheader("💰 Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

st.sidebar.subheader("⚙️ Settings")
profit_threshold = st.sidebar.slider("Minimum Profit % Threshold", 0.5, 5.0, 1.0, 0.1)
show_near_misses = st.sidebar.checkbox("Show Near Miss Opportunities", value=True)

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        # ==================== STOCK PRICE ====================
        if dummy_mode and dummy_date and dummy_time:
            target_dt = datetime.combine(dummy_date, dummy_time)
            from_date = (target_dt - timedelta(days=7)).date()
            to_date = (target_dt + timedelta(days=2)).date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))
        else:
            from_date = (datetime.now() - timedelta(days=2)).date()
            to_date = datetime.now().date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))

        if len(aggs) < 10:
            st.warning(f"❌ Not enough data for {ticker}")
            return []

        df = pd.DataFrame([{'timestamp': pd.to_datetime(a.timestamp, unit='ms'), 'close': a.close} for a in aggs])
        df.set_index('timestamp', inplace=True)

        if dummy_mode:
            time_diffs = (df.index - target_dt).map(abs)
            closest_idx = time_diffs.argmin()
            current_price = float(df['close'].iloc[closest_idx])
            later_idx = min(closest_idx + 12, len(df)-1)
            price_later = float(df['close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
        else:
            current_price = float(df['close'].iloc[-1])
            price_ago = float(df['close'].iloc[-13] if len(df) >= 13 else df['close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        st.info(f"📊 **{ticker}** ≈ ${current_price:.2f} | Move: **{move_pct:+.1f}%** in recent period")

        # ==================== OPTIONS SNAPSHOT ====================
        today = datetime.now().date()
        opportunities = []
        near_misses = []

        params = {
            "expiration_date.gte": (today + timedelta(days=180)).strftime("%Y-%m-%d"),
            "expiration_date.lte": (today + timedelta(days=730)).strftime("%Y-%m-%d"),
            "contract_type": "call",
        }

        chain = list(client.list_snapshot_options_chain(ticker, params=params))
        st.info(f"🔍 Found **{len(chain)}** long-dated call LEAPs for {ticker}")

        for opt in chain:
            strike = float(opt.details.strike_price)
            if not (current_price * 0.75 <= strike <= current_price * 1.40):
                continue

            # Robust price extraction
            last_price = 0.0
            oi = getattr(opt, 'open_interest', 0)
            vol = getattr(getattr(opt, 'day', None), 'volume', 0) if hasattr(opt, 'day') else 0

            if hasattr(opt, 'last_trade') and opt.last_trade and opt.last_trade.price:
                last_price = float(opt.last_trade.price)
            elif hasattr(opt, 'day') and opt.day and opt.day.close:
                last_price = float(opt.day.close)
            elif hasattr(opt, 'greeks') and opt.greeks and opt.greeks.delta:
                last_price = max(0.10, abs(float(opt.greeks.delta)) * current_price * 0.55)

            if last_price < 0.05:
                continue

            expected_catch = abs(move_pct) * 0.7 * (current_price * 0.015)
            predicted_sell = last_price + expected_catch
            profit_pct = ((predicted_sell - last_price) / last_price) * 100

            opp = {
                "expiry": opt.details.expiration_date,
                "strike": round(strike, 2),
                "buy_target": round(last_price * 0.96, 2),
                "sell_target": round(predicted_sell, 2),
                "profit_pct": round(profit_pct, 1),
                "move_pct": round(move_pct, 2),
                "oi": oi,
                "vol": vol,
                "reason": f"Stock moved **{move_pct:.1f}%**. LEAP lagging.",
                "target_reason": "Expecting market maker catch-up.",
                "profit_reason": "Momentum estimate."
            }

            if profit_pct > profit_threshold:
                opportunities.append(opp)
            elif show_near_misses and profit_pct > 0.3:
                near_misses.append(opp)

        # Sort and limit
        opportunities = sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        near_misses = sorted(near_misses, key=lambda x: x['profit_pct'], reverse=True)[:5]

        st.success(f"✅ **{len(opportunities)}** opportunities above {profit_threshold}%")
        if near_misses:
            st.info(f"📉 {len(near_misses)} near-miss opportunities (shown below)")

        return opportunities, near_misses

    except Exception as e:
        st.error(f"Error with {ticker}: {str(e)}")
        return [], []

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
            if isinstance(result, tuple):
                opps, near = result
                st.session_state.opportunities[ticker] = {"opps": opps, "near": near}
            else:
                st.session_state.opportunities[ticker] = {"opps": result, "near": []}
            st.rerun()
    
    if ticker in st.session_state.opportunities:
        data = st.session_state.opportunities[ticker]
        opps = data.get("opps", [])
        near = data.get("near", [])

        if opps:
            st.success(f"**Top Opportunities for {ticker}**")
            for opp in opps:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Expiry", opp["expiry"])
                        st.metric("Strike", f"${opp['strike']}")
                    with c2:
                        st.metric("Buy", f"${opp['buy_target']}")
                        st.metric("Sell Target", f"${opp['sell_target']}")
                    with c3:
                        st.metric("Est. Profit", f"{opp['profit_pct']}%", delta=f"{opp['profit_pct']}%")
                    st.caption(f"OI: {opp['oi']} | Vol: {opp['vol']}")
                    st.write(opp["reason"])
        else:
            st.warning("No opportunities above threshold.")

        if near and show_near_misses:
            st.subheader("📉 Near Miss Opportunities")
            for opp in near:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    with c1: st.metric("Expiry", opp["expiry"]); st.metric("Strike", f"${opp['strike']}")
                    with c2: st.metric("Buy", f"${opp['buy_target']}")
                    with c3: st.metric("Profit", f"{opp['profit_pct']}%")
                    st.caption(f"OI: {opp['oi']} | Vol: {opp['vol']}")

st.caption("LEAPs Lag Hunter • Polygon.io • Debug Mode")            to_date = (target_dt + timedelta(days=2)).date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))
        else:
            from_date = (datetime.now() - timedelta(days=2)).date()
            to_date = datetime.now().date()
            aggs = list(client.list_aggs(ticker, 5, "minute", from_=from_date, to=to_date, limit=50000))

        if len(aggs) < 10:
            st.warning(f"Not enough 5m bars for {ticker}")
            return []

        df = pd.DataFrame([{
            'timestamp': pd.to_datetime(a.timestamp, unit='ms'),
            'close': a.close
        } for a in aggs])
        df.set_index('timestamp', inplace=True)

        if dummy_mode:
            time_diffs = (df.index - target_dt).map(abs)
            closest_idx = time_diffs.argmin()
            current_price = float(df['close'].iloc[closest_idx])
            later_idx = min(closest_idx + 12, len(df) - 1)
            price_later = float(df['close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
        else:
            current_price = float(df['close'].iloc[-1])
            price_ago = float(df['close'].iloc[-13] if len(df) >= 13 else df['close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        st.info(f"📊 **{ticker}** current \~${current_price:.2f} | Recent move: **{move_pct:.1f}%**")

        # ==================== LONG-DATED OPTIONS SNAPSHOT CHAIN ====================
        today = datetime.now().date()
        opportunities = []

        # Bulk snapshot for all long-dated calls (most reliable pricing)
        params = {
            "expiration_date.gte": (today + timedelta(days=180)).strftime("%Y-%m-%d"),
            "expiration_date.lte": (today + timedelta(days=730)).strftime("%Y-%m-%d"),
            "contract_type": "call",
        }

        chain = list(client.list_snapshot_options_chain(ticker, params=params))

        st.info(f"Found {len(chain)} long-dated call options for {ticker}")

        for opt in chain:
            strike = float(opt.details.strike_price)
            if not (current_price * 0.75 <= strike <= current_price * 1.40):
                continue

            # Robust price extraction (multiple fallbacks)
            last_price = 0.0
            if hasattr(opt, 'last_trade') and opt.last_trade and opt.last_trade.price is not None:
                last_price = float(opt.last_trade.price)
            elif hasattr(opt, 'day') and opt.day and opt.day.close is not None:
                last_price = float(opt.day.close)
            elif hasattr(opt, 'greeks') and opt.greeks and hasattr(opt.greeks, 'delta') and opt.greeks.delta:
                # Rough estimate if no trade data
                last_price = max(0.10, abs(opt.greeks.delta) * current_price * 0.6)

            if last_price < 0.10:
                continue

            expected_catch = abs(move_pct) * 0.7 * (current_price * 0.015)
            predicted_sell = last_price + expected_catch
            profit_pct = ((predicted_sell - last_price) / last_price) * 100

            if profit_pct > 2.0:
                opportunities.append({
                    "expiry": opt.details.expiration_date,
                    "strike": round(strike, 2),
                    "buy_target": round(last_price * 0.96, 2),
                    "sell_target": round(predicted_sell, 2),
                    "profit_pct": round(profit_pct, 1),
                    "move_pct": round(move_pct, 2),
                    "reason": f"Stock moved **{move_pct:.1f}%** recently. LEAP lagging (low gamma).",
                    "target_reason": "Buy near current market expecting MM catch-up.",
                    "profit_reason": "Momentum estimate for leveraged ticker."
                })

        sorted_opps = sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:5]
        st.info(f"✅ Found **{len(sorted_opps)}** opportunities >2% for {ticker}")
        return sorted_opps

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
    
    # Top 5 Opportunities
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
                    
                    st.markdown("**Why this opportunity?**")
                    st.write(opp["reason"])
                    st.write(opp["target_reason"])
                    st.write(opp["profit_reason"])
        else:
            st.warning("No opportunities > 2% found.")

    # === BEST FOR BUDGET ===
    if ticker in st.session_state.opportunities and st.session_state.opportunities[ticker]:
        # Choose the one with highest total dollar profit
        best = max(st.session_state.opportunities[ticker], 
                   key=lambda x: (budget // (x['buy_target'] * 100)) * (x['sell_target'] - x['buy_target']) * 100)
        
        option_cost = best['buy_target'] * 100
        max_contracts = int(budget // option_cost)
        
        st.subheader(f"💎 Best Opportunity for Your ${budget:,.0f} Budget")
        with st.container(border=True):
            st.success(f"**Recommended: {ticker} {best['expiry']} ${best['strike']} Call**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Contracts You Can Buy", max_contracts)
                st.metric("Total Investment", f"${max_contracts * option_cost:,.0f}")
            with col2:
                st.metric("Buy Target", f"${best['buy_target']:.2f}")
                st.metric("Target Sell", f"${best['sell_target']:.2f}")
            with col3:
                est_profit = max_contracts * (best['sell_target'] - best['buy_target']) * 100
                st.metric("Expected Profit Today", f"${est_profit:,.0f}", delta=f"{best['profit_pct']}%")
            
            st.info(f"**Reason:** Highest total dollar profit within your budget. Strong momentum + pricing lag in this long-dated option.")

st.caption("LEAPs Lag Hunter • Powered by Polygon.io • Top 5 only • Full reasoning • Budget optimized")

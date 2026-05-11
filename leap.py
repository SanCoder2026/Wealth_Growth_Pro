import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import os

st.set_page_config(page_title="LEAPs Lag Hunter", layout="wide")
st.title("🚀 LEAPs Lag Hunter")
st.markdown("**Very Sensitive Mode • Top 5 Opportunities with Reasoning**")

# Session State
if "tickers" not in st.session_state:
    st.session_state.tickers = ["SOXL"]
if "opportunities" not in st.session_state:
    st.session_state.opportunities = {}

# ==================== SIDEBAR ====================
st.sidebar.subheader("🔑 Polygon.io API Key")
api_key = st.sidebar.text_input("API Key", type="password", value=os.getenv("POLYGON_API_KEY", ""))
if not api_key:
    st.sidebar.warning("Please enter your Polygon.io API key (free tier works).")
    st.stop()

client = RESTClient(api_key=api_key)

# Budget
st.sidebar.subheader("💰 Your Trading Budget")
budget = st.sidebar.number_input("Available Budget ($)", min_value=500, value=5000, step=500)

# ==================== ANALYSIS FUNCTION ====================
def analyze_leap_lag(ticker, dummy_mode=False, dummy_date=None, dummy_time=None):
    try:
        # ==================== STOCK PRICE & MOVE ====================
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

st.caption("LEAPs Lag Hunter • Powered by Polygon.io • Top 5 only • Full reasoning • Budget optimized")            to_date = (target_dt + timedelta(days=2)).date()
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
            
            col1, col2, col3 = st            aggs = list(client.list_aggs(ticker, multiplier=5, timespan="minute",
                                       from_=from_date, to=to_date, limit=50000))
            if not aggs:
                return []
            # Convert to DataFrame for easier handling
            df = pd.DataFrame([{
                'timestamp': pd.to_datetime(a.timestamp, unit='ms'),
                'close': a.close
            } for a in aggs]).set_index('timestamp')
            time_diffs = (df.index - target_dt).map(abs)
            closest_idx = time_diffs.argmin()
            current_price = float(df['close'].iloc[closest_idx])
            later_idx = min(closest_idx + 12, len(df)-1)
            price_later = float(df['close'].iloc[later_idx])
            move_pct = (price_later - current_price) / current_price * 100
        else:
            # Live: last \~2 days of 5m data
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            aggs = list(client.list_aggs(ticker, multiplier=5, timespan="minute",
                                       from_=from_date, to=to_date, limit=50000))
            if len(aggs) < 10:
                return []
            df = pd.DataFrame([{'close': a.close} for a in aggs])
            current_price = float(df['close'].iloc[-1])
            price_ago = float(df['close'].iloc[-13] if len(df) >= 13 else df['close'].iloc[0])
            move_pct = (current_price - price_ago) / price_ago * 100

        # Get long-dated LEAPs contracts
        today = datetime.now().date()
        long_exps = []
        contracts_gen = client.list_options_contracts(
            underlying_ticker=ticker,
            expiration_date_gte=(today + timedelta(days=180)).strftime("%Y-%m-%d"),
            expiration_date_lte=(today + timedelta(days=730)).strftime("%Y-%m-%d"),
            limit=1000
        )
        for contract in contracts_gen:
            if contract.expiration_date not in long_exps:
                long_exps.append(contract.expiration_date)
        long_exps = sorted(set(long_exps))[:15]

        opportunities = []
        
        for exp in long_exps:
            # Get contracts for this expiry (calls only)
            call_contracts = list(client.list_options_contracts(
                underlying_ticker=ticker,
                expiration_date=exp,
                contract_type="call",
                limit=500
            ))
            
            for contract in call_contracts:
                strike = float(contract.strike_price)
                if not (current_price * 0.75 <= strike <= current_price * 1.40):
                    continue
                
                # Get last price via snapshot (fast) or fallback to agg
                try:
                    snapshot = client.get_snapshot_option(ticker=contract.ticker)
                    last_price = float(snapshot.last_quote.ask if hasattr(snapshot, 'last_quote') and snapshot.last_quote else 
                                     (snapshot.day.close if hasattr(snapshot, 'day') else 0))
                except:
                    last_price = 0.0
                
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
                        "reason": f"Stock moved **{move_pct:.1f}%** in the last \~1 hour. Long-dated option is lagging due to lower gamma.",
                        "target_reason": "Buy near current market price expecting quick catch-up as market makers adjust.",
                        "profit_reason": "Momentum-based estimate for fast-moving leveraged ticker."
                    })
        
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

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
import math

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M (Paper)", layout="wide", initial_sidebar_state="expanded")
INITIAL_INVESTMENT_DEFAULT = 81000.0
PREMIUM_TARGET_MONTHLY = 100000.0

# === SESSION STATE ===
if "etfs" not in st.session_state:
    st.session_state.etfs = {
        "TQQQ": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.40},
        "SOXL": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.35},
        "UPRO": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.25}
    }
if "history" not in st.session_state:
    st.session_state.history = []
if "initial_capital" not in st.session_state:
    st.session_state.initial_capital = INITIAL_INVESTMENT_DEFAULT
if "capital_additions" not in st.session_state:
    st.session_state.capital_additions = []
if "option_trades" not in st.session_state:
    st.session_state.option_trades = []  # {"ticker": str, "type": "call"/"put", "strike": float, "expiry": str, "contracts": int, "premium": float, "status": "open"/"expired"/"assigned"}

etfs = st.session_state.etfs
history = st.session_state.history
initial_capital = st.session_state.initial_capital
capital_additions = st.session_state.capital_additions
option_trades = st.session_state.option_trades

# === ALPACA PAPER TRADING ===
if "ALPACA_API_KEY" in st.secrets and "ALPACA_SECRET_KEY" in st.secrets:
    trading_client = TradingClient(st.secrets["ALPACA_API_KEY"], st.secrets["ALPACA_SECRET_KEY"], paper=True)
    data_client = StockHistoricalDataClient(st.secrets["ALPACA_API_KEY"], st.secrets["ALPACA_SECRET_KEY"])
    try:
        account = trading_client.get_account()
        st.sidebar.success(f"Alpaca Paper: ${float(account.cash):,.2f} cash")
    except Exception as e:
        st.sidebar.error(f"Alpaca error: {e}")
        trading_client = None
        data_client = None
else:
    st.sidebar.warning("Add ALPACA keys in Secrets for paper trading")
    trading_client = None
    data_client = None

# === PRICE FETCH ===
@st.cache_data(ttl=300)
def fetch_prices(tickers):
    if trading_client:
        try:
            quotes = data_client.get_latest_quotes(tickers)
            return {q.symbol: round(q.ask_price or q.bid_price, 4) for q in quotes}
        except:
            pass
    # Fallback
    try:
        data = yf.Tickers(" ".join(tickers))
        prices = {}
        for t in tickers:
            price = data.tickers[t].info.get('currentPrice') or data.tickers[t].info.get('regularMarketPrice')
            prices[t] = round(price, 4) if price else 0
        return prices
    except:
        return {t: 0 for t in tickers}

prices = fetch_prices(list(etfs.keys()))

# === CALCULATIONS ===
gross_value = sum(etfs[t]["shares"] * prices.get(t, 0) for t in etfs)
margin = history[-1]["margin_debt"] if history else 0
total_capital_added = initial_capital + sum(a["amount"] for a in capital_additions)
net_equity = gross_value - margin
profit = net_equity - total_capital_added
pct_to_m = max(0, (net_equity / 1000000) * 100)

monthly_premium_est = sum(h.get("premium", 0) for h in history[-4:])

# === DASHBOARD ===
st.title("🚀 Wealth Growth Pro → $1M (Paper Trading)")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")

st.caption(f"Monthly Premium Estimate: ${monthly_premium_est:,.2f} (Target: ${PREMIUM_TARGET_MONTHLY:,.0f})")

# Holdings Table
rows = []
total_val = gross_value or 1
for t in etfs:
    d = etfs[t]
    shares = d["shares"]
    purchase_value = shares * d["cost_basis"]
    current_value = shares * prices.get(t, 0)
    current_pct = current_value / total_val * 100
    target_pct = d.get("target_pct", 0.0) * 100
    contracts_owned = d["contracts_sold"]
    weekly_contracts = d["weekly_contracts"]
    otm = 0.12 if "SOXL" in t else 0.09 if "TQQQ" in t else 0.07
    strike = round(prices.get(t, 0) * (1 + otm), 2)
    rows.append({
        "Ticker": t,
        "Shares": f"{shares:.4f}",
        "Contracts Owned": contracts_owned,
        "Weekly Contracts": weekly_contracts,
        "Purchase Value": f"${purchase_value:,.2f}",
        "Current Value": f"${current_value:,.2f}",
        "Target %": f"{target_pct:.1f}",
        "Current %": f"{current_pct:.2f}",
        "Suggested Call Strike": f"${strike}"
    })

st.subheader("Current Holdings")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# === OPTIONS TRADING & WHEEL SECTION ===
with st.expander("Options Trading & Wheel Strategy (Paper)", expanded=True):
    st.subheader("Sell Weekly Call")
    ticker = st.selectbox("Select Ticker", list(etfs.keys()), key="opt_ticker")
    if ticker:
        current_price = prices.get(ticker, 0)
        if current_price == 0:
            st.error("Price not available")
        else:
            # Next Friday expiry
            today = datetime.now().date()
            days_ahead = 4 - today.weekday()  # Friday is weekday 4
            if days_ahead <= 0:
                days_ahead += 7
            expiry = today + timedelta(days=days_ahead)
            expiry_str = expiry.strftime("%Y-%m-%d")

            # Suggested strike (~20δ OTM)
            otm_pct = 0.12 if "SOXL" in ticker else 0.09 if "TQQQ" in ticker else 0.07
            suggested_strike = round(current_price * (1 + otm_pct), 2)

            st.write(f"Current Price: ${current_price:.4f}")
            st.write(f"Next Friday Expiry: {expiry_str}")
            st.write(f"Suggested Call Strike (~20δ): ${suggested_strike}")

            contracts = st.number_input("Number of Call Contracts to Sell", min_value=1, step=1, value=etfs[ticker]["weekly_contracts"])
            premium_per = st.number_input("Estimated Premium per Contract ($)", min_value=0.0, step=0.1)
            if st.button("Sell Call Contracts"):
                if trading_client:
                    try:
                        # Paper order (market for simplicity)
                        total_premium = contracts * premium_per * 100
                        st.info(f"Simulating sell of {contracts} call contracts @ ${premium_per}/contract = ${total_premium:.2f} premium")
                        # Update tracker
                        etfs[ticker]["weekly_contracts"] = contracts
                        today = datetime.now().strftime("%Y-%m-%d")
                        history.append({"date": today, "premium": total_premium, "option_trade": f"Sold {contracts} {ticker} calls @ {suggested_strike} exp {expiry_str}"})
                        st.success(f"Sold {contracts} calls — ${total_premium:.2f} premium collected")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Order failed: {e}")
                else:
                    st.warning("Alpaca not connected — premium recorded manually")
                    total_premium = contracts * premium_per * 100
                    etfs[ticker]["weekly_contracts"] = contracts
                    today = datetime.now().strftime("%Y-%m-%d")
                    history.append({"date": today, "premium": total_premium})
                    st.success(f"Recorded ${total_premium:.2f} premium (paper mode)")

    st.subheader("Monday Wheel Routine")
    if st.button("Run Monday Routine (Check assignments & next action)"):
        # Simulate assignment check (in paper, we can't detect real assignment, so manual for now)
        st.write("### Current Open Weekly Trades")
        open_trades = [t for t in option_trades if t["status"] == "open"]
        if not open_trades:
            st.info("No open option trades")
        else:
            for trade in open_trades:
                st.write(f"{trade['ticker']} {trade['type']} @ {trade['strike']} exp {trade['expiry']} — {trade['contracts']} contracts")
                # Simulate user input for assignment
                assigned = st.checkbox(f"Was this {trade['type']} assigned?", key=f"assign_{trade['ticker']}")
                if assigned:
                    trade["status"] = "assigned"
                    # Wheel logic
                    if trade["type"] == "call":
                        st.write("Call assigned — stocks called away")
                        # Buy back or sell put
                        st.write("→ Suggest: Sell put at same strike")
                    else:
                        st.write("Put assigned — shares bought")
                        st.write("→ Suggest: Sell call next week")
        st.rerun()

# Growth Chart (same as before)
st.subheader("Growth, Margin & Premium Tracker")
# ... (same chart code as previous version)

# Save button at bottom
if st.button("Save All Data"):
    st.success("Data saved to session")

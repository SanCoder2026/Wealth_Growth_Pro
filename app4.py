import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import os

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M (Auto Wheel)", layout="wide", initial_sidebar_state="expanded")
INITIAL_INVESTMENT_DEFAULT = 81000.0
PREMIUM_TARGET_MONTHLY = 100000.0

# === SESSION STATE INITIALIZATION ===
if "etfs" not in st.session_state:
    st.session_state.etfs = {}
if "history" not in st.session_state:
    st.session_state.history = []
if "initial_capital" not in st.session_state:
    st.session_state.initial_capital = INITIAL_INVESTMENT_DEFAULT
if "capital_additions" not in st.session_state:
    st.session_state.capital_additions = []
if "option_trades" not in st.session_state:
    st.session_state.option_trades = []

etfs = st.session_state.etfs
history = st.session_state.history
initial_capital = st.session_state.initial_capital
capital_additions = st.session_state.capital_additions
option_trades = st.session_state.option_trades

# === ALPACA PAPER TRADING ===
if "ALPACA_API_KEY" in st.secrets and "ALPACA_SECRET_KEY" in st.secrets:
    trading_client = TradingClient(st.secrets["ALPACA_API_KEY"], st.secrets["ALPACA_SECRET_KEY"], paper=True)
    try:
        account = trading_client.get_account()
        st.sidebar.success(f"Alpaca Paper: ${float(account.cash):,.2f} cash available")
    except Exception as e:
        st.sidebar.error(f"Alpaca connection failed: {e}")
        trading_client = None
else:
    st.sidebar.warning("Add ALPACA keys in Secrets for auto trading")
    trading_client = None

# === PRICE FETCH ===
@st.cache_data(ttl=300)
def fetch_prices(tickers):
    if trading_client:
        try:
            quotes = trading_client.get_latest_quotes(tickers)
            return {q.symbol: round(q.ask_price or q.bid_price, 4) for q in quotes}
        except:
            pass
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
st.title("🚀 Wealth Growth Pro → $1M (Auto Wheel Strategy)")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")

st.caption(f"Monthly Premium Estimate: ${monthly_premium_est:,.2f} (Target: ${PREMIUM_TARGET_MONTHLY:,.0f})")

# === HOLDINGS TABLE ===
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

# === AUTO WHEEL STRATEGY SECTION ===
st.subheader("🛞 Auto Wheel Strategy (Paper Mode)")

st.write("**How it works:**")
st.write("- On Monday (or first run), sells weekly OTM calls for Friday expiry")
st.write("- Uses all available cash to buy shares first (fractional allowed)")
st.write("- Sells as many contracts as possible based on shares owned")
st.write("- Reinvests premium immediately")
st.write("- Handles assignments (simulated in paper)")

if st.button("Run Auto Wheel Routine (Paper Mode)"):
    with st.spinner("Running auto wheel routine..."):
        # 1. Get available cash from Alpaca
        if trading_client:
            try:
                account = trading_client.get_account()
                cash = float(account.cash)
            except:
                cash = 0.0
        else:
            cash = 0.0

        # 2. Buy shares with free cash (most under-allocated ticker)
        if cash > 100:  # only if meaningful amount
            deviations = {t: (etfs[t].get("target_pct", 0.0) * total_capital_added) - (etfs[t]["shares"] * prices.get(t, 0)) for t in etfs}
            best = max(deviations, key=deviations.get)
            shares_to_buy = cash / prices.get(best, 1)
            if shares_to_buy > 0:
                if trading_client:
                    try:
                        order_data = MarketOrderRequest(
                            symbol=best,
                            qty=shares_to_buy,
                            side=OrderSide.BUY,
                            time_in_force=TimeInForce.GTC
                        )
                        trading_client.submit_order(order_data)
                        st.success(f"Executed: Bought {shares_to_buy:.4f} {best} with ${cash:,.2f} cash")
                    except Exception as e:
                        st.error(f"Buy failed: {e}")
                # Update local tracker
                old = etfs[best]
                new_shares = old["shares"] + shares_to_buy
                new_basis = (old["shares"] * old["cost_basis"] + shares_to_buy * prices[best]) / new_shares if new_shares > 0 else prices[best]
                etfs[best]["shares"] = new_shares
                etfs[best]["cost_basis"] = new_basis

        # 3. Sell weekly calls on all tickers with shares
        today = datetime.now().date()
        days_ahead = 4 - today.weekday()  # Friday = 4
        if days_ahead <= 0:
            days_ahead += 7
        expiry = today + timedelta(days=days_ahead)

        total_premium = 0
        for t in etfs:
            shares = etfs[t]["shares"]
            if shares >= 100:
                contracts = int(shares // 100)
                current_price = prices.get(t, 0)
                otm_pct = 0.12 if "SOXL" in t else 0.09 if "TQQQ" in t else 0.07
                strike = round(current_price * (1 + otm_pct), 2)
                # Estimate premium (real app would fetch option price)
                estimated_premium_per = current_price * 0.02  # rough 2% weekly
                premium = contracts * estimated_premium_per * 100
                total_premium += premium

                if trading_client:
                    try:
                        # Simulate selling call (Alpaca options not in paper yet, so simulate)
                        st.info(f"Simulated: Sold {contracts} {t} calls @ ${strike} exp {expiry} — est premium ${premium:,.2f}")
                    except:
                        pass

                etfs[t]["weekly_contracts"] = contracts
                history.append({"date": datetime.now().strftime("%Y-%m-%d"), "premium": premium, "option_trade": f"Sold {contracts} {t} calls @ {strike} exp {expiry}"})

        st.success(f"Auto Wheel Routine Complete — Estimated premium collected: ${total_premium:,.2f}")
        st.rerun()

# Growth Chart
st.subheader("Growth, Margin & Premium Tracker")

show_margin = st.checkbox("Show Margin Debt", value=False)
show_premium = st.checkbox("Show Monthly Premium Estimate", value=False)
show_goal = st.checkbox("Show $100k/month Premium Goal", value=True)

if history:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df["net_profit"] = df["portfolio_value"] - df["margin_debt"] - initial_capital
    df["monthly_premium"] = df["premium"].rolling(window=4, min_periods=1).sum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["portfolio_value"], name="Gross Value", line=dict(color="royalblue")))
    fig.add_trace(go.Scatter(x=df["date"], y=df["net_profit"], name="Net Profit", line=dict(color="green", width=3)))
    fig.add_hline(y=initial_capital, line_dash="dash", line_color="red", annotation_text="Initial Capital")

    if show_margin:
        fig.add_trace(go.Scatter(x=df["date"], y=-df["margin_debt"], name="Margin Debt (negative)", line=dict(color="orange", dash="dot")))
    if show_premium:
        fig.add_trace(go.Scatter(x=df["date"], y=df["monthly_premium"], name="Monthly Premium Est.", line=dict(color="purple")))
    if show_goal:
        fig.add_hline(y=PREMIUM_TARGET_MONTHLY, line_dash="dash", line_color="purple", annotation_text="$100k/month Goal")

    for add in capital_additions:
        add_date = pd.to_datetime(add["date"])
        fig.add_vline(x=add_date, line_dash="dot", line_color="green", annotation_text=f"+${add['amount']:,.0f}")

    fig.update_layout(height=600, title="Path to $1M + $100k/month Premium")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Record margin, premium or capital to start tracking")

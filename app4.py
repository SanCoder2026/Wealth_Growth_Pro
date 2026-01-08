import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import os

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M (Paper Trading)", layout="wide", initial_sidebar_state="expanded")
INITIAL_INVESTMENT_DEFAULT = 81000.0
PREMIUM_TARGET_MONTHLY = 100000.0

# === SESSION STATE INITIALIZATION ===
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

etfs = st.session_state.etfs
history = st.session_state.history
initial_capital = st.session_state.initial_capital
capital_additions = st.session_state.capital_additions

# === GLOBAL RESET BUTTON ===
if st.button("🔴 Reset All My Data"):
    if st.button("Confirm Reset — This cannot be undone"):
        st.session_state.etfs = {
            "TQQQ": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.40},
            "SOXL": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.35},
            "UPRO": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.25}
        }
        st.session_state.history = []
        st.session_state.initial_capital = INITIAL_INVESTMENT_DEFAULT
        st.session_state.capital_additions = []
        st.success("All data reset! Refresh the page.")
        st.rerun()

# === ALPACA PAPER TRADING CONNECTION ===
if "ALPACA_API_KEY" in st.secrets and "ALPACA_SECRET_KEY" in st.secrets:
    trading_client = TradingClient(st.secrets["ALPACA_API_KEY"], st.secrets["ALPACA_SECRET_KEY"], paper=True)
    try:
        account = trading_client.get_account()
        st.sidebar.success(f"Connected to Alpaca Paper: ${float(account.cash):,.2f} cash")
    except Exception as e:
        st.sidebar.error(f"Alpaca connection failed: {e}")
        trading_client = None
else:
    st.sidebar.warning("Add ALPACA_API_KEY and ALPACA_SECRET_KEY in Streamlit Secrets for paper trading")
    trading_client = None

# === PRICE FETCH (Alpaca first, fallback to yfinance) ===
@st.cache_data(ttl=300)
def fetch_prices(tickers_list):
    if trading_client:
        try:
            quotes = trading_client.get_latest_quotes(tickers_list)
            prices = {}
            for q in quotes:
                price = q.ask_price or q.bid_price or 0
                prices[q.symbol] = round(price, 4)
            return prices
        except:
            pass
    # Fallback to yfinance
    try:
        data = yf.Tickers(" ".join(tickers_list))
        prices = {}
        for t in tickers_list:
            price = data.tickers[t].info.get('currentPrice') or data.tickers[t].info.get('regularMarketPrice')
            prices[t] = round(price, 4) if price else 0
        return prices
    except:
        return {t: 0 for t in tickers_list}

current_tickers = list(etfs.keys())
prices = fetch_prices(current_tickers)

# === CALCULATIONS ===
gross_value = sum(etfs[t]["shares"] * prices.get(t, 0) for t in current_tickers)
margin = history[-1]["margin_debt"] if history else 0
total_capital_added = initial_capital + sum(add["amount"] for add in capital_additions)
net_equity = gross_value - margin
profit = net_equity - total_capital_added
pct_to_m = max(0, (net_equity / 1000000) * 100)

total_premium_last4 = sum(h.get("premium", 0) for h in history[-4:])
monthly_premium_est = total_premium_last4

# === DASHBOARD ===
st.title("🚀 Wealth Growth Pro → $1M (Alpaca Paper Trading)")

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
        "Suggested Strike (~20δ)": f"${strike}"
    })

st.subheader("Current Holdings")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# === DATA ENTRY SECTION ===
with st.expander("📊 Data Entry (Expand to update – Collapse when done)", expanded=True):
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Weekly Premium & Suggestion")
        premium = st.number_input("Premium Received ($)", min_value=0.0, step=10.0)
        if st.button("Suggest Reinvestment") and premium > 0:
            total_val = gross_value
            deviations = {t: total_val * etfs[t].get("target_pct", 0.0) - (etfs[t]["shares"] * prices.get(t, 0)) for t in etfs}
            best = max(deviations, key=deviations.get)
            shares_buy = premium / prices.get(best, 1)
            st.success(f"Buy **{shares_buy:.4f} {best}** @ ${prices.get(best, 0):.4f} (uses full ${premium:.2f})")

            if trading_client and st.button(f"EXECUTE PAPER TRADE: Buy {shares_buy:.4f} {best}"):
                try:
                    order_data = MarketOrderRequest(
                        symbol=best,
                        qty=shares_buy,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.GTC
                    )
                    trading_client.submit_order(order_data)
                    st.success("Paper trade executed!")
                    # Update holdings
                    old = etfs[best]
                    new_shares = old["shares"] + shares_buy
                    new_basis = (old["shares"] * old["cost_basis"] + shares_buy * prices[best]) / new_shares
                    etfs[best]["shares"] = new_shares
                    etfs[best]["cost_basis"] = new_basis
                    st.rerun()
                except Exception as e:
                    st.error(f"Trade failed: {e}")

        st.subheader("Add Purchase")
        ticker = st.selectbox("Ticker", list(etfs.keys()), key="add_ticker")
        shares = st.number_input("Shares (fractional)", min_value=0.0, step=0.0001, key="add_shares")
        avg_price = st.number_input("Avg Price", min_value=0.0, key="add_price")
        if st.button("Submit Purchase"):
            if shares > 0 and avg_price > 0:
                old = etfs[ticker]
                new_shares = old["shares"] + shares
                new_basis = (old["shares"] * old["cost_basis"] + shares * avg_price) / new_shares
                etfs[ticker]["shares"] = new_shares
                etfs[ticker]["cost_basis"] = new_basis
                today = datetime.now().strftime("%Y-%m-%d")
                history.append({"date": today, "portfolio_value": gross_value, "margin_debt": margin, "premium": premium})
                st.success("Purchase added!")

    with col_right:
        st.subheader("Update Contracts")
        ct_weekly = st.selectbox("Ticker (Weekly)", list(etfs.keys()), key="weekly_ticker")
        weekly = st.number_input("Weekly Contracts", min_value=0, step=1, key="weekly_num")
        if st.button("Update Weekly"):
            etfs[ct_weekly]["weekly_contracts"] = weekly
            st.success("Weekly contracts updated")

        ct_owned = st.selectbox("Ticker (Owned)", list(etfs.keys()), key="owned_ticker")
        owned = st.number_input("Contracts Owned", min_value=0, step=1, key="owned_num")
        if st.button("Update Contracts Owned"):
            etfs[ct_owned]["contracts_sold"] = owned
            st.success("Contracts Owned updated")

        st.subheader("Record Margin Debt")
        margin_input = st.number_input("Current Margin ($)", min_value=0.0, key="margin_input")
        if st.button("Record"):
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "portfolio_value": gross_value, "margin_debt": margin_input, "premium": 0})
            st.success("Margin recorded")

# Growth Chart with Toggles
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
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M", layout="wide", initial_sidebar_state="expanded")
INITIAL_INVESTMENT = 81000.0
TARGET_ALLOC = {"TQQQ": 0.40, "SOXL": 0.35, "UPRO": 0.25}
PREMIUM_TARGET_MONTHLY = 100000.0

# === SUBSCRIPTION PAYWALL (COMMENTED OUT) ===
# from st_paywall import add_auth
# add_auth(required=True)
# if st.session_state.get("user_subscribed", False):
#     st.success(f"Welcome back, {st.session_state.get('email', 'Subscriber')}! Full access unlocked.")
# else:
#     st.info("Subscribe to unlock the full Wealth Growth Pro tracker.")

st.success("Wealth Growth Pro — Full Access")

# === PER-SESSION DATA (NO SHARED FILE) ===
if "etfs" not in st.session_state:
    st.session_state.etfs = {t: {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0} for t in TARGET_ALLOC}
if "history" not in st.session_state:
    st.session_state.history = []

etfs = st.session_state.etfs
history = st.session_state.history

# === GLOBAL RESET BUTTON (CLEARS CURRENT SESSION ONLY) ===
if st.button("🔴 Reset My Session Data"):
    st.session_state.etfs = {t: {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0} for t in TARGET_ALLOC}
    st.session_state.history = []
    st.success("Your session data reset! Refresh to see blank state.")
    st.experimental_rerun()

# === PRICE FETCH ===
@st.cache_data(ttl=300)
def fetch_prices():
    try:
        data = yf.Tickers("TQQQ SOXL UPRO")
        prices = {}
        for t in TARGET_ALLOC:
            price = data.tickers[t].info.get('currentPrice') or data.tickers[t].info.get('regularMarketPrice')
            prices[t] = round(price, 4) if price else 0
        return prices
    except:
        return {t: 0 for t in TARGET_ALLOC}

prices = fetch_prices()

# === CALCULATIONS ===
gross_value = sum(etfs[t]["shares"] * prices.get(t, 0) for t in TARGET_ALLOC)
margin = history[-1]["margin_debt"] if history else 0
net_equity = gross_value - margin
profit = net_equity - INITIAL_INVESTMENT
pct_to_m = max(0, (net_equity / 1000000) * 100)

total_premium_last4 = sum(h.get("premium", 0) for h in history[-4:])
monthly_premium_est = total_premium_last4

# === DASHBOARD ===
st.title("🚀 Wealth Growth Pro → $1M")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Initial Capital", f"${INITIAL_INVESTMENT:,.0f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")

st.caption(f"Monthly Premium Estimate: ${monthly_premium_est:,.2f} (Target: ${PREMIUM_TARGET_MONTHLY:,.0f})")

# Holdings Table
rows = []
total_val = gross_value or 1
for t in TARGET_ALLOC:
    d = etfs[t]
    shares = d["shares"]
    purchase_value = shares * d["cost_basis"]
    current_value = shares * prices[t]
    current_pct = current_value / total_val * 100
    target_pct = TARGET_ALLOC[t] * 100
    contracts_owned = d["contracts_sold"]
    weekly_contracts = d["weekly_contracts"]
    otm = 0.12 if t == "SOXL" else 0.09 if t == "TQQQ" else 0.07
    strike = round(prices[t] * (1 + otm), 2)
    rows.append({
        "Ticker": t,
        "Shares": f"{shares:.4f}",
        "Contracts Owned": contracts_owned,
        "Weekly Contracts": weekly_contracts,
        "Purchase Value": f"${purchase_value:,.2f}",
        "Current Value": f"${current_value:,.2f}",
        "Target %": f"{target_pct:.1f}%",
        "Current %": f"{current_pct:.2f}%",
        "Suggested Strike (~20δ)": f"${strike}"
    })

st.subheader("Current Holdings")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# === DATA ENTRY SECTION (COLLAPSIBLE) ===
with st.expander("📊 Data Entry (Expand to update – Collapse when done)", expanded=True):
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Weekly Premium & Suggestion")
        premium = st.number_input("Premium Received ($)", min_value=0.0, step=10.0)
        if st.button("Suggest Reinvestment") and premium > 0:
            total_val = gross_value
            deviations = {t: total_val * TARGET_ALLOC[t] - (etfs[t]["shares"] * prices[t]) for t in TARGET_ALLOC}
            best = max(deviations, key=deviations.get)
            shares_buy = premium / prices[best]
            st.success(f"Buy **{shares_buy:.4f} {best}** @ ${prices[best]:.4f} (uses full ${premium:.2f})")

        st.subheader("Add Purchase")
        ticker = st.selectbox("Ticker", list(TARGET_ALLOC.keys()), key="add_ticker")
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
        ct_weekly = st.selectbox("Ticker (Weekly)", list(TARGET_ALLOC.keys()), key="weekly_ticker")
        weekly = st.number_input("Weekly Contracts", min_value=0, step=1, key="weekly_num")
        if st.button("Update Weekly"):
            etfs[ct_weekly]["weekly_contracts"] = weekly
            st.success("Weekly contracts updated")

        ct_owned = st.selectbox("Ticker (Owned)", list(TARGET_ALLOC.keys()), key="owned_ticker")
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

# Growth Chart
st.subheader("Growth, Margin & Premium Tracker")
if history:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df["net_profit"] = df["portfolio_value"] - df["margin_debt"] - INITIAL_INVESTMENT
    df["monthly_premium"] = df["premium"].rolling(window=4, min_periods=1).sum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["portfolio_value"], name="Gross Value", line=dict(color="royalblue")))
    fig.add_trace(go.Scatter(x=df["date"], y=df["net_profit"], name="Net Profit", line=dict(color="green", width=3)))
    fig.add_trace(go.Scatter(x=df["date"], y=-df["margin_debt"], name="Margin Debt (negative)", line=dict(color="orange", dash="dot")))
    fig.add_trace(go.Scatter(x=df["date"], y=df["monthly_premium"], name="Monthly Premium Est.", line=dict(color="purple")))
    fig.add_hline(y=PREMIUM_TARGET_MONTHLY, line_dash="dash", line_color="purple", annotation_text="$100k/month Goal")
    fig.add_hline(y=INITIAL_INVESTMENT, line_dash="dash", line_color="red", annotation_text="Initial $81k")
    fig.update_layout(height=600, title="Path to $1M + $100k/month Premium")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Record margin or premium to start tracking growth")

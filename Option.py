import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime, timedelta
import glob
import shutil
import yfinance as yf

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M", layout="wide", initial_sidebar_state="expanded")
PREMIUM_TARGET_MONTHLY = 100000.0

st.markdown(
    """
    <h1 style='text-align: center; color: #1E90FF; font-family: "Arial Black", sans-serif; 
    font-size: 3.5rem; font-weight: bold; letter-spacing: 4px; margin: 20px 0 10px 0;'>
        Wealth Growth Pro
    </h1>
    <p style='text-align: center; color: #444; font-size: 1.4rem; margin-top: -15px; margin-bottom: 30px;'>
        → Building Toward $1 Million with Discipline & Strategy (JSON + Backup)
    </p>
    <hr style='border-top: 3px solid #1E90FF;'>
    """,
    unsafe_allow_html=True
)

TARGET_ALLOCATIONS = {
    "SOXL": 0.30, "SLV": 0.25, "TQQQ": 0.16, "URA": 0.10,
    "IAU": 0.06, "COPX": 0.06, "UPRO": 0.06, "UAMY": 0.01,
}

# === USERNAME ===
if "username" not in st.session_state:
    st.session_state.username = "Investor"

username = st.text_input("👤 User Name", value=st.session_state.username, key="username_input")
if username != st.session_state.username:
    st.session_state.username = username

DATA_DIR = f"data/{username}/"
LATEST_FILE = f"{DATA_DIR}{username}_latest.json"
HISTORY_DIR = f"{DATA_DIR}{username}_history/"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# === LOAD / SAVE ===
def save_version(data):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    version_file = f"{HISTORY_DIR}{timestamp}.json"
    with open(version_file, "w") as f:
        json.dump(data, f, indent=2)
    with open(LATEST_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_latest():
    if os.path.exists(LATEST_FILE):
        try:
            with open(LATEST_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    # Default data
    default_etfs = {ticker: {"shares": 0.0, "cost_basis": 0.0, "target_pct": pct, "contracts_sold": 0, "weekly_contracts": 0}
                    for ticker, pct in TARGET_ALLOCATIONS.items()}
    return {
        "etfs": default_etfs,
        "history": [],
        "initial_capital": 0.0,
        "capital_additions": [],
        "option_trades": [],
        "cash_balance": 0.0
    }

data = load_latest()
etfs = data.get("etfs", {})
history = data.get("history", [])
initial_capital = float(data.get("initial_capital", 0.0))
capital_additions = data.get("capital_additions", [])
option_trades = data.get("option_trades", [])
cash_balance = float(data.get("cash_balance", 0.0))
margin = 0.0

# === PRICE FETCH ===
@st.cache_data(ttl=300)
def fetch_prices(tickers):
    try:
        data_ = yf.Tickers(" ".join(tickers))
        return {t: round(data_.tickers[t].info.get('currentPrice') or data_.tickers[t].info.get('regularMarketPrice', 0), 4)
                for t in tickers}
    except:
        return {t: 0 for t in tickers}

prices = fetch_prices(list(etfs.keys()))

# === CALCULATIONS ===
gross_value = sum(etfs.get(t, {}).get("shares", 0) * prices.get(t, 0) for t in etfs)
total_capital_added = initial_capital + sum(a.get("amount", 0) for a in capital_additions)
net_equity = gross_value - margin + cash_balance
profit = net_equity - total_capital_added
pct_to_m = (net_equity / 1_000_000) * 100 if net_equity > 0 else 0

st.success(f"Welcome back, **{username}**!")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Margin Debt", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.1f}%")

st.caption(f"**Cash**: ${cash_balance:,.2f} | Recent Premium: ${sum(h.get('premium', 0) for h in history[-4:]):,.0f}")

# === CAPITAL, MARGIN & CASH ===
with st.expander("💰 Capital, Margin & Cash Management", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Add Capital")
        amt = st.number_input("Amount ($)", min_value=0.0, step=1000.0, key="add_amt")
        if st.button("Add Capital") and amt > 0:
            date_str = datetime.now().strftime("%Y-%m-%d")
            cash_balance += amt
            capital_additions.append({"date": date_str, "amount": float(amt)})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success(f"Added ${amt:,.2f}")
            st.rerun()

    with c2:
        st.subheader("Margin Debt")
        new_margin = st.number_input("Margin ($)", value=float(margin), step=100.0)
        if st.button("Update Margin"):
            margin = new_margin
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success("Margin updated")
            st.rerun()

    with c3:
        st.subheader("💵 Cash Balance")
        new_cash = st.number_input("Cash ($)", value=float(cash_balance), step=100.0)
        if st.button("Update Cash"):
            cash_balance = new_cash
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success(f"Cash set to ${cash_balance:,.2f}")
            st.rerun()

# === OPEN OPTIONS TABLE ===
st.subheader("🛡️ Open Options Positions")
open_opts = [t for t in option_trades if t.get("status") == "open"]

if open_opts:
    rows = []
    today = datetime.now().date()
    for t in open_opts:
        try:
            expiry_dt = datetime.strptime(t.get("expiry", ""), "%Y-%m-%d").date()
            dte = max(0, (expiry_dt - today).days)
        except:
            dte = 0
        price = prices.get(t.get("ticker"), 0)
        otm_pct = 0.12 if "SOXL" in t.get("ticker", "") else 0.09 if "TQQQ" in t.get("ticker", "") else 0.07
        sugg_roll = round(price * (1 + otm_pct), 2) if price > 0 else 0
        rows.append({
            "Ticker": t.get("ticker", ""),
            "Contracts": int(t.get("contracts", 0)),
            "Strike": f"${float(t.get('strike', 0)):.2f}",
            "Expiry": t.get("expiry", ""),
            "DTE": dte,
            "Moneyness": "ITM" if price > float(t.get("strike", 0)) else "OTM",
            "Suggested Roll Strike": f"${sugg_roll:.2f}"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No open option positions yet.")

# === GROWTH TRACKER + MONTHLY PREMIUM ===
st.subheader("Growth Tracker")
if history:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df = df.dropna(subset=["date"])
    df["cum_premium"] = pd.to_numeric(df.get("premium", 0), errors='coerce').fillna(0).cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df.get("portfolio_value", 0), name="Gross Value", line=dict(color="#1E90FF")))
    fig.add_trace(go.Scatter(x=df["date"], y=df["cum_premium"], name="Cumulative Premium P&L", line=dict(color="orange", dash="dot")))
    fig.add_hline(y=1000000, line_dash="dash", annotation_text="$1M Target")
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("📅 Monthly Premium Income")
if history:
    dfh = pd.DataFrame(history)
    dfh["date"] = pd.to_datetime(dfh.get("date"), errors="coerce")
    dfh["month"] = dfh["date"].dt.strftime("%Y-%m")
    monthly = dfh.groupby("month")["premium"].sum().reset_index()
    fig_bar = go.Figure(go.Bar(x=monthly["month"], y=monthly["premium"], marker_color="#1E90FF"))
    fig_bar.update_layout(height=400, xaxis_title="Month", yaxis_title="Premium ($)")
    st.plotly_chart(fig_bar, use_container_width=True)

# === BACKUP SECTION ===
with st.expander("💾 Backup & Restore"):
    col_dl, col_ul = st.columns(2)
    with col_dl:
        if st.button("⬇️ Download Full Backup"):
            backup = {
                "etfs": etfs,
                "history": history,
                "initial_capital": initial_capital,
                "capital_additions": capital_additions,
                "option_trades": option_trades,
                "cash_balance": cash_balance,
                "timestamp": datetime.now().isoformat(),
                "username": username
            }
            json_str = json.dumps(backup, indent=2)
            st.download_button(
                label="Download wealthgrowth_backup.json",
                data=json_str,
                file_name=f"wealthgrowth_{username}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json"
            )
    with col_ul:
        uploaded = st.file_uploader("Upload backup JSON", type=["json"])
        if uploaded:
            try:
                backup_data = json.load(uploaded)
                if st.button("Restore from this file"):
                    with open(LATEST_FILE, "w") as f:
                        json.dump(backup_data, f, indent=2)
                    st.success("Backup restored! Refreshing...")
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")

st.caption("Data saved locally as JSON. Use Download/Upload for phone ↔ desktop sync.")

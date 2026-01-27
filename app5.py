import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime, timedelta
import glob
import shutil

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M (v5)", layout="wide", initial_sidebar_state="expanded")
INITIAL_INVESTMENT_DEFAULT = 81000.0
PREMIUM_TARGET_MONTHLY = 100000.0

# === USERNAME SECTION ===
st.markdown("### 👤 User Name Entry")
col_user1, col_user2 = st.columns([3, 1])
with col_user1:
    username_input = st.text_input("User Name :", value="", placeholder="Enter your username", key="username_input", label_visibility="collapsed")
with col_user2:
    apply_btn = st.button("APPLY", type="primary", use_container_width=True)

if apply_btn:
    if not username_input.strip():
        st.error("Username cannot be empty!")
    else:
        st.session_state.username = username_input.strip()
        st.success(f"Username set: **{st.session_state.username}**")
        st.rerun()

if "username" not in st.session_state or not st.session_state.username:
    st.info("👆 Please enter a username and click **APPLY** to begin.")
    st.stop()

username = st.session_state.username
DATA_DIR = f"data/{username}/"
LATEST_FILE = f"{DATA_DIR}{username}_latest.json"
HISTORY_DIR = f"{DATA_DIR}{username}_history/"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# === LOAD / SAVE / VERSIONING ===
def save_version(data, is_session_start=False):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    version_file = f"{HISTORY_DIR}{timestamp}.json"
    with open(version_file, "w") as f:
        json.dump(data, f, indent=2)
    
    # Always update latest
    with open(LATEST_FILE, "w") as f:
        json.dump(data, f, indent=2)
    
    if is_session_start:
        st.session_state.last_session_start = timestamp

def load_latest():
    if os.path.exists(LATEST_FILE):
        try:
            with open(LATEST_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "etfs": {
            "TQQQ": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.40},
            "SOXL": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.35},
            "UPRO": {"shares": 0.0, "cost_basis": 0.0, "contracts_sold": 0, "weekly_contracts": 0, "target_pct": 0.25}
        },
        "history": [],
        "initial_capital": INITIAL_INVESTMENT_DEFAULT,
        "capital_additions": [],
        "option_trades": []   # added from app3
    }

def load_version(filename):
    path = f"{HISTORY_DIR}{filename}"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None

# Load current state
data = load_latest()
etfs = data.get("etfs", {})
history = data.get("history", [])
initial_capital = data.get("initial_capital", INITIAL_INVESTMENT_DEFAULT)
capital_additions = data.get("capital_additions", [])
option_trades = data.get("option_trades", [])

# Auto-save session start snapshot if new session
if "session_snapshotted" not in st.session_state:
    save_version(data, is_session_start=True)
    st.session_state.session_snapshotted = True

# === RESET ===
if st.button(f"🔴 Reset ALL {username}'s Data"):
    if st.button("Confirm — deletes everything permanently"):
        if os.path.exists(DATA_DIR):
            shutil.rmtree(DATA_DIR)
        st.success("All data deleted. Refresh page.")
        st.rerun()

# === HISTORY & RESTORE ===
with st.expander(f"🕒 Session History & Restore ({username})", expanded=False):
    versions = sorted(glob.glob(f"{HISTORY_DIR}*.json"), reverse=True)
    if versions:
        st.write(f"Found {len(versions)} saved versions")
        selected_file = st.selectbox(
            "Select version to preview / restore",
            [os.path.basename(f) for f in versions[:15]],
            format_func=lambda x: x.replace("_", " ").replace(".json", "")
        )
        if st.button("Load & Replace Current State"):
            old_data = load_version(selected_file)
            if old_data:
                with open(LATEST_FILE, "w") as f:
                    json.dump(old_data, f, indent=2)
                st.success(f"Restored version: {selected_file}")
                st.rerun()
    else:
        st.info("No history versions yet — will appear after changes")

# === PRICE FETCH ===
@st.cache_data(ttl=300)
def fetch_prices(tickers_list):
    try:
        data = yf.Tickers(" ".join(tickers_list))
        return {t: round(data.tickers[t].info.get('currentPrice') or data.tickers[t].info.get('regularMarketPrice', 0), 4)
                for t in tickers_list}
    except:
        return {t: 0 for t in tickers_list}

prices = fetch_prices(list(etfs.keys()))

# === CALCULATIONS ===
gross_value = sum(etfs[t]["shares"] * prices.get(t, 0) for t in etfs)
margin = history[-1].get("margin_debt", 0) if history else 0
total_capital_added = initial_capital + sum(a["amount"] for a in capital_additions)
net_equity = gross_value - margin
profit = net_equity - total_capital_added
pct_to_m = max(0, (net_equity / 1000000) * 100)
monthly_premium_est = sum(h.get("premium", 0) for h in history[-4:])

# === DASHBOARD ===
st.success(f"Welcome back, {username}!")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")

st.caption(f"Monthly Premium Estimate: ${monthly_premium_est:,.2f} (Target: ${PREMIUM_TARGET_MONTHLY:,.0f})")

# === CAPITAL MANAGEMENT ===
with st.expander("💰 Capital & Margin", expanded=False):
    col_cap1, col_cap2 = st.columns(2)
    with col_cap1:
        st.subheader("Add Capital")
        add_amount = st.number_input("Amount ($)", min_value=0.0, step=1000.0, key="add_amt")
        add_date = st.date_input("Date", value=datetime.now().date(), key="add_date")
        if st.button("Add Capital") and add_amount > 0:
            capital_additions.append({"date": add_date.strftime("%Y-%m-%d"), "amount": add_amount})
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "portfolio_value": gross_value, "margin_debt": margin, "premium": 0})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades})
            st.success(f"Added ${add_amount:,.2f}")
            st.rerun()

    with col_cap2:
        st.subheader("Update Margin Debt")
        margin_input = st.number_input("Current Margin ($)", min_value=0.0, value=margin, key="margin_upd")
        if st.button("Record Margin") and margin_input != margin:
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "portfolio_value": gross_value, "margin_debt": margin_input, "premium": 0})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades})
            st.success("Margin updated")
            st.rerun()

# === TICKERS & ALLOCATIONS (from app2) ===
with st.expander("📈 Manage Tickers & Targets", expanded=False):
    # Add new ticker ...
    st.subheader("Add Ticker")
    new_ticker = st.text_input("Ticker (e.g. NVDA)", "").strip().upper()
    if st.button("Add") and new_ticker and new_ticker not in etfs:
        suggested_pct = 0.10  # simplified — can expand volatility logic
        etfs[new_ticker] = {"shares":0.0, "cost_basis":0.0, "contracts_sold":0, "weekly_contracts":0, "target_pct":suggested_pct}
        save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                      "capital_additions": capital_additions, "option_trades": option_trades})
        st.success(f"{new_ticker} added")
        st.rerun()

    # Edit targets ...
    st.subheader("Target Allocations")
    new_targets = {}
    for t in list(etfs):
        col_t1, col_t2 = st.columns([3,1])
        col_t1.write(t)
        pct = st.number_input(f"% {t}", 0.0, 100.0, etfs[t]["target_pct"]*100, 0.1, key=f"tgt_{t}") / 100
        new_targets[t] = pct

    if st.button("Save & Normalize"):
        total = sum(new_targets.values())
        if total > 0:
            for t in new_targets:
                etfs[t]["target_pct"] = new_targets[t] / total
        save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                      "capital_additions": capital_additions, "option_trades": option_trades})
        st.success("Targets updated & normalized")
        st.rerun()

# === HOLDINGS TABLE ===
rows = []
total_val = gross_value or 1
for t in etfs:
    d = etfs[t]
    val = d["shares"] * prices.get(t, 0)
    rows.append({
        "Ticker": t,
        "Shares": f"{d['shares']:.4f}",
        "Contracts Owned": d["contracts_sold"],
        "Weekly Contracts": d["weekly_contracts"],
        "Current Value": f"${val:,.2f}",
        "Current %": f"{val/total_val*100:.2f}",
        "Target %": f"{d['target_pct']*100:.1f}",
    })
st.subheader("Holdings")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# === OPTIONS / WHEEL SECTION (from app3) ===
with st.expander("🛞 Options Trading & Weekly Wheel (Paper)", expanded=True):
    st.subheader("Sell Weekly Call")
    ticker = st.selectbox("Ticker", list(etfs.keys()), key="opt_tkr")
    if ticker and prices.get(ticker, 0) > 0:
        current_price = prices[ticker]
        today = datetime.now().date()
        days_ahead = (4 - today.weekday()) % 7 or 7
        expiry = today + timedelta(days=days_ahead)
        expiry_str = expiry.strftime("%Y-%m-%d")

        otm_pct = 0.12 if "SOXL" in ticker else 0.09 if "TQQQ" in ticker else 0.07
        strike = round(current_price * (1 + otm_pct), 2)

        st.write(f"Price: **${current_price:.2f}**   |   Next Friday: **{expiry_str}**")
        st.write(f"Suggested OTM Call Strike: **${strike}**")

        contracts = st.number_input("Contracts to Sell", min_value=1, step=1, value=etfs[ticker]["weekly_contracts"])
        premium_per = st.number_input("Premium per contract ($)", min_value=0.0, step=0.05)
        if st.button("Sell Calls"):
            total_prem = contracts * premium_per * 100
            etfs[ticker]["weekly_contracts"] = contracts
            today_str = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today_str, "premium": total_prem, "note": f"Sold {contracts} {ticker} calls"})
            
            # Optional: record open trade
            option_trades.append({
                "ticker": ticker, "type": "call", "strike": strike, "expiry": expiry_str,
                "contracts": contracts, "premium": premium_per, "status": "open"
            })
            
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades})
            st.success(f"Recorded ${total_prem:,.2f} premium")
            st.rerun()

    st.subheader("Monday Wheel Check")
    if st.button("Run Assignment Check"):
        open_trades = [t for t in option_trades if t["status"] == "open"]
        if not open_trades:
            st.info("No open trades")
        for trade in open_trades:
            st.write(f"{trade['ticker']} {trade['type']} @{trade['strike']} exp {trade['expiry']} — {trade['contracts']} ct")
            key = f"assign_{trade['ticker']}_{trade['expiry']}"
            if st.checkbox("Was assigned?", key=key):
                trade["status"] = "assigned"
                st.write("→ Next: consider selling put / call depending on direction")
        if st.button("Save Assignment Updates"):
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades})
            st.success("Assignments updated")
            st.rerun()

# === DATA ENTRY (Purchases, Premiums, etc.) ===
with st.expander("📊 Manual Updates", expanded=False):
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Record Premium / Reinvest")
        premium = st.number_input("Premium Received ($)", 0.0, step=10.0)
        if st.button("Record Premium") and premium > 0:
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "premium": premium, "portfolio_value": gross_value, "margin_debt": margin})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades})
            st.success("Premium recorded")

        # Add purchase ...
        st.subheader("Add Purchase")
        tk = st.selectbox("Ticker", list(etfs), key="buy_tk")
        sh = st.number_input("Shares", 0.0001, step=0.0001)
        pr = st.number_input("Avg Price", 0.01, step=0.01)
        if st.button("Submit Buy"):
            if sh > 0 and pr > 0:
                old = etfs[tk]
                new_s = old["shares"] + sh
                new_b = (old["shares"] * old["cost_basis"] + sh * pr) / new_s if new_s > 0 else pr
                etfs[tk]["shares"] = new_s
                etfs[tk]["cost_basis"] = new_b
                history.append({"date": datetime.now().strftime("%Y-%m-%d"), "portfolio_value": gross_value,
                                "margin_debt": margin, "premium": 0})
                save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                              "capital_additions": capital_additions, "option_trades": option_trades})
                st.success("Purchase added")

    with col_r:
        st.subheader("Contracts")
        ct_tk = st.selectbox("Ticker", list(etfs), key="ct_tk")
        weekly = st.number_input("Weekly Sold", 0, step=1)
        owned = st.number_input("Total Owned", 0, step=1)
        if st.button("Update Contracts"):
            etfs[ct_tk]["weekly_contracts"] = weekly
            etfs[ct_tk]["contracts_sold"] = owned
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades})
            st.success("Contracts updated")

# === CHART ===
st.subheader("Growth Tracker")
show_margin = st.checkbox("Show Margin", False)
show_prem = st.checkbox("Show Monthly Premium", False)

if history:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df["net"] = df["portfolio_value"] - df.get("margin_debt", 0) - initial_capital
    df["monthly_prem"] = df["premium"].rolling(4, min_periods=1).sum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["portfolio_value"], name="Gross"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["net"], name="Net Profit", line=dict(color="green")))
    if show_margin and "margin_debt" in df:
        fig.add_trace(go.Scatter(x=df["date"], y=-df["margin_debt"], name="Margin Debt", line=dict(color="orange", dash="dot")))
    if show_prem:
        fig.add_trace(go.Scatter(x=df["date"], y=df["monthly_prem"], name="Monthly Premium", line=dict(color="purple")))
    fig.add_hline(y=1000000, line_dash="dash", annotation_text="$1M")

    fig.update_layout(height=550)
    st.plotly_chart(fig, use_container_width=True)

st.caption("Made with ❤️ — v5 with versioning & wheel section")
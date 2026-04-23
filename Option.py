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
st.set_page_config(page_title="Wealth Growth Pro → $1M", layout="wide", initial_sidebar_state="expanded")
PREMIUM_TARGET_MONTHLY = 100000.0

st.markdown(
    """
    <h1 style='text-align: center; color: #1E90FF; font-family: "Arial Black", Gadget, sans-serif; 
    font-size: 3.5rem; font-weight: bold; letter-spacing: 4px; 
    margin: 20px 0 10px 0; text-shadow: 3px 3px 10px rgba(0,0,0,0.4);'>
        Wealth Growth Pro
    </h1>
    <p style='text-align: center; color: #444; font-size: 1.4rem; margin-top: -15px; margin-bottom: 30px;'>
        → Building Toward $1 Million with Discipline & Strategy
    </p>
    <hr style='border-top: 3px solid #1E90FF; margin: 0 0 30px 0;'>
    """,
    unsafe_allow_html=True
)

TARGET_ALLOCATIONS = {
    "SOXL": 0.30, "SLV": 0.25, "TQQQ": 0.16, "URA": 0.10,
    "IAU": 0.06, "COPX": 0.06, "UPRO": 0.06, "UAMY": 0.01,
    "IBIT": 0.05,
}

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

# === LOAD / SAVE ===
def save_version(data, is_session_start=False):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    version_file = f"{HISTORY_DIR}{timestamp}.json"
    with open(version_file, "w") as f:
        json.dump(data, f, indent=2)
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
    default_etfs = {ticker: {"shares": 0.0, "cost_basis": 0.0, "target_pct": pct} for ticker, pct in TARGET_ALLOCATIONS.items()}
    return {
        "etfs": default_etfs,
        "history": [],
        "initial_capital": 0.0,
        "capital_additions": [],
        "option_trades": [],
        "cash_balance": 0.0
    }

def load_version(filename):
    path = f"{HISTORY_DIR}{filename}"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None

data = load_latest()
etfs = data.get("etfs", {})
history = data.get("history", [])
initial_capital = float(data.get("initial_capital", 0.0))
capital_additions = data.get("capital_additions", [])
option_trades = data.get("option_trades", [])
cash_balance = float(data.get("cash_balance", 0.0))

margin = 0.0
if history:
    last_margin = history[-1].get("margin_debt")
    if last_margin is not None:
        try:
            margin = float(last_margin)
        except:
            margin = 0.0

if "session_snapshotted" not in st.session_state:
    save_version(data, is_session_start=True)
    st.session_state.session_snapshotted = True

# === HISTORY & RESTORE (kept unchanged) ===
with st.expander(f"🕒 Session History & Restore ({username})", expanded=False):
    versions = sorted(glob.glob(f"{HISTORY_DIR}*.json"), reverse=True)
    if versions:
        st.write(f"Found {len(versions)} saved versions (showing last 30)")
        display_options = []
        for f in versions[:30]:
            basename = os.path.basename(f)
            dt_str = basename.replace(".json", "").replace("_", " ")
            try:
                data_temp = load_version(basename)
                last_entry = data_temp["history"][-1] if data_temp["history"] else {}
                note = last_entry.get("note", "")
                if note:
                    dt_str += f" – {note[:40]}..."
            except:
                pass
            display_options.append((basename, dt_str))
        
        selected_display = st.selectbox(
            "Select version to preview / restore",
            options=display_options,
            format_func=lambda x: x[1],
            index=0
        )
        
        selected_file = selected_display[0] if selected_display else None
        
        if st.button("Load & Replace Current State") and selected_file:
            old_data = load_version(selected_file)
            if old_data:
                with open(LATEST_FILE, "w") as f:
                    json.dump(old_data, f, indent=2)
                st.success(f"Restored version from {selected_display[1]}")
                st.rerun()
    else:
        st.info("No saved history yet — will appear after changes")

    st.markdown("---")
    st.markdown("### 💾 Manual Backup & Restore")

    col_dl, col_ul = st.columns(2)
    with col_dl:
        if st.button("⬇️ Download Full Backup Now"):
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
        uploaded = st.file_uploader("Choose backup JSON file", type=["json"])
        if uploaded:
            try:
                backup_data = json.load(uploaded)
                if st.button("Restore from this file", type="primary"):
                    with open(LATEST_FILE, "w") as f:
                        json.dump(backup_data, f, indent=2)
                    st.success("Backup restored!")
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Reset button
if st.button(f"🔴 Reset ALL {username}'s Data", type="secondary"):
    if st.button("Confirm — this deletes everything permanently"):
        if os.path.exists(DATA_DIR):
            shutil.rmtree(DATA_DIR)
        st.session_state.clear()
        st.success("All data reset. Refreshing...")
        st.rerun()

# === INITIAL CAPITAL SETUP ===
if initial_capital <= 0:
    st.warning("Initial capital has not been set yet.")
    with st.form(key="set_initial_capital_form"):
        st.subheader("Set Your Starting Capital")
        initial_input = st.number_input("Initial Investment Amount ($)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")
        if st.form_submit_button("Confirm & Start") and initial_input > 0:
            initial_capital = float(initial_input)
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "portfolio_value": 0.0, "margin_debt": 0.0, "premium": 0, "note": "Initial capital set"})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success(f"Initial capital set to **${initial_capital:,.2f}**")
            st.rerun()
else:
    st.info(f"Initial capital: **${initial_capital:,.2f}**")

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

# === PORTFOLIO CALCULATIONS ===
gross_value = sum(float(etfs[t].get("shares", 0)) * prices.get(t, 0) for t in etfs)
total_capital_added = initial_capital + sum(a.get("amount", 0) for a in capital_additions)
net_equity = gross_value - margin + cash_balance
profit = net_equity - total_capital_added
pct_to_m = max(0, (net_equity / 1000000) * 100) if net_equity > 0 else 0
monthly_premium_est = sum(h.get("premium", 0) for h in history[-4:]) if history else 0

# === DASHBOARD ===
st.success(f"Welcome back, {username}!")
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")
col6.metric("Profit / Loss", f"${profit:,.2f}", delta=f"${profit:,.2f}", delta_color="normal" if profit >= 0 else "inverse")
col7.metric("Avg Monthly Premium", f"${avg_monthly_premium:,.0f}" if 'avg_monthly_premium' in locals() else "$0", delta=f"{(avg_monthly_premium / PREMIUM_TARGET_MONTHLY * 100):.1f}% of goal" if 'avg_monthly_premium' in locals() else "")

st.caption(f"**Cash**: ${cash_balance:,.2f} | Recent Premium Est: ${monthly_premium_est:,.0f}")

# === CAPITAL & MARGIN ===
with st.expander("💰 Capital & Margin"):
    col1, col2, col3 = st.columns(3)
    with col1: st.subheader("Add Capital")
    # ... (your existing Add Capital code) ...
    with col2: st.subheader("Margin Debt")
    # ... (your existing Margin code) ...
    with col3: st.subheader("💵 Cash Balance")
    # ... (your existing Cash code) ...

# === MANAGE TICKERS & ADD NEW ===
# ... (your existing Manage Tickers code) ...

# === NEW: MANAGE OPEN OPTIONS (Multiple options per ticker) ===
with st.expander("📊 Manage Open Options", expanded=False):
    st.subheader("Add New Option")
    col1, col2 = st.columns(2)
    with col1:
        new_ticker = st.selectbox("Ticker", list(etfs.keys()), key="new_opt_ticker")
    with col2:
        new_type = st.selectbox("Type", ["call", "put"], key="new_opt_type")
    col3, col4 = st.columns(2)
    with col3:
        new_strike = st.number_input("Strike Price", min_value=0.0, step=0.01, key="new_opt_strike")
        new_contracts = st.number_input("Contracts", min_value=1, step=1, key="new_opt_contracts")
    with col4:
        new_premium = st.number_input("Premium per contract ($)", min_value=0.0, step=0.05, key="new_opt_premium")
        new_expiry = st.date_input("Expiry Date", value=datetime.now().date() + timedelta(days=7), key="new_opt_expiry")
    new_sold_date = st.date_input("Sold Date", value=datetime.now().date(), key="new_opt_sold_date")

    if st.button("Add New Option"):
        option_trades.append({
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "ticker": new_ticker,
            "type": new_type,
            "strike": float(new_strike),
            "expiry": new_expiry.strftime("%Y-%m-%d"),
            "contracts": int(new_contracts),
            "premium_per": float(new_premium),
            "sold_date": new_sold_date.strftime("%Y-%m-%d"),
            "status": "open"
        })
        save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                      "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
        st.success(f"Added new {new_type} option for {new_ticker}")
        st.rerun()

    st.subheader("Existing Open Options")
    for i, opt in enumerate(option_trades):
        if opt.get("status") != "open":
            continue
        with st.expander(f"{opt['ticker']} {opt['type'].upper()} @ ${opt['strike']:.2f} exp {opt['expiry']} — {opt['contracts']} contracts"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                new_contracts = st.number_input("Contracts", value=opt["contracts"], key=f"edit_c_{i}")
            with col_b:
                new_premium = st.number_input("Premium per contract", value=opt["premium_per"], key=f"edit_p_{i}")
            with col_c:
                if st.button("Save Edit", key=f"save_{i}"):
                    option_trades[i]["contracts"] = new_contracts
                    option_trades[i]["premium_per"] = new_premium
                    save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                                  "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
                    st.success("Option updated")
                    st.rerun()
            if st.button("Close Full Position", key=f"close_{i}"):
                option_trades[i]["status"] = "closed"
                save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                              "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
                st.success("Position closed")
                st.rerun()

# === CURRENT HOLDINGS TABLE ===
st.subheader("Current Holdings")
# ... (your existing Current Holdings table code remains unchanged) ...

# === OPEN OPTIONS POSITIONS TABLE ===
st.subheader("🛡️ Open Options Positions")

if option_trades:
    opt_rows = []
    today = datetime.now().date()
    for trade in option_trades:
        if trade.get("status") != "open":
            continue
        try:
            expiry_dt = datetime.strptime(trade["expiry"], "%Y-%m-%d").date()
            days_left = max(0, (expiry_dt - today).days)
        except:
            days_left = 0
        current_price = prices.get(trade.get("ticker", ""), 0)
        itm_otm = "ITM" if current_price > trade.get("strike", 0) else "OTM" if current_price < trade.get("strike", 0) else "ATM"
        
        # Per-option suggested roll (higher premium, safer OTM)
        otm_pct = 0.12 if "SOXL" in trade.get("ticker", "") else 0.09 if "TQQQ" in trade.get("ticker", "") else 0.07
        suggested_roll_strike = round(current_price * (1 + otm_pct), 2) if current_price > 0 else "-"
        suggested_roll_expiry = (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d")
        
        opt_rows.append({
            "Ticker": trade.get("ticker", ""),
            "Type": trade.get("type", "").upper(),
            "Strike": f"${trade.get('strike', 0):.2f}",
            "Expiry": trade.get("expiry", ""),
            "DTE": days_left,
            "Moneyness": itm_otm,
            "Contracts": trade.get("contracts", 0),
            "Premium per Contract": f"${trade.get('premium_per', 0):.2f}",
            "Suggested Roll Strike": f"${suggested_roll_strike}",
            "Suggested Roll Expiry": suggested_roll_expiry
        })
    
    st.dataframe(pd.DataFrame(opt_rows), use_container_width=True, hide_index=True)
else:
    st.info("No open option positions yet. Add them in 'Manage Open Options' section above.")

# === MANUAL UPDATES & GROWTH CHART ===
# ... (your existing Manual Updates and Growth Tracker sections remain unchanged) ...

st.caption("Wealth Growth Pro — Multiple options per ticker supported")

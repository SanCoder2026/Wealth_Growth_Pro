import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime
import glob
import shutil

# === CONFIG ===
st.set_page_config(page_title="Wealth Growth Pro → $1M", layout="wide", initial_sidebar_state="expanded")
PREMIUM_TARGET_MONTHLY = 100000.0

# Attractive centered title
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

# Your exact target allocation percentages (sum = 100%)
TARGET_ALLOCATIONS = {
    "SOXL": 0.30,
    "SLV": 0.25,
    "TQQQ": 0.16,
    "URA": 0.10,
    "IAU": 0.06,
    "COPX": 0.06,
    "UPRO": 0.06,
    "UAMY": 0.01,
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

# === LOAD / SAVE / VERSIONING ===
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
    
    # Default starting tickers with your targets - initial_capital = 0 for new users
    default_etfs = {}
    for ticker, pct in TARGET_ALLOCATIONS.items():
        default_etfs[ticker] = {
            "shares": 0.0,
            "cost_basis": 0.0,
            "target_pct": pct
        }
    
    return {
        "etfs": default_etfs,
        "history": [],
        "initial_capital": 0.0,           # new users start at 0 - must set it
        "capital_additions": [],
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

# === INITIAL CAPITAL SETUP (only shown if not set) ===
if initial_capital <= 0:
    st.warning("Initial capital has not been set yet. Please define your starting point.")
    with st.form(key="set_initial_capital_form"):
        st.subheader("Set Your Starting Capital")
        initial_input = st.number_input(
            "Initial Investment Amount ($)",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            format="%.2f",
            help="This is your starting equity before any trades or additions"
        )
        submit_btn = st.form_submit_button("Confirm & Start", type="primary")
        
        if submit_btn and initial_input > 0:
            initial_capital = float(initial_input)
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({
                "date": today,
                "portfolio_value": 0.0,
                "margin_debt": 0.0,
                "premium": 0,
                "note": "Initial capital set"
            })
            save_version({
                "etfs": etfs,
                "history": history,
                "initial_capital": initial_capital,
                "capital_additions": capital_additions
            })
            st.success(f"Initial capital set to **${initial_capital:,.2f}**")
            st.rerun()
else:
    st.info(f"Initial capital: **${initial_capital:,.2f}**")
    # Optional: allow change (with confirmation)
    if st.button("Change Initial Capital (affects calculations)", type="secondary"):
        with st.form(key="change_initial_form"):
            new_initial = st.number_input(
                "New Initial Capital ($)",
                min_value=0.0,
                value=initial_capital,
                step=1000.0,
                format="%.2f"
            )
            col_confirm, col_cancel = st.columns(2)
            if col_confirm.form_submit_button("Update", type="primary"):
                initial_capital = float(new_initial)
                save_version({
                    "etfs": etfs,
                    "history": history,
                    "initial_capital": initial_capital,
                    "capital_additions": capital_additions
                })
                st.success("Initial capital updated")
                st.rerun()
            if col_cancel.form_submit_button("Cancel"):
                st.rerun()

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
total_capital_added = initial_capital + sum(a.get("amount", 0) for a in capital_additions)
net_equity = gross_value - margin
profit = net_equity - total_capital_added
pct_to_m = max(0, (net_equity / 1000000) * 100) if net_equity > 0 else 0
monthly_premium_est = sum(h.get("premium", 0) for h in history[-4:]) if history else 0

# === DASHBOARD ===
st.success(f"Welcome back, {username}!")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")

st.caption(f"Monthly Premium Estimate: ${monthly_premium_est:,.2f} (Target: ${PREMIUM_TARGET_MONTHLY:,.0f})")

# The rest of the code (capital & margin expander, ticker management, rebalance, holdings table, manual updates, chart) 
# remains the same as in the previous full version you have.
# Copy-paste the remaining sections from your last working full code here...

# For completeness, here's a minimal placeholder for the rest:
st.markdown("---")
st.subheader("Portfolio Management Sections")
st.info("Capital & Margin, Ticker Management, Holdings Table, Manual Updates, and Chart sections go here (same as previous version)")

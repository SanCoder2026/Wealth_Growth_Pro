import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
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
        → Building Toward $1 Million • Google Sheets Backend ("Option" Spreadsheet)
    </p>
    <hr style='border-top: 3px solid #1E90FF;'>
    """,
    unsafe_allow_html=True
)

TARGET_ALLOCATIONS = {
    "SOXL": 0.30, "SLV": 0.25, "TQQQ": 0.16, "URA": 0.10,
    "IAU": 0.06, "COPX": 0.06, "UPRO": 0.06, "UAMY": 0.01,
}

# === IMPROVED GOOGLE SHEETS CLIENT ===
@st.cache_resource(show_spinner="Connecting to Google Sheets...")
def get_gspread_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)

gc = get_gspread_client()

# Open spreadsheet by name "Option"
try:
    sh = gc.open("Option")
except Exception as e:
    st.error(f"Could not open spreadsheet 'Option'. Error: {str(e)}")
    st.stop()

# Get or create worksheets
def get_worksheet(name):
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=name, rows=500, cols=20)

ws_etfs = get_worksheet("ETFs")
ws_history = get_worksheet("History")
ws_capital = get_worksheet("Capital")
ws_options = get_worksheet("Options")

# === LOAD DATA FUNCTIONS ===
def load_etfs():
    records = ws_etfs.get_all_records()
    etfs = {}
    for r in records:
        if r.get("Ticker"):
            etfs[r["Ticker"]] = {
                "shares": float(r.get("Shares", 0)),
                "cost_basis": float(r.get("CostBasis", 0)),
                "target_pct": float(r.get("TargetPct", TARGET_ALLOCATIONS.get(r["Ticker"], 0.01))),
                "contracts_sold": int(r.get("ContractsSold", 0)),
                "weekly_contracts": int(r.get("WeeklyContracts", 0)),
            }
    return etfs

def load_history():
    return ws_history.get_all_records(default_value=0)

def load_capital():
    records = ws_capital.get_all_records()
    initial = 0.0
    cash = 0.0
    margin = 0.0
    additions = []
    for r in records:
        if r.get("InitialCapital"):
            initial = float(r.get("InitialCapital", 0))
        if r.get("CashBalance"):
            cash = float(r.get("CashBalance", 0))
        if r.get("MarginDebt"):
            margin = float(r.get("MarginDebt", 0))
        if r.get("AdditionAmount"):
            additions.append({"date": r.get("Date"), "amount": float(r.get("AdditionAmount", 0))})
    return initial, cash, margin, additions

def load_options():
    return ws_options.get_all_records()

etfs = load_etfs()
history = load_history()
initial_capital, cash_balance, margin, capital_additions = load_capital()
option_trades = load_options()

# Username
username = st.text_input("👤 User Name", value=st.session_state.get("username", "Investor"), key="username")
st.session_state.username = username

# === PRICE FETCH ===
@st.cache_data(ttl=300)
def fetch_prices(tickers):
    if not tickers:
        return {}
    try:
        data = yf.Tickers(" ".join(tickers))
        return {t: round(data.tickers[t].info.get("currentPrice") or 
                        data.tickers[t].info.get("regularMarketPrice", 0), 4)
                for t in tickers}
    except:
        return {t: 0 for t in tickers}

prices = fetch_prices(list(etfs.keys()) or list(TARGET_ALLOCATIONS.keys()))

# === CALCULATIONS ===
gross_value = sum(etfs.get(t, {}).get("shares", 0) * prices.get(t, 0) for t in etfs)
total_capital_added = initial_capital + sum(a.get("amount", 0) for a in capital_additions)
net_equity = gross_value - margin + cash_balance
profit = net_equity - total_capital_added
pct_to_m = (net_equity / 1_000_000) * 100 if net_equity > 0 else 0

st.success(f"Welcome back, **{username}**! Data synced from Google Sheets.")
cols = st.columns(5)
cols[0].metric("Gross Portfolio", f"${gross_value:,.2f}")
cols[1].metric("Margin Debt", f"${margin:,.2f}")
cols[2].metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
cols[3].metric("Total Capital Added", f"${total_capital_added:,.2f}")
cols[4].metric("Progress to $1M", f"{pct_to_m:.1f}%")

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
            ws_capital.append_row([date_str, amt, cash_balance, margin, initial_capital, "Capital Added"])
            st.success(f"Added ${amt:,.2f} — Cash updated")
            st.rerun()

    with c2:
        st.subheader("Margin Debt")
        new_margin = st.number_input("Margin ($)", value=float(margin), step=100.0)
        if st.button("Update Margin"):
            margin = new_margin
            ws_capital.append_row([datetime.now().strftime("%Y-%m-%d"), 0, cash_balance, margin, initial_capital, "Margin Update"])
            st.success("Margin updated")
            st.rerun()

    with c3:
        st.subheader("💵 Cash Balance")
        new_cash = st.number_input("Cash ($)", value=float(cash_balance), step=100.0)
        if st.button("Update Cash"):
            cash_balance = new_cash
            ws_capital.append_row([datetime.now().strftime("%Y-%m-%d"), 0, cash_balance, margin, initial_capital, "Cash Update"])
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

# === GROWTH TRACKER + MONTHLY PREMIUM CHART ===
st.subheader("Growth Tracker")
if history:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"], errors='coerce')
    df = df.dropna(subset=["date"])
    df["cum_premium"] = df.get("premium", pd.Series(0)).cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df.get("portfolio_value", 0), name="Gross Value", line=dict(color="#1E90FF")))
    fig.add_trace(go.Scatter(x=df["date"], y=[net_equity] * len(df), name="Net Equity (Current)", line=dict(color="green")))
    fig.add_trace(go.Scatter(x=df["date"], y=df["cum_premium"], name="Cumulative Premium P&L", line=dict(color="orange", dash="dot")))
    fig.add_hline(y=1000000, line_dash="dash", annotation_text="$1M Target")
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("📅 Monthly Premium Income")
if history:
    dfh = pd.DataFrame(history)
    dfh["date"] = pd.to_datetime(dfh["date"], errors='coerce')
    dfh["month"] = dfh["date"].dt.strftime("%Y-%m")
    monthly = dfh.groupby("month")["premium"].sum().reset_index()
    fig_bar = go.Figure(go.Bar(x=monthly["month"], y=monthly["premium"], marker_color="#1E90FF"))
    fig_bar.update_layout(height=400, xaxis_title="Month", yaxis_title="Premium ($)")
    st.plotly_chart(fig_bar, use_container_width=True)

st.caption("✅ All data is saved live to your 'Option' Google Spreadsheet — works on mobile & desktop!")

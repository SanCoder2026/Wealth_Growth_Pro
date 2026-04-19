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

# Target allocations
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
    
    default_etfs = {}
    for ticker, pct in TARGET_ALLOCATIONS.items():
        default_etfs[ticker] = {
            "shares": 0.0,
            "cost_basis": 0.0,
            "target_pct": pct,
            "contracts_sold": 0,
            "weekly_contracts": 0,
            "premium_per": 0.0,
            "sold_date": "",
            "current_strike": 0.0,
            "current_expiry": ""
        }
    
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

# === HISTORY & RESTORE SECTION ===
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
        st.write("Upload backup from old version")
        uploaded = st.file_uploader("Choose backup JSON file", type=["json"])
        if uploaded is not None:
            try:
                backup_data = json.load(uploaded)
                required = ["etfs", "history", "initial_capital", "capital_additions", "option_trades"]
                if all(k in backup_data for k in required):
                    if st.button("Restore from this file (overwrites current data)", type="primary"):
                        with open(LATEST_FILE, "w") as f:
                            json.dump(backup_data, f, indent=2)
                        st.success("Backup restored! Refreshing page...")
                        st.rerun()
                else:
                    st.error("Invalid backup — missing required sections")
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")

# Reset button
if st.button(f"🔴 Reset ALL {username}'s Data", type="secondary"):
    if st.button("Confirm — this deletes everything permanently"):
        if os.path.exists(DATA_DIR):
            shutil.rmtree(DATA_DIR)
        st.success("All data deleted. Refresh page.")
        st.rerun()

# === INITIAL CAPITAL SETUP ===
if initial_capital <= 0:
    st.warning("Initial capital has not been set yet. Please define your starting point.")
    with st.form(key="set_initial_capital_form"):
        st.subheader("Set Your Starting Capital")
        initial_input = st.number_input(
            "Initial Investment Amount ($)",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            format="%.2f"
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
                "capital_additions": capital_additions,
                "option_trades": option_trades,
                "cash_balance": cash_balance
            })
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

# Monthly Average Premium (for dashboard)
current_year = datetime.now().year
year_history = [h for h in history if pd.to_datetime(h.get("date", "")).year == current_year]
monthly_premiums = {}
for h in year_history:
    month = pd.to_datetime(h.get("date", "")).strftime("%Y-%m")
    monthly_premiums[month] = monthly_premiums.get(month, 0) + float(h.get("premium", 0))
avg_monthly_premium = sum(monthly_premiums.values()) / len(monthly_premiums) if monthly_premiums else 0

# === DASHBOARD ===
st.success(f"Welcome back, {username}!")
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("Gross Portfolio", f"${gross_value:,.2f}")
col2.metric("Current Margin", f"${margin:,.2f}")
col3.metric("Net Equity", f"${net_equity:,.2f}", delta=f"${profit:,.2f}")
col4.metric("Total Capital Added", f"${total_capital_added:,.2f}")
col5.metric("Progress to $1M", f"{pct_to_m:.2f}%")
col6.metric("Profit / Loss", f"${profit:,.2f}", delta=f"${profit:,.2f}", delta_color="normal" if profit >= 0 else "inverse")
col7.metric("Avg Monthly Premium", f"${avg_monthly_premium:,.0f}", 
            delta=f"{(avg_monthly_premium / PREMIUM_TARGET_MONTHLY * 100):.1f}% of goal")

st.caption(f"**Cash**: ${cash_balance:,.2f} | Recent Premium Est: ${monthly_premium_est:,.0f}")

# === CAPITAL & MARGIN ===
with st.expander("💰 Capital & Margin"):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Add Capital")
        add_amount = st.number_input("Amount ($)", min_value=0.0, step=1000.0, key="add_cap")
        add_date = st.date_input("Date", value=datetime.now().date(), key="add_date_cap")
        if st.button("Add Capital") and add_amount > 0:
            capital_additions.append({"date": add_date.strftime("%Y-%m-%d"), "amount": float(add_amount)})
            cash_balance += float(add_amount)
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "portfolio_value": gross_value, "margin_debt": float(margin), "premium": 0})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success(f"Added ${add_amount:,.2f}")
            st.rerun()

    with col2:
        st.subheader("Margin Debt")
        margin_input = st.number_input("Current Margin ($)", min_value=0.0, value=float(margin), step=100.0, format="%.2f")
        if st.button("Update Margin") and margin_input != margin:
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "portfolio_value": gross_value, "margin_debt": float(margin_input), "premium": 0})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success("Margin updated")
            st.rerun()

    with col3:
        st.subheader("💵 Cash Balance")
        cash_input = st.number_input("Current Cash ($)", min_value=0.0, value=float(cash_balance), step=100.0, format="%.2f")
        if st.button("Update Cash"):
            cash_balance = float(cash_input)
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success(f"Cash updated to ${cash_balance:,.2f}")
            st.rerun()

# === MANAGE TICKERS & ADD NEW ===
with st.expander("📈 Manage Tickers & Rebalance", expanded=True):
    st.subheader("Add New Ticker")
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_ticker = st.text_input("Ticker Symbol", "", key="new_ticker_input", placeholder="e.g. NVDA, TSLA").strip().upper()
    with col_add2:
        if st.button("Add & Rebalance", type="primary", use_container_width=True):
            if new_ticker and new_ticker not in etfs:
                new_target = 0.05 if new_ticker == "IBIT" else 0.005
                current_total = sum(d.get("target_pct", 0) for d in etfs.values())
                if current_total > 0:
                    scale_factor = (1.0 - new_target) / current_total
                    for t in etfs:
                        etfs[t]["target_pct"] *= scale_factor
                etfs[new_ticker] = {
                    "shares": 0.0,
                    "cost_basis": 0.0,
                    "target_pct": new_target,
                    "contracts_sold": 0,
                    "weekly_contracts": 0,
                    "premium_per": 0.0,
                    "sold_date": "",
                    "current_strike": 0.0,
                    "current_expiry": ""
                }
                save_version({
                    "etfs": etfs,
                    "history": history,
                    "initial_capital": initial_capital,
                    "capital_additions": capital_additions,
                    "option_trades": option_trades,
                    "cash_balance": cash_balance
                })
                st.success(f"Added **{new_ticker}** — targets rebalanced to 100%")
                st.rerun()
            else:
                st.warning("Ticker already exists or input invalid")

# === UPDATE EXISTING OPTIONS / CONTRACTS ===
with st.expander("📊 Update Existing Options / Contracts", expanded=False):
    st.subheader("Update Contracts for Ticker")
    ct_tk = st.selectbox("Select Ticker", list(etfs.keys()), key="ct_update_tk")
    if ct_tk:
        col1, col2 = st.columns(2)
        with col1:
            contracts = st.number_input(
                "Number of Contracts Sold",
                min_value=0,
                step=1,
                value=int(etfs[ct_tk].get("contracts_sold", 0)),
                key="contracts_upd"
            )
        with col2:
            premium_per = st.number_input(
                "Premium Value ($ per contract)",
                min_value=0.0,
                step=0.05,
                value=float(etfs[ct_tk].get("premium_per", 0.0)),
                key="premium_upd"
            )
        
        col3, col4 = st.columns(2)
        with col3:
            strike = st.number_input(
                "Strike Price",
                min_value=0.0,
                step=0.01,
                value=float(etfs[ct_tk].get("current_strike", 0.0)),
                format="%.2f",
                key="strike_upd"
            )
        with col4:
            sold_date = st.date_input(
                "Sold Date",
                value=datetime.now().date(),
                key="sold_date_upd"
            )
        
        expiry_date = st.date_input(
            "Expiry Date",
            value=datetime.now().date() + timedelta(days=7),
            key="expiry_upd"
        )
        
        if st.button("Update Contracts & Position Info"):
            etfs[ct_tk]["contracts_sold"] = contracts
            etfs[ct_tk]["premium_per"] = float(premium_per)
            etfs[ct_tk]["current_strike"] = float(strike)
            etfs[ct_tk]["current_expiry"] = expiry_date.strftime("%Y-%m-%d")
            etfs[ct_tk]["sold_date"] = sold_date.strftime("%Y-%m-%d")
            
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success(f"Options updated for **{ct_tk}**")
            st.rerun()

# === CURRENT HOLDINGS TABLE ===
st.subheader("Current Holdings")

rows = []
total_val = gross_value if gross_value > 0 else 1.0

for t in sorted(etfs.keys()):
    d = etfs[t]
    current_price = prices.get(t, 0)
    shares = float(d.get("shares", 0))
    cost_basis = float(d.get("cost_basis", 0))
    
    purchase_value = shares * cost_basis
    current_value  = shares * current_price
    
    profit_dollar = current_value - purchase_value
    profit_pct    = (profit_dollar / purchase_value * 100) if purchase_value > 0 else 0
    
    if "SOXL" in t or "TQQQ" in t:
        otm_pct = 0.14
        delta_est = "~30Δ"
    elif "URA" in t:
        otm_pct = 0.12
        delta_est = "~28–32Δ"
    elif "SLV" in t or "COPX" in t:
        otm_pct = 0.085
        delta_est = "~30Δ"
    elif "IAU" in t or "UPRO" in t:
        otm_pct = 0.065
        delta_est = "~30–35Δ"
    else:
        otm_pct = 0.10
        delta_est = "~30Δ"
    
    suggested_strike = round(current_price * (1 + otm_pct), 2) if current_price > 0 else "-"
    
    rows.append({
        "Ticker": t,
        "Shares": f"{shares:.4f}",
        "Purchase Price": f"${cost_basis:.2f}" if cost_basis > 0 else "-",
        "Current Price": f"${current_price:.2f}" if current_price > 0 else "-",
        "Current Value": f"${current_value:,.2f}",
        "Current %": f"{(current_value / total_val * 100):.2f}%",
        "Target %": f"{d.get('target_pct', 0)*100:.1f}%",
        "Profit %": f"{profit_pct:+.2f}%" if purchase_value > 0 else "-",
        "Suggested Strike": f"${suggested_strike}",
        "Suggested Expiry": (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d"),
        "Suggested Action": "Sell New Call" if d.get("contracts_sold", 0) == 0 else "Roll Call"
    })

st.dataframe(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True
)

# === OPEN OPTIONS POSITIONS TABLE ===
st.subheader("🛡️ Open Options Positions")

open_options = []

for ticker, info in etfs.items():
    contracts = int(info.get("contracts_sold", 0))
    expiry = info.get("current_expiry")
    strike = float(info.get("current_strike", 0))
    premium_per = float(info.get("premium_per", 0.0))
    if contracts > 0 and expiry:
        open_options.append({
            "ticker": ticker,
            "strike": strike,
            "expiry": expiry,
            "contracts": contracts,
            "premium_per": premium_per,
            "sold_date": info.get("sold_date", "")
        })

if open_options:
    opt_rows = []
    today = datetime.now().date()
    
    for trade in open_options:
        try:
            expiry_dt = datetime.strptime(trade["expiry"], "%Y-%m-%d").date()
            days_left = max(0, (expiry_dt - today).days)
        except:
            days_left = 0
            
        current_price = prices.get(trade.get("ticker", ""), 0)
        itm_otm = "ITM" if current_price > trade.get("strike", 0) else "OTM" if current_price < trade.get("strike", 0) else "ATM"
        
        otm_pct = 0.12 if "SOXL" in trade.get("ticker", "") else 0.09 if "TQQQ" in trade.get("ticker", "") else 0.07
        suggested_roll = round(current_price * (1 + otm_pct), 2) if current_price > 0 else "-"
        
        opt_rows.append({
            "Ticker": trade.get("ticker", ""),
            "Contracts": trade.get("contracts", 0),
            "Strike": f"${trade.get('strike', 0):.2f}",
            "Expiry": trade.get("expiry", ""),
            "DTE": days_left,
            "Moneyness": itm_otm,
            "Sold Date": trade.get("sold_date", ""),
            "Premium per Contract": f"${trade.get('premium_per', 0):.2f}",
            "Suggested Roll Strike": f"${suggested_roll}"
        })
    
    st.dataframe(
        pd.DataFrame(opt_rows),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No open option positions yet. Go to 'Update Existing Options / Contracts' to add data.")

# === MONTHLY PREMIUM BAR CHART ===
st.subheader("📅 Monthly Premium Income vs $100K Goal")

if history:
    df_hist = pd.DataFrame(history)
    df_hist["date"] = pd.to_datetime(df_hist["date"], errors="coerce")
    df_hist = df_hist.dropna(subset=["date"])
    df_hist["month"] = df_hist["date"].dt.strftime("%Y-%m")
    monthly = df_hist.groupby("month")["premium"].sum().reset_index()
    monthly = monthly.sort_values("month")
    
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=monthly["month"], 
        y=monthly["premium"], 
        name="Premium Earned",
        marker_color="#1E90FF"
    ))
    fig_bar.add_hline(y=PREMIUM_TARGET_MONTHLY, line_dash="dash", annotation_text="$100K Goal", line_color="red")
    fig_bar.update_layout(
        height=400, 
        xaxis_title="Month",
        yaxis_title="Premium ($)",
        title="Monthly Premium Income"
    )
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No premium data recorded yet. Use 'Record Premium' in Manual Updates to see the chart.")

# === MANUAL UPDATES ===
with st.expander("📊 Manual Updates"):
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Add Purchase")
        tk = st.selectbox("Ticker", list(etfs.keys()), key="buy_tk")
        sh = st.number_input("Shares", 0.0001, step=0.0001)
        pr = st.number_input("Avg Price", 0.01, step=0.01)
        if st.button("Submit Buy"):
            if sh > 0 and pr > 0:
                old = etfs[tk]
                new_s = float(old["shares"]) + float(sh)
                new_b = (float(old["shares"]) * float(old["cost_basis"]) + float(sh) * float(pr)) / new_s if new_s > 0 else float(pr)
                etfs[tk]["shares"] = new_s
                etfs[tk]["cost_basis"] = new_b
                history.append({"date": datetime.now().strftime("%Y-%m-%d"), "portfolio_value": gross_value, "margin_debt": float(margin), "premium": 0})
                save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                              "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
                st.success("Purchase added")
                st.rerun()

    with col_r:
        st.subheader("Sell / Reduce Shares")
        tk_sell = st.selectbox("Ticker (Sell)", list(etfs.keys()), key="sell_tk")
        sh_sell = st.number_input("Shares to Sell", min_value=0.0001, step=0.0001)
        if st.button("Submit Sell"):
            if sh_sell > 0:
                old = etfs[tk_sell]
                current_shares = float(old["shares"])
                if sh_sell > current_shares:
                    st.error(f"Cannot sell more ({sh_sell:.4f}) than owned ({current_shares:.4f})")
                else:
                    new_shares = current_shares - float(sh_sell)
                    etfs[tk_sell]["shares"] = new_shares
                    if new_shares <= 0:
                        etfs[tk_sell]["cost_basis"] = 0.0
                    history.append({"date": datetime.now().strftime("%Y-%m-%d"), "portfolio_value": gross_value, "margin_debt": float(margin), "premium": 0})
                    save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                                  "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
                    st.success(f"Sold {sh_sell:.4f} shares of {tk_sell}")
                    st.rerun()

        st.subheader("Record Premium")
        premium = st.number_input("Premium Received ($)", 0.0, step=10.0)
        if st.button("Record") and premium > 0:
            today = datetime.now().strftime("%Y-%m-%d")
            history.append({"date": today, "premium": float(premium), "portfolio_value": gross_value, "margin_debt": float(margin)})
            save_version({"etfs": etfs, "history": history, "initial_capital": initial_capital,
                          "capital_additions": capital_additions, "option_trades": option_trades, "cash_balance": cash_balance})
            st.success("Premium recorded")
            st.rerun()

# === GROWTH CHART ===
st.subheader("Growth Tracker")
if history:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df["net"] = df["portfolio_value"] - df.get("margin_debt", 0.0) - initial_capital

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["portfolio_value"], name="Gross"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["net"], name="Net Equity", line=dict(color="green")))
    fig.add_hline(y=1000000, line_dash="dash", annotation_text="$1M")
    fig.update_layout(height=550)
    st.plotly_chart(fig, use_container_width=True)

st.caption("Wealth Growth Pro — Monthly Premium Bar Chart Added")

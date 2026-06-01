"""
Wealth Growth — Covered-Call Portfolio Manager
Rebuilt: accurate data, volatility-based strikes, cleaner UI.

Single-file Streamlit app. Drop strike_engine.py in the same folder.

Run:  streamlit run app.py
"""

import os
import json
import time
import glob
import math
import shutil
from datetime import datetime, timedelta, date

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

# Volatility-based options math (verified module)
from strike_engine import (
    realized_vol_for, suggest_strike, prob_itm, call_delta,
    sds_otm, trend_strength_for, enrich_option_row,
)
import allocation_engine as ae

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PREMIUM_TARGET_MONTHLY = 100_000
MILLION_GOAL = 1_000_000

TARGET_ALLOCATIONS = {
    "SOXL": 0.30, "TQQQ": 0.20, "SLV": 0.20,
    "URA": 0.10, "IBIT": 0.10, "COPX": 0.10,
}

# Per-ticker rough IV fallback if live vol fetch fails (annualized).
# Used ONLY when the live volatility fetch fails; otherwise realized vol is used.
VOL_FALLBACK = {
    "SOXL": 0.70, "TQQQ": 0.55, "SLV": 0.25, "URA": 0.35, "IBIT": 0.60,
    "COPX": 0.35, "IAU": 0.15, "UPRO": 0.50, "UAMY": 0.80, "SNPS": 0.40,
    "UVXY": 0.95, "SOXX": 0.30, "GLD": 0.15, "SPY": 0.18,
}
DEFAULT_VOL_FALLBACK = 0.45   # only for truly unknown tickers

st.set_page_config(page_title="Wealth Growth", layout="wide",
                   page_icon="📈", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Styling — clean, professional, restrained
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  /* Typography */
  @import url('https://fonts.googleapis.com/css2?family=Spline+Sans:wght@400;500;600;700&family=Spline+Sans+Mono:wght@400;500&display=swap');
  html, body, [class*="css"] { font-family: 'Spline Sans', sans-serif; }
  code, .mono { font-family: 'Spline Sans Mono', monospace; }

  /* Tighten default Streamlit padding */
  .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1300px; }

  /* Metric cards */
  div[data-testid="stMetric"] {
      background: #11161f;
      border: 1px solid #1f2733;
      border-radius: 12px;
      padding: 14px 16px;
  }
  div[data-testid="stMetricLabel"] { color: #8b97a8; font-size: 0.72rem;
      text-transform: uppercase; letter-spacing: 0.05em; }
  div[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 700; }

  /* Headings */
  h1 { font-weight: 700; letter-spacing: -0.02em; }
  h2, h3 { font-weight: 600; letter-spacing: -0.01em; color: #e6edf3; }

  /* Dataframe polish */
  .stDataFrame { border-radius: 10px; overflow: hidden; }

  /* Buttons */
  .stButton button { border-radius: 9px; font-weight: 600; }

  /* Section divider */
  hr { border-color: #1f2733; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data persistence (same JSON format as your existing app — backups still load)
# ---------------------------------------------------------------------------

def user_paths(username):
    base = f"data/{username}/"
    return {
        "dir": base,
        "latest": f"{base}{username}_latest.json",
        "history_dir": f"{base}{username}_history/",
    }


def ensure_dirs(username):
    p = user_paths(username)
    os.makedirs(p["dir"], exist_ok=True)
    os.makedirs(p["history_dir"], exist_ok=True)
    return p


DEFAULT_DATA = lambda: {
    "etfs": {t: {"shares": 0.0, "cost_basis": 0.0, "target_pct": pct}
             for t, pct in TARGET_ALLOCATIONS.items()},
    "history": [],
    "initial_capital": 0.0,
    "capital_additions": [],
    "option_trades": [],
    "cash_balance": 0.0,
    "open_options": [],
}


def _normalize(data):
    """Backfill any missing keys so older backups load cleanly."""
    data.setdefault("cash_balance", 0.0)
    data.setdefault("open_options", [])
    data.setdefault("capital_additions", [])
    data.setdefault("option_trades", [])
    data.setdefault("history", [])
    data.setdefault("initial_capital", 0.0)
    data.setdefault("alloc_settings", {       # regime rotation settings
        "base_tech_share": 0.50, "max_tilt": 0.30, "max_weight": 0.30,
    })
    for t, etf in data.get("etfs", {}).items():
        etf.setdefault("shares", 0.0)
        etf.setdefault("cost_basis", 0.0)
        etf.setdefault("target_pct", 0.0)
    # Migrate legacy single-option fields → open_options list
    for t, etf in list(data.get("etfs", {}).items()):
        if int(etf.get("contracts_sold", 0)) > 0 and etf.get("current_expiry"):
            data["open_options"].append({
                "id": f"legacy_{t}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "ticker": t, "contracts": int(etf["contracts_sold"]),
                "strike": float(etf.get("current_strike", 0)),
                "expiry": etf.get("current_expiry", ""),
                "sold_date": etf.get("sold_date", ""),
                "premium_per": float(etf.get("premium_per", 0)),
            })
            for k in ("contracts_sold", "premium_per", "sold_date",
                      "current_strike", "current_expiry"):
                etf.pop(k, None)
    return data


def load_latest(username):
    p = user_paths(username)
    if os.path.exists(p["latest"]):
        try:
            with open(p["latest"]) as f:
                return _normalize(json.load(f))
        except Exception:
            pass
    return DEFAULT_DATA()


def save_version(username, data):
    p = ensure_dirs(username)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    with open(f"{p['history_dir']}{ts}.json", "w") as f:
        json.dump(data, f, indent=2)
    with open(p["latest"], "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Accurate price fetching — multi-source with quality flags
# ---------------------------------------------------------------------------

@st.cache_data(ttl=90)
def fetch_prices(tickers_tuple):
    """
    Returns {ticker: {'price': float, 'source': str, 'ok': bool}}.
    Tries fast_info → info → 1d history, per ticker. Reports the source so
    you can see data quality at a glance.
    """
    tickers = list(tickers_tuple)
    out = {}
    for t in tickers:
        price, source = 0.0, "none"
        try:
            tk = yf.Ticker(t)
            try:
                fi = tk.fast_info
                price = float(fi.get("lastPrice") or fi.get("regularMarketPrice") or 0)
                if price > 0:
                    source = "fast_info"
            except Exception:
                price = 0
            if price <= 0:
                info = tk.info
                price = float(info.get("currentPrice") or info.get("regularMarketPrice")
                              or info.get("previousClose") or 0)
                if price > 0:
                    source = "info"
            if price <= 0:
                h = tk.history(period="1d", interval="1m")
                if not h.empty:
                    price = float(h["Close"].iloc[-1]); source = "history"
        except Exception:
            pass
        out[t] = {"price": round(price, 4), "source": source, "ok": price > 0}
    return out


def get_vol(ticker):
    """Realized vol with per-ticker fallback so the app never shows blanks."""
    v = realized_vol_for(ticker)
    if v and v > 0:
        return v, "realized"
    return VOL_FALLBACK.get(ticker, DEFAULT_VOL_FALLBACK), "fallback"


# ---------------------------------------------------------------------------
# Login / user selection
# ---------------------------------------------------------------------------

st.title("📈 Wealth Growth")
st.caption("Covered-call portfolio manager · volatility-based strike selection")

if "username" not in st.session_state:
    st.session_state.username = ""

if not st.session_state.username:
    with st.container(border=True):
        st.subheader("Sign in")
        u = st.text_input("Username", placeholder="your name", label_visibility="collapsed")
        if st.button("Continue", type="primary"):
            if u.strip():
                st.session_state.username = u.strip()
                st.rerun()
            else:
                st.error("Enter a username to continue.")
    st.stop()

username = st.session_state.username
ensure_dirs(username)

# Load data once per run
data = load_latest(username)
etfs = data["etfs"]
history = data["history"]
initial_capital = float(data["initial_capital"])
capital_additions = data["capital_additions"]
option_trades = data["option_trades"]
cash_balance = float(data["cash_balance"])
open_options = data["open_options"]
alloc_settings = data.get("alloc_settings", {})

# Current margin = last recorded margin_debt
margin = 0.0
for h in reversed(history):
    if h.get("margin_debt") is not None:
        try:
            margin = float(h["margin_debt"]); break
        except Exception:
            pass

# Snapshot once per session
if "snapped" not in st.session_state:
    save_version(username, data)
    st.session_state.snapped = True

# Fetch prices
price_data = fetch_prices(tuple(etfs.keys()))
prices = {t: price_data[t]["price"] for t in price_data}


# ---------------------------------------------------------------------------
# Portfolio calculations
# ---------------------------------------------------------------------------
gross_value = sum(float(etfs[t]["shares"]) * prices.get(t, 0) for t in etfs)
total_capital_added = initial_capital + sum(a.get("amount", 0) for a in capital_additions)
net_equity = gross_value - margin + cash_balance
profit = net_equity - total_capital_added

# Monthly premium average (current year)
monthly_premiums = {}
for h in history:
    try:
        if pd.to_datetime(h.get("date", "")).year == datetime.now().year:
            m = pd.to_datetime(h["date"]).strftime("%Y-%m")
            monthly_premiums[m] = monthly_premiums.get(m, 0) + float(h.get("premium", 0))
    except Exception:
        continue
avg_monthly_premium = (sum(monthly_premiums.values()) / len(monthly_premiums)
                       if monthly_premiums else 0)

# Leverage ratio (a key risk number given margin use)
leverage = (gross_value / net_equity) if net_equity > 0 else 0

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
top = st.columns([6, 1])
with top[0]:
    st.markdown(f"#### Welcome back, **{username}**")
with top[1]:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# Data quality strip
bad = [t for t, d in price_data.items() if not d["ok"]]
if bad:
    st.warning(f"⚠️ Price unavailable for: {', '.join(bad)} — values may be off. Try Refresh.")

m = st.columns(4)
m[0].metric("Net Equity", f"${net_equity:,.0f}", delta=f"${profit:,.0f}")
m[1].metric("Gross Portfolio", f"${gross_value:,.0f}")
m[2].metric("Margin Debt", f"${margin:,.0f}")
m[3].metric("Leverage", f"{leverage:.2f}×",
            delta="watch" if leverage > 1.5 else "ok",
            delta_color="inverse" if leverage > 1.5 else "normal")

m2 = st.columns(4)
m2[0].metric("Cash", f"${cash_balance:,.0f}")
m2[1].metric("Capital Added", f"${total_capital_added:,.0f}")
m2[2].metric("Progress to $1M", f"{max(0, net_equity/MILLION_GOAL*100):.1f}%")
m2[3].metric("Avg Monthly Premium", f"${avg_monthly_premium:,.0f}",
             delta=f"{avg_monthly_premium/PREMIUM_TARGET_MONTHLY*100:.0f}% of goal")

if initial_capital <= 0:
    st.info("Set your starting capital in the sidebar to begin tracking growth.")

st.divider()


# ---------------------------------------------------------------------------
# STRIKE ADVISOR — volatility-based (replaces fixed-% guesses)
# ---------------------------------------------------------------------------
st.subheader("🎯 Weekly Strike Advisor")
st.caption("Strikes sized by each ticker's actual volatility — not a fixed %. "
           "Pick your comfort level for assignment risk.")

ctrl = st.columns([1, 1, 2])
with ctrl[0]:
    target_prob = st.slider("Target assignment probability", 5, 50, 20, 5,
                            help="Lower = safer/farther strikes, less premium. "
                                 "20% ≈ sell ~0.8σ out.") / 100.0
with ctrl[1]:
    dte = st.number_input("Days to expiry", 1, 60, 7,
                          help="Your weekly cadence = 7")

adv_rows = []
for t in sorted(etfs.keys()):
    if float(etfs[t]["shares"]) <= 0:
        continue
    spot = prices.get(t, 0)
    if spot <= 0:
        continue
    vol, vol_src = get_vol(t)
    sugg = suggest_strike(spot, vol, dte, target_prob=target_prob)
    trend = trend_strength_for(t) or {"label": "—", "score": 0}

    # Trend nudge: strong uptrend → push a bit further out
    nudge = ""
    if trend["score"] >= 70:
        nudge = "strong trend → consider going wider"
    elif trend["score"] < 45:
        nudge = "weak/flat → closer strike ok for premium"

    weekly_sigma = vol / math.sqrt(52) * 100
    adv_rows.append({
        "Ticker": t,
        "Price": f"${spot:,.2f}",
        "Vol (ann)": f"{vol*100:.0f}%" + ("*" if vol_src == "fallback" else ""),
        "1wk ±1σ": f"±{weekly_sigma:.1f}%",
        "Suggested Strike": f"${sugg['strike']:,.2f}",
        "% OTM": f"{sugg['pct_otm']:+.1f}%",
        "σ OTM": f"{sugg['sds_otm']:.2f}" if sugg['sds_otm'] else "-",
        "Assign Prob": f"{target_prob*100:.0f}%",
        "Trend": trend["label"],
        "Note": nudge,
    })

if adv_rows:
    st.dataframe(pd.DataFrame(adv_rows), use_container_width=True, hide_index=True)
    st.caption("σ OTM = standard deviations out (normalized by the stock's own volatility). "
               "`*` = volatility fallback used (live fetch failed). "
               "Strike has ~the chosen assignment probability by Black-Scholes.")
else:
    st.info("Add share holdings below to see strike suggestions.")

st.divider()


# ---------------------------------------------------------------------------
# HOLDINGS
# ---------------------------------------------------------------------------
st.subheader("📊 Holdings")
open_by_ticker = {}
for o in open_options:
    open_by_ticker[o["ticker"]] = open_by_ticker.get(o["ticker"], 0) + o["contracts"]

total_val = gross_value if gross_value > 0 else 1.0
hold_rows = []
for t in sorted(etfs.keys()):
    d = etfs[t]
    spot = prices.get(t, 0)
    shares = float(d["shares"])
    basis = float(d["cost_basis"])
    cur_val = shares * spot
    pur_val = shares * basis
    pnl = cur_val - pur_val
    pnl_pct = (pnl / pur_val * 100) if pur_val > 0 else 0
    hold_rows.append({
        "Ticker": t,
        "Shares": f"{shares:,.2f}",
        "Cost": f"${basis:,.2f}" if basis > 0 else "—",
        "Price": f"${spot:,.2f}" if spot > 0 else "—",
        "Value": f"${cur_val:,.0f}",
        "Weight": f"{cur_val/total_val*100:.1f}%",
        "Target": f"{d.get('target_pct',0)*100:.0f}%",
        "P&L": f"{pnl_pct:+.1f}%" if pur_val > 0 else "—",
        "Open Calls": open_by_ticker.get(t, 0),
    })
st.dataframe(pd.DataFrame(hold_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# OPEN OPTIONS — with live assignment probability + delta (early warning)
# ---------------------------------------------------------------------------
st.subheader("🛡️ Open Option Positions")
if open_options:
    today = date.today()
    opt_rows = []
    high_risk = 0
    below_basis = []
    for o in open_options:
        spot = prices.get(o["ticker"], 0)
        try:
            exp = datetime.strptime(o["expiry"], "%Y-%m-%d").date()
            dleft = max(0, (exp - today).days)
        except Exception:
            dleft = 0
        vol, _ = get_vol(o["ticker"])
        strike = o.get("strike", 0)
        p = prob_itm(spot, strike, dleft, vol) if (spot and strike and dleft) else None
        dlt = call_delta(spot, strike, dleft, vol) if (spot and strike and dleft) else None
        moneyness = ("ITM" if spot > strike else "OTM" if spot < strike else "ATM") if spot else "—"
        if p is not None and p > 0.50:
            high_risk += 1

        # Cost-basis check: would assignment sell shares below what you paid?
        basis = float(etfs.get(o["ticker"], {}).get("cost_basis", 0))
        vs_basis = "—"
        if basis > 0 and strike > 0:
            if strike < basis:
                vs_basis = f"⚠️ -{(1-strike/basis)*100:.0f}%"
                below_basis.append(f"{o['ticker']} (${strike:.0f} strike vs ${basis:.2f} cost)")
            else:
                vs_basis = f"+{(strike/basis-1)*100:.0f}%"

        opt_rows.append({
            "Ticker": o["ticker"],
            "Contracts": o["contracts"],
            "Strike": f"${strike:,.2f}",
            "Expiry": o["expiry"],
            "DTE": dleft,
            "Moneyness": moneyness,
            "Assign Prob": f"{p*100:.0f}%" if p is not None else "—",
            "Delta": f"{dlt:.2f}" if dlt is not None else "—",
            "Strike vs Cost": vs_basis,
            "Premium": f"${o.get('premium_per',0):.2f}",
        })
    st.dataframe(pd.DataFrame(opt_rows), use_container_width=True, hide_index=True)
    if high_risk:
        st.warning(f"⚠️ {high_risk} position(s) have >50% assignment probability — "
                   f"consider rolling if you want to keep the shares.")
    if below_basis:
        st.error("🔻 Strike BELOW cost basis (assignment = loss on shares): "
                 + "; ".join(below_basis)
                 + ". Premium may offset, but you'd sell the stock at a loss.")
    st.caption("Assign Prob & Delta from realized volatility (≈ Robinhood's delta). "
               "'Strike vs Cost' shows gain/loss on shares if assigned. "
               "Premium $0.00 = legacy import; edit the position to set it.")
else:
    st.info("No open option positions. Add one in **Manage Positions** below.")

st.divider()


# ---------------------------------------------------------------------------
# LEAP EXPLORER — real chain data, no fabricated profit numbers
# ---------------------------------------------------------------------------
st.subheader("🔭 LEAP Explorer")
st.caption("Long-dated call data straight from the live chain. No predicted "
           "'profit' — just real prices, delta, and breakeven so you can judge.")

with st.expander("Explore LEAP calls for a ticker", expanded=False):
    lc = st.columns([1, 1, 1])
    with lc[0]:
        leap_ticker = st.selectbox("Ticker", sorted(etfs.keys()), key="leap_tk")
    with lc[1]:
        min_months = st.number_input("Min months out", 3, 24, 6)
    with lc[2]:
        moneyness_filter = st.selectbox("Strikes", ["Near the money", "All OTM", "All"])

    if st.button("Load LEAP chain", type="primary"):
        with st.spinner(f"Fetching {leap_ticker} option chain…"):
            try:
                tk = yf.Ticker(leap_ticker)
                spot = prices.get(leap_ticker, 0) or float(tk.fast_info.get("lastPrice", 0))
                exps = tk.options
                target_exps = [e for e in exps
                               if min_months*30 <= (datetime.strptime(e, "%Y-%m-%d") - datetime.now()).days <= 760]
                rows = []
                for e in target_exps[:6]:
                    try:
                        calls = tk.option_chain(e).calls
                        dte = (datetime.strptime(e, "%Y-%m-%d") - datetime.now()).days
                        for _, r in calls.iterrows():
                            strike = float(r["strike"])
                            if moneyness_filter == "Near the money" and not (spot*0.85 <= strike <= spot*1.15):
                                continue
                            if moneyness_filter == "All OTM" and strike < spot:
                                continue
                            bid, ask = float(r.get("bid", 0)), float(r.get("ask", 0))
                            mid = (bid + ask)/2 if (bid and ask) else float(r.get("lastPrice", 0))
                            if mid <= 0.10:
                                continue
                            iv = float(r.get("impliedVolatility", 0)) or get_vol(leap_ticker)[0]
                            delta = call_delta(spot, strike, dte, iv)
                            breakeven = strike + mid
                            rows.append({
                                "Expiry": e,
                                "DTE": dte,
                                "Strike": f"${strike:,.0f}",
                                "Mid": f"${mid:,.2f}",
                                "Bid/Ask": f"{bid:.2f}/{ask:.2f}",
                                "Delta": f"{delta:.2f}" if delta else "—",
                                "IV": f"{iv*100:.0f}%",
                                "Breakeven": f"${breakeven:,.2f}",
                                "BE % move": f"{(breakeven/spot-1)*100:+.1f}%",
                                "OI": int(r.get("openInterest", 0) or 0),
                            })
                    except Exception:
                        continue
                if rows:
                    st.success(f"{leap_ticker} @ ${spot:,.2f} — {len(rows)} contracts")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                    st.caption("Breakeven = strike + premium paid. 'BE % move' = how far the "
                               "stock must rise just to break even at expiry. Delta ≈ how much "
                               "the option moves per $1 of stock. No profit is predicted — you decide.")
                else:
                    st.warning("No LEAP contracts matched. Try a different ticker or filter.")
            except Exception as ex:
                st.error(f"Could not load chain: {ex}")

st.divider()


# ---------------------------------------------------------------------------
# ALLOCATION MODEL — regime-based tech<->metals rotation (data-driven only)
# ---------------------------------------------------------------------------
st.subheader("🧭 Allocation Model")
st.caption("Tech↔metals rotation. When semis + Nasdaq are strong, the model tilts "
           "toward leveraged tech; when tech weakens, it rotates toward metals "
           "(where safe-haven money flows). Weights within each sleeve come from "
           "premium-yield potential and diversification. Always sums to 100%.")

with st.expander("Compute rotation-based target allocation", expanded=False):
    held = [t for t in etfs if float(etfs[t]["shares"]) > 0]
    if not held:
        st.info("Add holdings first.")
    else:
        # Show sleeve membership
        sleeve_map = {t: ae.classify_sleeve(t) for t in held}
        tech_list = [t for t in held if sleeve_map[t] == "tech"]
        metal_list = [t for t in held if sleeve_map[t] == "metals"]
        other_list = [t for t in held if sleeve_map[t] == "other"]
        sc = st.columns(3)
        sc[0].markdown(f"**Tech sleeve**\n\n{', '.join(tech_list) or '—'}")
        sc[1].markdown(f"**Metals sleeve**\n\n{', '.join(metal_list) or '—'}")
        sc[2].markdown(f"**Other**\n\n{', '.join(other_list) or '—'}")
        st.caption("Sleeve assignment is automatic. (Tell me if any ticker is "
                   "mis-classified and I'll adjust the lists.)")

        st.markdown("**Rotation settings**")
        bc = st.columns(3)
        base_tech = bc[0].slider("Tech share at neutral", 0.30, 0.70,
                                 float(alloc_settings.get("base_tech_share", 0.50)), 0.05,
                                 help="Tech sleeve's share when tech health is neutral (0.5).")
        max_tilt = bc[1].slider("Max rotation swing", 0.10, 0.45,
                                float(alloc_settings.get("max_tilt", 0.30)), 0.05,
                                help="How far the split can shift toward tech or metals at the extremes.")
        cap = bc[2].slider("Max per ticker", 0.10, 0.50,
                           float(alloc_settings.get("max_weight", 0.30)), 0.05)

        if st.button("Compute allocation", type="primary"):
            with st.spinner("Reading tech health (SOXX + QQQ) and correlations…"):
                health = ae.tech_health()
                rets = ae.fetch_returns(held, period="6mo")
                targets = ae.compute_targets(held, rets, health=health,
                                             base_tech_share=base_tech,
                                             max_tilt=max_tilt, max_weight=cap)
            for t in held:
                etfs[t]["target_pct"] = targets[t]["target_pct"]
            data["alloc_settings"] = {"base_tech_share": base_tech,
                                      "max_tilt": max_tilt, "max_weight": cap}
            persist()

            meta = targets["_meta"]
            hh = meta["tech_health"]
            # Tech-health gauge
            g = st.columns(4)
            g[0].metric("Tech Health", hh["label"], delta=f"{hh['score']*100:.0f}/100")
            g[1].metric("Semis (SOXX)", f"{hh['soxx']*100:.0f}/100")
            g[2].metric("Nasdaq (QQQ)", f"{hh['qqq']*100:.0f}/100")
            g[3].metric("Tech / Metals split",
                        f"{meta['tech_share']*100:.0f}% / {meta['metal_share']*100:.0f}%")

            rows = []
            for t in sorted(held, key=lambda x: -targets[x]["target_pct"]):
                v = targets[t]
                cur_val = float(etfs[t]["shares"]) * prices.get(t, 0)
                cur_w = cur_val / gross_value * 100 if gross_value > 0 else 0
                rows.append({
                    "Ticker": t,
                    "Sleeve": v["sleeve"],
                    "Target %": f"{v['target_pct']*100:.1f}%",
                    "Current %": f"{cur_w:.1f}%",
                    "Drift": f"{cur_w - v['target_pct']*100:+.1f}%",
                    "Vol": f"{v['vol']*100:.0f}%" if v["vol"] else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.success("Targets saved. Negative 'Drift' = underweight = buy more. "
                       "Re-run weekly; as tech health changes, the tech/metals split rotates.")

st.markdown("**Reinvest premium toward target**")
rc = st.columns([1, 3])
with rc[0]:
    cash_invest = st.number_input("Cash to deploy ($)", 0.0, step=500.0, key="reinvest_cash")
if cash_invest > 0:
    held = [t for t in etfs if float(etfs[t]["shares"]) > 0]
    tw = {t: float(etfs[t].get("target_pct", 0)) for t in held}
    tw_sum = sum(tw.values())
    if tw_sum > 0:
        tw = {t: tw[t]/tw_sum for t in tw}   # normalize in case stored targets are off
        cur_vals = {t: float(etfs[t]["shares"]) * prices.get(t, 0) for t in held}
        plan = ae.reinvestment_plan(cur_vals, tw, cash_invest)
        plan_rows = [{"Ticker": t, "Buy $": f"${amt:,.0f}",
                      "≈ Shares": f"{amt/prices.get(t,1):.1f}" if prices.get(t,0) else "—"}
                     for t, amt in sorted(plan.items(), key=lambda x: -x[1]) if amt > 0]
        st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)
        st.caption("Buys the most underweight positions first to move you toward target. "
                   "Never suggests selling. Deploys the full amount.")
    else:
        st.info("Compute a target allocation first (above).")

st.divider()

# ---------------------------------------------------------------------------
# CHARTS
# ---------------------------------------------------------------------------
cc = st.columns(2)
with cc[0]:
    st.subheader("Monthly Premium vs Goal")
    if monthly_premiums:
        dfm = pd.DataFrame(sorted(monthly_premiums.items()), columns=["month", "premium"])
        fig = go.Figure()
        fig.add_trace(go.Bar(x=dfm["month"], y=dfm["premium"], marker_color="#3b82f6",
                             name="Premium"))
        fig.add_hline(y=PREMIUM_TARGET_MONTHLY, line_dash="dash", line_color="#ef4444",
                      annotation_text="$100K goal")
        fig.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#e6edf3", yaxis_title="$")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Record premium income to see this chart.")

with cc[1]:
    st.subheader("Net Equity Growth")
    if history:
        dfh = pd.DataFrame(history)
        dfh["date"] = pd.to_datetime(dfh["date"], errors="coerce")
        dfh = dfh.dropna(subset=["date"]).sort_values("date")
        if not dfh.empty:
            dfh["net"] = dfh["portfolio_value"].fillna(0) - dfh.get("margin_debt", 0).fillna(0)
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=dfh["date"], y=dfh["portfolio_value"],
                                      name="Gross", line=dict(color="#8b97a8")))
            fig2.add_trace(go.Scatter(x=dfh["date"], y=dfh["net"],
                                      name="Net", line=dict(color="#22c55e")))
            fig2.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#e6edf3")
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("History will appear as you record activity.")


# ===========================================================================
# SIDEBAR — all management tools (declutters main view)
# ===========================================================================
def persist():
    save_version(username, {
        "etfs": etfs, "history": history, "initial_capital": initial_capital,
        "capital_additions": capital_additions, "option_trades": option_trades,
        "cash_balance": cash_balance, "open_options": open_options,
        "alloc_settings": alloc_settings,
    })

sb = st.sidebar
sb.header(f"⚙️ Manage · {username}")

with sb.expander("💵 Capital · Margin · Cash"):
    if initial_capital <= 0:
        ic = st.number_input("Set initial capital ($)", 0.0, step=1000.0)
        if st.button("Set capital") and ic > 0:
            data["initial_capital"] = float(ic)
            history.append({"date": datetime.now().strftime("%Y-%m-%d"),
                            "portfolio_value": gross_value, "margin_debt": margin,
                            "premium": 0, "note": "Initial capital set"})
            persist(); st.rerun()
    add_cap = st.number_input("Add capital ($)", 0.0, step=1000.0)
    if st.button("Add capital") and add_cap > 0:
        capital_additions.append({"date": datetime.now().strftime("%Y-%m-%d"),
                                  "amount": float(add_cap)})
        data["cash_balance"] = cash_balance + add_cap
        history.append({"date": datetime.now().strftime("%Y-%m-%d"),
                        "portfolio_value": gross_value, "margin_debt": margin, "premium": 0})
        persist(); st.rerun()
    new_margin = st.number_input("Set margin debt ($)", 0.0, value=float(margin), step=100.0)
    if st.button("Update margin"):
        history.append({"date": datetime.now().strftime("%Y-%m-%d"),
                        "portfolio_value": gross_value, "margin_debt": float(new_margin),
                        "premium": 0})
        persist(); st.rerun()
    new_cash = st.number_input("Set cash ($)", 0.0, value=float(cash_balance), step=100.0)
    if st.button("Update cash"):
        data["cash_balance"] = float(new_cash); persist(); st.rerun()

with sb.expander("📈 Buy / Sell Shares"):
    bt = st.selectbox("Ticker", list(etfs.keys()), key="buy_t")
    bs = st.number_input("Shares", 0.0, step=1.0, key="buy_s")
    bp = st.number_input("Price", 0.0, step=0.01, key="buy_p")
    if st.button("Add purchase") and bs > 0 and bp > 0:
        old = etfs[bt]; ns = float(old["shares"]) + bs
        etfs[bt]["cost_basis"] = ((float(old["shares"])*float(old["cost_basis"]) + bs*bp)/ns
                                  if ns > 0 else bp)
        etfs[bt]["shares"] = ns
        persist(); st.rerun()
    sst = st.selectbox("Ticker ", list(etfs.keys()), key="sell_t")
    ss = st.number_input("Shares to sell", 0.0, step=1.0, key="sell_s")
    if st.button("Sell shares") and ss > 0:
        cur = float(etfs[sst]["shares"])
        if ss > cur:
            st.error(f"Only {cur:.2f} owned.")
        else:
            etfs[sst]["shares"] = cur - ss
            if cur - ss <= 0:
                etfs[sst]["cost_basis"] = 0.0
            persist(); st.rerun()

with sb.expander("💰 Record Premium"):
    prem = st.number_input("Premium received ($)", 0.0, step=10.0)
    if st.button("Record premium") and prem > 0:
        history.append({"date": datetime.now().strftime("%Y-%m-%d"), "premium": float(prem),
                        "portfolio_value": gross_value, "margin_debt": margin})
        persist(); st.rerun()

with sb.expander("🛡️ Add / Close Option"):
    ot = st.selectbox("Ticker", list(etfs.keys()), key="opt_t")
    oc = st.number_input("Contracts", 0, step=1, value=1, key="opt_c")
    osk = st.number_input("Strike", 0.0, step=0.5, key="opt_k")
    op = st.number_input("Premium/contract", 0.0, step=0.05, key="opt_p")
    oe = st.date_input("Expiry", date.today()+timedelta(days=7), key="opt_e")
    if st.button("Add option") and oc > 0 and osk > 0:
        open_options.append({"id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                             "ticker": ot, "contracts": int(oc), "strike": float(osk),
                             "expiry": oe.strftime("%Y-%m-%d"),
                             "sold_date": date.today().strftime("%Y-%m-%d"),
                             "premium_per": float(op)})
        persist(); st.rerun()
    if open_options:
        labels = [f"{o['ticker']} {o['contracts']}c ${o['strike']:.0f} {o['expiry']}"
                  for o in open_options]
        idx = st.selectbox("Select position", range(len(open_options)),
                           format_func=lambda i: labels[i])
        sel = open_options[idx]
        # Edit fields (fixes legacy $0 premiums without delete+re-add)
        ep = st.number_input("Edit premium/contract", 0.0, value=float(sel.get("premium_per", 0)),
                             step=0.05, key="edit_prem")
        ek = st.number_input("Edit strike", 0.0, value=float(sel.get("strike", 0)),
                             step=0.5, key="edit_strike")
        c_edit, c_close = st.columns(2)
        with c_edit:
            if st.button("Save edits"):
                sel["premium_per"] = float(ep)
                sel["strike"] = float(ek)
                persist(); st.rerun()
        with c_close:
            if st.button("Close position"):
                open_options.pop(idx); persist(); st.rerun()

with sb.expander("💾 Backup / Restore"):
    backup = json.dumps({**data, "username": username,
                         "timestamp": datetime.now().isoformat()}, indent=2)
    st.download_button("⬇️ Download backup", backup,
                       file_name=f"wealthgrowth_{username}_{datetime.now():%Y%m%d_%H%M}.json",
                       mime="application/json")
    up = st.file_uploader("Restore from backup", type=["json"])
    if up and st.button("Restore (overwrites)", type="primary"):
        try:
            restored = _normalize(json.load(up))
            save_version(username, restored)
            st.cache_data.clear(); st.success("Restored."); st.rerun()
        except Exception as e:
            st.error(f"Bad file: {e}")

with sb.expander("🚪 Account"):
    if st.button("Sign out"):
        st.session_state.username = ""; st.rerun()

st.caption("Volatility-based strikes · live assignment probabilities · "
           "data via yfinance. Analytical aid, not financial advice.")

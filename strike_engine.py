"""
strike_engine.py — Volatility-based strike selection for your covered-call app.

DROP-IN UPGRADE for "Option.py". Replaces the fixed-percentage OTM logic
(otm_pct = 0.14 etc.) with strikes sized by each ticker's ACTUAL volatility,
and adds real assignment-probability (ProbITM) and delta columns.

Why: a fixed "14% OTM" means totally different risk when a stock is calm vs.
swinging 10%/week. Sizing by volatility is what stops weekly calls from going
ITM unexpectedly.

USAGE in your Streamlit app:
    from strike_engine import (
        realized_vol_for, suggest_strike, prob_itm, enrich_option_row,
        trend_strength_for
    )

    # Replace the old fixed-otm block with:
    rv = realized_vol_for(ticker)                      # annualized vol
    sugg = suggest_strike(current_price, rv, days_to_expiry, target_prob=0.20)
    # sugg = {'strike', 'pct_otm', 'prob_itm', 'sds_otm'}

No API key needed — uses yfinance (which your app already uses) for history.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Dict, Optional

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False


# ---------------------------------------------------------------------------
# Normal distribution (no scipy)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Volatility — cached per ticker per day
# ---------------------------------------------------------------------------

_vol_cache: Dict[str, tuple] = {}   # ticker -> (date, vol)

def realized_vol_for(ticker: str, window: int = 30) -> Optional[float]:
    """
    Annualized realized volatility from recent daily closes (fraction).
    Cached once per day per ticker. Returns None if data unavailable.
    """
    today = dt.date.today()
    if ticker in _vol_cache and _vol_cache[ticker][0] == today:
        return _vol_cache[ticker][1]
    if not _HAS_YF:
        return None
    try:
        hist = yf.Ticker(ticker).history(period="3mo", interval="1d")
        closes = list(hist["Close"].dropna())
        if len(closes) < window + 1:
            window = max(10, len(closes) - 1)
        rets = []
        for i in range(-window, 0):
            if closes[i-1] > 0:
                rets.append(math.log(closes[i] / closes[i-1]))
        if len(rets) < 2:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        vol = math.sqrt(var) * math.sqrt(252)
        _vol_cache[ticker] = (today, vol)
        return vol
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Options math
# ---------------------------------------------------------------------------

def _d2(spot, strike, t_years, vol, r=0.04):
    if t_years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return None
    d1 = (math.log(spot/strike) + (r + 0.5*vol**2)*t_years) / (vol*math.sqrt(t_years))
    return d1 - vol*math.sqrt(t_years)


def prob_itm(spot, strike, days_to_expiry, vol, r=0.04) -> Optional[float]:
    """Probability the call finishes ITM (≈ assignment probability), 0..1."""
    t = days_to_expiry / 365.0
    d2 = _d2(spot, strike, t, vol, r)
    return _norm_cdf(d2) if d2 is not None else None


def call_delta(spot, strike, days_to_expiry, vol, r=0.04) -> Optional[float]:
    """Black-Scholes call delta (≈ what Robinhood shows)."""
    t = days_to_expiry / 365.0
    if t <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return None
    d1 = (math.log(spot/strike) + (r + 0.5*vol**2)*t) / (vol*math.sqrt(t))
    return _norm_cdf(d1)


def sds_otm(spot, strike, days_to_expiry, vol) -> Optional[float]:
    """How many standard deviations OTM the strike is for this expiry."""
    t = days_to_expiry / 365.0
    if t <= 0 or vol <= 0:
        return None
    sigma_move = spot * vol * math.sqrt(t)
    return (strike - spot) / sigma_move if sigma_move else None


# ---------------------------------------------------------------------------
# Strike suggestion — by target assignment probability
# ---------------------------------------------------------------------------

def suggest_strike(spot: float, vol: float, days_to_expiry: int,
                   target_prob: float = 0.20) -> dict:
    """
    Suggest a strike whose assignment probability ≈ target_prob.
    Solves for the strike that gives the desired prob_itm.

    target_prob: desired assignment odds (0.20 = 20%). Lower = safer/farther.
    Returns {'strike', 'pct_otm', 'prob_itm', 'sds_otm'}.
    """
    if not spot or not vol or days_to_expiry <= 0:
        # Fallback to a mild fixed OTM if we can't compute
        strike = round(spot * 1.05, 1) if spot else 0
        return {"strike": strike, "pct_otm": 5.0, "prob_itm": None, "sds_otm": None}

    t = days_to_expiry / 365.0
    # Invert N(d2)=target_prob → d2 = Φ⁻¹(target_prob)
    # Φ⁻¹ via rational approximation (Acklam) — good enough here
    z = _inv_norm_cdf(target_prob)
    # d2 = (ln(S/K) + (r-0.5σ²)t) / (σ√t) = z  → solve for K
    r = 0.04
    K = spot * math.exp(-(z * vol * math.sqrt(t)) + (r - 0.5*vol**2)*t)
    K = round(K, 1)
    return {
        "strike": K,
        "pct_otm": round((K/spot - 1) * 100, 1),
        "prob_itm": round(target_prob * 100, 1),
        "sds_otm": round(sds_otm(spot, K, days_to_expiry, vol), 2),
    }


def _inv_norm_cdf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's algorithm)."""
    if p <= 0: return -10.0
    if p >= 1: return 10.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2*math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2*math.log(1-p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5; rr = q*q
    return (((((a[0]*rr+a[1])*rr+a[2])*rr+a[3])*rr+a[4])*rr+a[5])*q / \
           (((((b[0]*rr+b[1])*rr+b[2])*rr+b[3])*rr+b[4])*rr+1)


# ---------------------------------------------------------------------------
# Trend strength (for strike-width guidance)
# ---------------------------------------------------------------------------

def trend_strength_for(ticker: str) -> Optional[dict]:
    """Returns {'score':0-100, 'label':str} or None."""
    if not _HAS_YF:
        return None
    try:
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        closes = list(hist["Close"].dropna())
        if len(closes) < 210:
            return None
        price = closes[-1]
        ma200 = sum(closes[-200:]) / 200
        ma50 = sum(closes[-50:]) / 50
        ma50_prev = sum(closes[-60:-10]) / 50
        mom = price / closes[-21] - 1
        c_long = 50 + max(min((price/ma200-1)*200, 50), -50)
        c_slope = 50 + max(min((ma50/ma50_prev-1)*1000, 50), -50)
        c_short = 50 + max(min((price/ma50-1)*400, 50), -50)
        c_mom = 50 + max(min(mom*300, 50), -50)
        score = (c_long + c_slope + c_short + c_mom) / 4
        if score >= 70:   label = "Strong uptrend"
        elif score >= 55: label = "Moderate uptrend"
        elif score >= 45: label = "Flat / choppy"
        elif score >= 30: label = "Weakening"
        else:             label = "Downtrend"
        return {"score": round(score, 1), "label": label}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Convenience: enrich an open-option row with risk columns
# ---------------------------------------------------------------------------

def enrich_option_row(opt: dict, spot: float) -> dict:
    """
    Given one of your open_options dicts + current spot, return the extra
    risk columns to add to your options table.
    """
    try:
        expiry = dt.datetime.strptime(opt["expiry"], "%Y-%m-%d").date()
        dte = max((expiry - dt.date.today()).days, 0)
    except Exception:
        dte = 0
    vol = realized_vol_for(opt["ticker"]) or 0.5
    strike = opt.get("strike", 0)
    p = prob_itm(spot, strike, dte, vol) if (spot and strike and dte) else None
    d = call_delta(spot, strike, dte, vol) if (spot and strike and dte) else None
    return {
        "Assignment Prob": f"{p*100:.0f}%" if p is not None else "-",
        "Delta": f"{d:.2f}" if d is not None else "-",
        "Vol (ann)": f"{vol*100:.0f}%" if vol else "-",
    }

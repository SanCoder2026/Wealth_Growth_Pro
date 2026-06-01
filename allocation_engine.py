"""
allocation_engine.py — Regime-based tech<->metals rotation (data-driven only).

The framework you described:
  - Tech strong   -> tilt toward leveraged tech (premium + growth)
  - Tech weakening-> rotate toward metals (where safe-haven money flows)

NO subjective inputs. Everything is computed:
  1. TECH HEALTH  : blended trend of semis (SOXX) + Nasdaq (QQQ), 0..1
  2. SLEEVE SPLIT : gradual tilt between tech sleeve and metals sleeve based on
                    tech health (smooth, not stepped)
  3. WITHIN SLEEVE: weights set by premium-yield (volatility) + diversification
                    (low correlation to the rest)
  4. CAP + NORMALIZE: no ticker exceeds max_weight; total = 100%
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

try:
    import yfinance as yf
    _HAS = True
except ImportError:
    _HAS = False


# ---------------------------------------------------------------------------
# Sleeve classification
# ---------------------------------------------------------------------------

TECH_TICKERS   = {"SOXL", "TQQQ", "UPRO", "SNPS", "SOXX", "QQQ", "TECL", "NVDA",
                  "USD", "FNGU"}
METAL_TICKERS  = {"SLV", "IAU", "GLD", "COPX", "URA", "UAMY", "GDX", "SIL",
                  "CPER", "PALL", "PPLT", "STLD"}

def classify_sleeve(ticker: str) -> str:
    t = ticker.upper()
    if t in TECH_TICKERS:
        return "tech"
    if t in METAL_TICKERS:
        return "metals"
    return "other"


# ---------------------------------------------------------------------------
# Returns / stats helpers
# ---------------------------------------------------------------------------

def _daily_returns(closes: List[float]) -> List[float]:
    return [closes[i]/closes[i-1] - 1 for i in range(1, len(closes)) if closes[i-1] > 0]


def fetch_returns(tickers: List[str], period="6mo") -> Dict[str, List[float]]:
    if not _HAS:
        return {}
    series = {}
    for t in tickers:
        try:
            h = yf.Ticker(t).history(period=period, interval="1d")
            r = _daily_returns(list(h["Close"].dropna()))
            if len(r) > 20:
                series[t] = r
        except Exception:
            continue
    if series:
        n = min(len(v) for v in series.values())
        series = {t: v[-n:] for t, v in series.items()}
    return series


def _vol(r: List[float]) -> float:
    if len(r) < 2:
        return 0.0
    m = sum(r)/len(r)
    return math.sqrt(sum((x-m)**2 for x in r)/(len(r)-1)) * math.sqrt(252)


def _corr(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a)/n, sum(b)/n
    cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n))/n
    sa = math.sqrt(sum((x-ma)**2 for x in a)/n)
    sb = math.sqrt(sum((x-mb)**2 for x in b)/n)
    return cov/(sa*sb) if sa and sb else 0.0


# ---------------------------------------------------------------------------
# 1. TECH HEALTH - blended semis + Nasdaq trend, 0..1
# ---------------------------------------------------------------------------

def tech_health(semis="SOXX", nasdaq="QQQ") -> Dict[str, float]:
    """
    Returns {'score': 0..1, 'soxx': 0..1, 'qqq': 0..1, 'label': str}.
    1.0 = very strong tech trend, 0.0 = very weak. Uses price vs 50/200-day MAs
    and 50-day slope, blended 50/50 between semis and Nasdaq.
    """
    def one(sym):
        if not _HAS:
            return 0.5
        try:
            h = yf.Ticker(sym).history(period="1y", interval="1d")
            c = list(h["Close"].dropna())
            if len(c) < 210:
                return 0.5
            price = c[-1]
            ma50 = sum(c[-50:]) / 50
            ma200 = sum(c[-200:]) / 200
            ma50_prev = sum(c[-60:-10]) / 50
            above200 = 0.5 + max(min((price/ma200 - 1) * 2.0, 0.5), -0.5)
            above50  = 0.5 + max(min((price/ma50 - 1) * 4.0, 0.5), -0.5)
            slope    = 0.5 + max(min((ma50/ma50_prev - 1) * 10.0, 0.5), -0.5)
            return (above200 + above50 + slope) / 3
        except Exception:
            return 0.5

    s = one(semis)
    q = one(nasdaq)
    score = (s + q) / 2
    if score >= 0.70:   label = "Tech strong"
    elif score >= 0.55: label = "Tech firm"
    elif score >= 0.45: label = "Neutral"
    elif score >= 0.30: label = "Tech weakening"
    else:               label = "Tech weak"
    return {"score": round(score, 3), "soxx": round(s, 3),
            "qqq": round(q, 3), "label": label}


# ---------------------------------------------------------------------------
# Within-sleeve scores (premium-yield + diversification)
# ---------------------------------------------------------------------------

def _within_sleeve_weights(tickers: List[str], returns: Dict[str, List[float]],
                           w_premium=0.5, w_div=0.5) -> Dict[str, float]:
    if not tickers:
        return {}
    vols = {t: _vol(returns.get(t, [])) for t in tickers}
    vmax = max(vols.values()) if vols else 1.0
    vmin = min(vols.values()) if vols else 0.0
    vr = (vmax - vmin) or 1.0
    raw = {}
    for t in tickers:
        prem = (vols[t] - vmin) / vr
        others = [t2 for t2 in returns if t2 != t]
        if others and t in returns:
            ac = sum(_corr(returns[t], returns[o]) for o in others) / len(others)
        else:
            ac = 0.0
        div = max(0.0, min(1.0, (1 - ac) / 2))
        raw[t] = max(w_premium * prem + w_div * div, 0.0001)
    tot = sum(raw.values()) or 1.0
    return {t: raw[t] / tot for t in tickers}


# ---------------------------------------------------------------------------
# Main: regime-based target allocation
# ---------------------------------------------------------------------------

def compute_targets(
    tickers: List[str],
    returns: Dict[str, List[float]] = None,
    health: Dict[str, float] = None,
    base_tech_share: float = 0.50,
    max_tilt: float = 0.30,
    max_weight: float = 0.30,
    w_premium: float = 0.5,
    w_div: float = 0.5,
) -> Dict[str, dict]:
    returns = returns or {}
    health = health or {"score": 0.5}
    h = health["score"]

    sleeves = {"tech": [], "metals": [], "other": []}
    for t in tickers:
        sleeves[classify_sleeve(t)].append(t)

    have_tech = bool(sleeves["tech"])
    have_metal = bool(sleeves["metals"])

    if have_tech and have_metal:
        tech_share = base_tech_share + (h - 0.5) * 2 * max_tilt
        tech_share = max(0.10, min(0.90, tech_share))
        metal_share = 1.0 - tech_share
    elif have_tech:
        tech_share, metal_share = 1.0, 0.0
    elif have_metal:
        tech_share, metal_share = 0.0, 1.0
    else:
        tech_share, metal_share = 0.0, 0.0

    other_share = 0.0
    if sleeves["other"]:
        other_share = min(0.20, 0.05 * len(sleeves["other"]))
        scale = 1.0 - other_share
        tech_share *= scale
        metal_share *= scale

    tech_w  = _within_sleeve_weights(sleeves["tech"], returns, w_premium, w_div)
    metal_w = _within_sleeve_weights(sleeves["metals"], returns, w_premium, w_div)
    other_w = _within_sleeve_weights(sleeves["other"], returns, w_premium, w_div)

    raw = {}
    for t in sleeves["tech"]:
        raw[t] = tech_share * tech_w[t]
    for t in sleeves["metals"]:
        raw[t] = metal_share * metal_w[t]
    for t in sleeves["other"]:
        raw[t] = other_share * other_w[t]

    weights = _normalize_with_cap(raw, max_weight)

    out = {}
    for t in tickers:
        sleeve = classify_sleeve(t)
        v = _vol(returns.get(t, []))
        out[t] = {
            "target_pct": round(weights.get(t, 0), 4),
            "sleeve": sleeve,
            "vol": round(v, 3),
        }
    out["_meta"] = {
        "tech_health": health,
        "tech_share": round(tech_share, 3),
        "metal_share": round(metal_share, 3),
        "other_share": round(other_share, 3),
    }
    return out


def _normalize_with_cap(raw: Dict[str, float], cap: float) -> Dict[str, float]:
    tickers = list(raw.keys())
    total = sum(raw.values()) or 1.0
    w = {t: raw[t]/total for t in tickers}
    for _ in range(50):
        over = {t for t in tickers if w[t] > cap + 1e-9}
        if not over:
            break
        capped = len(over) * cap
        remaining = 1.0 - capped
        free = [t for t in tickers if t not in over]
        fsum = sum(raw[t] for t in free) or 1.0
        for t in over:
            w[t] = cap
        for t in free:
            w[t] = remaining * (raw[t]/fsum)
    return w


def reinvestment_plan(current_values: Dict[str, float],
                      targets: Dict[str, float],
                      cash_to_invest: float) -> Dict[str, float]:
    """Allocate cash to the most underweight positions. Never sells."""
    total_now = sum(current_values.values()) + cash_to_invest
    desired = {t: targets.get(t, 0) * total_now for t in targets}
    shortfall = {t: max(0.0, desired[t] - current_values.get(t, 0)) for t in targets}
    ts = sum(shortfall.values())
    if ts <= 0:
        return {t: round(cash_to_invest * targets.get(t, 0), 2) for t in targets}
    return {t: round(cash_to_invest * shortfall[t]/ts, 2)
            for t in targets if shortfall[t] > 0}

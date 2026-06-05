import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
fetch_tv_tickers.py
--------------------
Fetches ATH + 52-week high movers for ASX and US from TradingView's
internal Scanner API. Saves ticker lists to cache/.

Usage (standalone):  python fetch_tv_tickers.py
Usage (imported):    from fetch_tv_tickers import fetch_all_tv_tickers
"""

import requests, time, logging, os
from typing import List, Tuple
import paths

log = logging.getLogger(__name__)

SCANNER_BASE    = "https://scanner.tradingview.com/{market}/scan"
SCAN_LIMIT      = 200
REQUEST_TIMEOUT = 20
DELAY_BETWEEN   = 2.0
ATH_PCT         = 0.10
HIGH_52W_PCT    = 0.05

SUFFIX_MAP = {"australia": ".AX", "america": ""}

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
    "Referer":      "https://www.tradingview.com/",
    "Origin":       "https://www.tradingview.com",
}


def _payload(limit=SCAN_LIMIT) -> dict:
    return {
        "filter": [
            {"left": "close",  "operation": "egreater", "right": 0},
            {"left": "volume", "operation": "egreater", "right": 0},
        ],
        "options": {"lang": "en"},
        "columns": ["name", "close", "High.All", "price_52_week_high", "volume"],
        "sort":    {"sortBy": "volume", "sortOrder": "desc"},
        "range":   [0, limit],
    }


def _fetch_scanner(market: str) -> List[dict]:
    url = SCANNER_BASE.format(market=market)
    try:
        resp = requests.post(url, json=_payload(), headers=HEADERS,
                             timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            log.warning(f"Scanner [{market}]: HTTP {resp.status_code} — {resp.text[:200]}")
            return []
        data = resp.json()
    except requests.RequestException as e:
        log.warning(f"Scanner [{market}]: {e}")
        return []

    rows = []
    for item in data.get("data", []):
        sym = item.get("s", "").split(":")[-1]
        d   = item.get("d", [])
        try:
            rows.append({
                "symbol":  sym,
                "close":   float(d[1]) if len(d) > 1 and d[1] else 0,
                "ath":     float(d[2]) if len(d) > 2 and d[2] else 0,
                "high_1y": float(d[3]) if len(d) > 3 and d[3] else 0,
            })
        except (TypeError, ValueError):
            continue

    log.info(f"  Scanner [{market}]: {len(rows)} stocks")
    return rows


def _filter(rows: List[dict]) -> List[str]:
    passed = []
    for r in rows:
        c, ath, h1y = r["close"], r["ath"], r["high_1y"]
        if c <= 0:
            continue
        if (ath   > 0 and c >= ath   * (1 - ATH_PCT))  or \
           (h1y   > 0 and c >= h1y   * (1 - HIGH_52W_PCT)):
            passed.append(r["symbol"])
    return passed


def _add_suffix(symbols: List[str], market: str) -> List[str]:
    suffix = SUFFIX_MAP.get(market, "")
    return [s + suffix if suffix and not s.endswith(suffix) else s
            for s in symbols]


def _dedup(symbols: List[str]) -> List[str]:
    seen, out = set(), []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_market_tickers(market: str) -> List[str]:
    log.info(f"[TV] Fetching {market.upper()} stocks...")
    rows     = _fetch_scanner(market)
    time.sleep(DELAY_BETWEEN)
    filtered = _filter(rows)
    tickers  = _add_suffix(_dedup(filtered), market)
    log.info(f"[TV] {market.upper()}: {len(tickers)} unique tickers after filter")
    return tickers


def fetch_all_tv_tickers() -> Tuple[List[str], List[str]]:
    """Returns (asx_tickers, us_tickers)."""
    paths.ensure_dirs()
    asx = fetch_market_tickers("australia")
    us  = fetch_market_tickers("america")

    # Save to cache/
    with open(paths.TV_ASX_TICKERS, "w") as f:
        f.write("\n".join(asx))
    with open(paths.TV_US_TICKERS, "w") as f:
        f.write("\n".join(us))

    return asx, us


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s",
                        datefmt="%H:%M:%S")
    print("=" * 55)
    print("TradingView Market Movers — Ticker Fetch")
    print(f"ATH: within {ATH_PCT*100:.0f}%   52W: within {HIGH_52W_PCT*100:.0f}%")
    print("=" * 55)

    asx, us = fetch_all_tv_tickers()

    print(f"\nASX ({len(asx)}):")
    for t in asx[:30]: print(f"  {t}")
    if len(asx) > 30:  print(f"  ... +{len(asx)-30} more")

    print(f"\nUS ({len(us)}):")
    for t in us[:30]:  print(f"  {t}")
    if len(us) > 30:   print(f"  ... +{len(us)-30} more")

    print(f"\nSaved → {paths.TV_ASX_TICKERS}")
    print(f"Saved → {paths.TV_US_TICKERS}")

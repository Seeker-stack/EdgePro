import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
paths.py
--------
Central path configuration for Edge Pro.
All scripts import from here — change paths in one place only.
"""

import os

# ── Root ──────────────────────────────────────────────────────────────────────
ROOT = str(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # resolves to C:\StockData regardless of location

# ── Data subdirectories ───────────────────────────────────────────────────────
DATA_DIR  = os.path.join(ROOT,     "data")
NSE_DIR   = os.path.join(DATA_DIR, "nse")
ASX_DIR   = os.path.join(DATA_DIR, "asx")
US_DIR    = os.path.join(DATA_DIR, "us")
BENCH_DIR = os.path.join(DATA_DIR, "benchmarks")

# ── Output directories ────────────────────────────────────────────────────────
SCREENER_DIR = os.path.join(ROOT, "screeners")
CACHE_DIR    = os.path.join(ROOT, "cache")
LOG_DIR      = os.path.join(ROOT, "logs")
EXPORT_DIR   = os.path.join(ROOT, "exports")
SCRIPTS_DIR  = os.path.join(ROOT, "scripts")

# ── Key files ─────────────────────────────────────────────────────────────────
TICKER_FILE    = os.path.join(ROOT,      "Tickers.txt")
SUMMARY_FILE   = os.path.join(CACHE_DIR, "last_run_summary.txt")
SECTOR_CACHE   = os.path.join(CACHE_DIR, "sector_cache.json")
TV_ASX_TICKERS = os.path.join(CACHE_DIR, "tv_asx_tickers.txt")
TV_US_TICKERS  = os.path.join(CACHE_DIR, "tv_us_tickers.txt")

# ── Screener CSVs ─────────────────────────────────────────────────────────────
TV_NSE_CSV = os.path.join(SCREENER_DIR, "TradingView_NSE.csv")
TV_ASX_CSV = os.path.join(SCREENER_DIR, "TradingView_ASX.csv")
TV_US_CSV  = os.path.join(SCREENER_DIR, "TradingView_US.csv")

# ── All data directories (used when scanning all markets) ─────────────────────
ALL_DATA_DIRS = [NSE_DIR, ASX_DIR, US_DIR]

# ── Helpers ───────────────────────────────────────────────────────────────────

def market_dir(ticker: str) -> str:
    """Return the correct data subdirectory for a ticker symbol."""
    if ticker.endswith((".NS", ".BO")): return NSE_DIR
    if ticker.endswith(".AX"):          return ASX_DIR
    return US_DIR


def ticker_market(ticker: str) -> str:
    """Return market string for a ticker: 'NSE', 'ASX', or 'US'."""
    if ticker.endswith((".NS", ".BO")): return "NSE"
    if ticker.endswith(".AX"):          return "ASX"
    return "US"


def ensure_dirs():
    """Create all required directories (safe to call multiple times)."""
    for d in [DATA_DIR, NSE_DIR, ASX_DIR, US_DIR, BENCH_DIR,
              SCREENER_DIR, CACHE_DIR, LOG_DIR, EXPORT_DIR, SCRIPTS_DIR]:
        os.makedirs(d, exist_ok=True)

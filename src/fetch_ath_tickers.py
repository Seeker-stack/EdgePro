import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
fetch_ath_tickers.py
--------------------
Scrapes TradingView ATH pages for ASX, NSE (India), and US stocks
and updates C:\\StockData\\Tickers.txt with the latest ATH tickers.

- Preserves any manually added tickers already in the file
- Adds new ATH tickers with .AX / .NS / no suffix as appropriate
- Removes duplicates
- Logs what was added / already present

Usage:
    uv run fetch_ath_tickers.py

Schedule alongside nightly_download.py — run this first, then
nightly_download.py will download data for the updated list.
"""

import os
import re
import time
import logging
from datetime import date

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

TICKERS_FILE = r"C:\StockData\Tickers.txt"
LOG_DIR      = r"C:\StockData\logs"
os.makedirs(LOG_DIR, exist_ok=True)

# TradingView ATH pages to scrape
# Each entry: (url, suffix_to_add, market_label)
ATH_PAGES = [
    (
        "https://www.tradingview.com/markets/stocks-australia/market-movers-ath/",
        ".AX",
        "ASX"
    ),
    (
        "https://www.tradingview.com/markets/stocks-india/market-movers-ath/",
        ".NS",
        "NSE India"
    ),
    (
        "https://www.tradingview.com/markets/stocks-usa/market-movers-ath/",
        "",
        "US"
    ),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DELAY = 2.0   # seconds between page requests — be polite

# ── Logging ───────────────────────────────────────────────────────────────────

log_path = os.path.join(LOG_DIR, f"fetch_ath_{date.today().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_existing_tickers() -> list[str]:
    """Read Tickers.txt preserving comments and blank lines."""
    if not os.path.exists(TICKERS_FILE):
        return []
    with open(TICKERS_FILE, "r") as f:
        return [line.rstrip("\n") for line in f]


def extract_tickers_from_symbol_links(soup: BeautifulSoup) -> list[str]:
    """
    TradingView renders symbol cells as links like:
        /symbols/ASX-BHP/  or  /symbols/NSE-RELIANCE/  or  /symbols/NASDAQ-AAPL/
    We extract the ticker part after the exchange dash.
    """
    tickers = []
    # Match all anchor hrefs pointing to /symbols/EXCHANGE-TICKER/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.match(r"^/symbols/[A-Z0-9]+-([A-Z0-9&.]+)/?$", href)
        if m:
            sym = m.group(1).strip()
            if sym and len(sym) <= 10:   # sanity check — skip garbage
                tickers.append(sym)
    # Deduplicate preserving order
    seen = set()
    out  = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def scrape_page(url: str, suffix: str, label: str) -> list[str]:
    """Fetch one ATH page and return list of tickers with correct suffix."""
    log.info(f"Fetching {label} ATH page...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.error(f"  Failed to fetch {url}: {e}")
        return []

    soup    = BeautifulSoup(resp.text, "html.parser")
    symbols = extract_tickers_from_symbol_links(soup)

    if not symbols:
        log.warning(f"  No symbols found on {label} page — page structure may have changed")
        return []

    # Add exchange suffix
    result = [f"{sym}{suffix}" for sym in symbols]
    log.info(f"  Found {len(result)} tickers: {', '.join(result[:10])}"
             + (" ..." if len(result) > 10 else ""))
    return result


def update_tickers_file(new_tickers: list[str]) -> tuple[int, int]:
    """
    Merge new_tickers into existing Tickers.txt.
    Returns (added_count, already_present_count).
    """
    existing_lines = load_existing_tickers()

    # Collect all tickers already in file (strip comments)
    existing_set = set()
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            existing_set.add(stripped.upper())

    added   = []
    already = []
    for t in new_tickers:
        if t.upper() in existing_set:
            already.append(t)
        else:
            added.append(t)

    if not added:
        log.info("No new tickers to add — Tickers.txt already up to date.")
        return 0, len(already)

    # Append new tickers under a dated section header
    lines_to_add = [
        "",
        f"# ATH tickers auto-fetched from TradingView — {date.today()}",
    ] + added

    with open(TICKERS_FILE, "a", encoding="utf-8") as f:
        for line in lines_to_add:
            f.write(line + "\n")

    log.info(f"Added {len(added)} new tickers to {TICKERS_FILE}")
    return len(added), len(already)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info("fetch_ath_tickers.py — TradingView ATH scraper")
    log.info(f"Date: {date.today()}")
    log.info("=" * 55)

    all_new = []
    for url, suffix, label in ATH_PAGES:
        tickers = scrape_page(url, suffix, label)
        all_new.extend(tickers)
        time.sleep(DELAY)

    if not all_new:
        log.warning("No tickers scraped from any page. Exiting.")
        return

    # Deduplicate across markets
    seen = set()
    deduped = []
    for t in all_new:
        if t.upper() not in seen:
            seen.add(t.upper())
            deduped.append(t)

    log.info(f"\nTotal unique tickers scraped: {len(deduped)}")
    added, present = update_tickers_file(deduped)

    log.info("\n" + "=" * 55)
    log.info("SUMMARY")
    log.info(f"  Scraped   : {len(deduped)} unique tickers")
    log.info(f"  Added     : {added} new tickers → Tickers.txt")
    log.info(f"  Existing  : {present} already in file")
    log.info(f"  File      : {TICKERS_FILE}")
    log.info("=" * 55)
    log.info("Done. Run nightly_download.py next to fetch OHLCV data.")


if __name__ == "__main__":
    main()

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
nightly_download.py
-------------------
Edge Pro — Nightly batch downloader (production layout)

Folder layout after setup_folders.py:
  C:\StockData\data\nse\        ← NSE stock CSVs
  C:\StockData\data\asx\        ← ASX stock CSVs
  C:\StockData\data\us\         ← US stock CSVs
  C:\StockData\data\benchmarks\ ← Index benchmarks
  C:\StockData\screeners\       ← TradingView screener CSVs
  C:\StockData\cache\           ← Tickers, summary, sector cache
  C:\StockData\logs\            ← Nightly logs

Schedule via Windows Task Scheduler after market close.
"""

import os, time, logging, traceback
from datetime import datetime, date

import pandas as pd
import yfinance as yf
import ta

import paths
from fetch_tv_tickers import fetch_all_tv_tickers
from tradingview_client import TradingViewClient

# ── Configuration ─────────────────────────────────────────────────────────────

DOWNLOAD_PERIOD     = "1y"
DELAY_SECONDS       = 1.4
BENCH_DELAY         = 1.0
ATH_PCT             = 0.10      # within 10 % of all-time high
HIGH_52W_PCT        = 0.05      # within  5 % of 52-week high
MIN_ROWS            = 50
SKIP_IF_FRESH       = 20        # skip re-download if CSV modified < N hours ago

BENCHMARKS = {
    "NSEI":    "^NSEI",
    "NSEBANK": "^NSEBANK",
    "GSPC":    "^GSPC",
    "IXIC":    "^IXIC",
    "AXJO":    "^AXJO",
    "FTSE":    "^FTSE",
    "N225":    "^N225",
    "HSI":     "^HSI",
    "DXY":     "DX-Y.NYB",
    "BTCUSD":  "BTC-USD",
    "GOLD":    "GC=F",
    "SILVER":  "SI=F",
    "CRUDE":   "CL=F",
    "COPPER":  "HG=F",
    "NATGAS":  "NG=F",
}

# ── Logging setup ─────────────────────────────────────────────────────────────

paths.ensure_dirs()
log_file = os.path.join(paths.LOG_DIR, f"nightly_{date.today():%Y%m%d}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_tickers(path: str) -> list[str]:
    if not os.path.exists(path):
        log.error(f"Tickers.txt not found: {path}")
        return []
    tickers = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                tickers.append(line.upper())
    log.info(f"Loaded {len(tickers)} tickers from Tickers.txt")
    return tickers


def download_ticker(symbol: str, period: str = DOWNLOAD_PERIOD) -> pd.DataFrame | None:
    try:
        raw = yf.download(symbol, period=period, interval="1d",
                          progress=False, auto_adjust=True)
        if raw.empty:
            return None

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        raw = raw.reset_index()
        raw.columns = [c.strip() for c in raw.columns]
        col_map = {"Date": "Date", "Open": "OPEN", "High": "HIGH",
                   "Low": "LOW", "Close": "CLOSE", "Volume": "VOLUME"}
        raw = raw.rename(columns=col_map)
        needed = ["Date", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]
        if any(c not in raw.columns for c in needed):
            return None

        raw = raw[needed].copy()
        raw["Date"] = pd.to_datetime(raw["Date"])
        raw = raw.dropna(subset=["CLOSE"]).sort_values("Date").reset_index(drop=True)
        return raw if len(raw) >= MIN_ROWS else None

    except Exception as e:
        log.warning(f"{symbol}: download error — {e}")
        return None


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    try:
        df["RSI"]       = ta.momentum.RSIIndicator(df["CLOSE"], window=14).rsi()
        df["ADX"]       = ta.trend.ADXIndicator(df["HIGH"], df["LOW"], df["CLOSE"], window=14).adx()
        df["EMA21"]     = df["CLOSE"].ewm(span=21,  adjust=False).mean()
        df["EMA55"]     = df["CLOSE"].ewm(span=55,  adjust=False).mean()
        df["EMA150"]    = df["CLOSE"].ewm(span=150, adjust=False).mean()
        df["EMA200"]    = df["CLOSE"].ewm(span=200, adjust=False).mean()
        df["AvgVol20"]  = df["VOLUME"].rolling(20).mean()
        df["VolumeSpike"] = (df["VOLUME"] > df["AvgVol20"] * 1.5).astype(int)
        df["High52W"]   = df["CLOSE"].rolling(252).max()
        df["Low52W"]    = df["CLOSE"].rolling(252).min()
        df["ATH"]       = df["CLOSE"].expanding().max()
    except Exception as e:
        log.warning(f"Indicator error: {e}")
    return df


def is_near_high(df: pd.DataFrame) -> tuple[bool, str]:
    close = df["CLOSE"].dropna()
    if len(close) < MIN_ROWS:
        return False, "insufficient data"

    current  = float(close.iloc[-1])
    high_52w = float(close.tail(252).max())
    ath      = float(close.max())

    near_ath = current >= ath      * (1 - ATH_PCT)
    near_52w = current >= high_52w * (1 - HIGH_52W_PCT)

    if near_ath:
        pct = round((1 - current / ath) * 100, 1)
        return True, f"ATH ({pct}% below ATH {ath:.2f})"
    elif near_52w:
        pct = round((1 - current / high_52w) * 100, 1)
        return True, f"52W High ({pct}% below 52W high {high_52w:.2f})"
    else:
        pct = round((1 - current / high_52w) * 100, 1)
        return False, f"too far from highs ({pct:.1f}% below 52W high)"


def is_fresh_csv(sym: str) -> tuple[bool, pd.DataFrame | None]:
    """Return (is_fresh, df) — skip re-download if CSV is recent."""
    path = os.path.join(paths.market_dir(sym), f"{sym}.csv")
    if not os.path.exists(path):
        return False, None
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    if age_hours > SKIP_IF_FRESH:
        return False, None
    try:
        df = pd.read_csv(path, parse_dates=["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        ok = len(df) >= MIN_ROWS
        return ok, (df if ok else None)
    except Exception:
        return False, None


def save_csv(df: pd.DataFrame, path: str) -> None:
    df_save = df.copy()
    df_save["Date"] = df_save["Date"].dt.strftime("%Y-%m-%d")
    df_save.to_csv(path, index=False)


def remove_stale_csvs(survivors: set[str]) -> int:
    """Remove CSVs from all market subdirs that are no longer in the passed list."""
    removed = 0
    for data_dir in paths.ALL_DATA_DIRS:
        if not os.path.isdir(data_dir):
            continue
        for fname in os.listdir(data_dir):
            if not fname.endswith(".csv"):
                continue
            ticker = fname.replace(".csv", "")
            if ticker not in survivors:
                os.remove(os.path.join(data_dir, fname))
                log.info(f"  Removed stale: {ticker}.csv")
                removed += 1
    return removed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    start_time = datetime.now()
    log.info("=" * 60)
    log.info("Edge Pro — Nightly Download (production layout)")
    log.info(f"Date      : {date.today()}")
    log.info(f"ATH filter: within {ATH_PCT*100:.0f}%  |  "
             f"52W filter: within {HIGH_52W_PCT*100:.0f}%")
    log.info("=" * 60)

    tickers = load_tickers(paths.TICKER_FILE)
    if not tickers:
        log.error("No tickers loaded. Aborting.")
        return

    # ── Step 0: Fetch ASX + US from TradingView market movers ─────────────
    log.info("\n[0/3] Fetching ASX + US tickers from TradingView...")
    try:
        asx_tickers, us_tickers = fetch_all_tv_tickers()
        log.info(f"  ASX : {len(asx_tickers)} tickers")
        log.info(f"  US  : {len(us_tickers)} tickers")

        existing = set(tickers)
        new_asx  = [t for t in asx_tickers if t not in existing]
        new_us   = [t for t in us_tickers  if t not in existing]
        tickers  = tickers + new_asx + new_us
        log.info(f"  +{len(new_asx)} ASX  +{len(new_us)} US  → {len(tickers)} total")

    except Exception as e:
        log.warning(f"TradingView ticker fetch failed: {e} — continuing with Tickers.txt")

    passed, failed, filtered = [], [], []

    # ── Step 1: Download & filter stock universe ───────────────────────────
    log.info(f"\n[1/3] Downloading {len(tickers)} tickers...")
    for i, sym in enumerate(tickers, 1):
        log.info(f"  [{i:03d}/{len(tickers)}] {sym}")

        # Skip if CSV is fresh from today's run
        fresh, df_cached = is_fresh_csv(sym)
        if fresh:
            ok, reason = is_near_high(df_cached)
            if ok:
                log.info(f"         → CACHED [{reason}]")
                passed.append(sym)
            else:
                log.info(f"         → CACHED + FILTERED: {reason}")
                filtered.append((sym, reason))
            continue

        df = download_ticker(sym)

        if df is None:
            log.info("         → SKIP (no data)")
            failed.append(sym)
            time.sleep(DELAY_SECONDS)
            continue

        ok, reason = is_near_high(df)
        if not ok:
            log.info(f"         → FILTERED: {reason}")
            filtered.append((sym, reason))
            time.sleep(DELAY_SECONDS)
            continue

        df = add_indicators(df)
        dest = os.path.join(paths.market_dir(sym), f"{sym}.csv")
        save_csv(df, dest)
        log.info(f"         → SAVED [{reason}]  rows={len(df)}")
        passed.append(sym)
        time.sleep(DELAY_SECONDS)

    # ── Step 2: Download benchmarks ────────────────────────────────────────
    log.info(f"\n[2/3] Downloading {len(BENCHMARKS)} benchmarks...")
    bench_ok, bench_fail = [], []

    for name, sym in BENCHMARKS.items():
        log.info(f"  {name} ({sym})")
        df = download_ticker(sym, period="1y")
        if df is None:
            log.warning("         → FAILED")
            bench_fail.append(name)
        else:
            df = add_indicators(df)
            dest = os.path.join(paths.BENCH_DIR, f"{name}.csv")
            save_csv(df, dest)
            log.info(f"         → saved  rows={len(df)}")
            bench_ok.append(name)
        time.sleep(BENCH_DELAY)

    # ── Step 3: TradingView indicator screener ─────────────────────────────
    log.info("\n[3/3] Fetching TradingView screener data...")
    tv_ok, tv_fail = [], []

    try:
        tv_client = TradingViewClient()

        nse_syms = [s for s in passed if s.endswith((".NS", ".BO"))][:20]
        asx_syms = [s for s in passed if s.endswith(".AX")][:10]
        us_syms  = [s for s in passed if not s.endswith((".NS", ".BO", ".AX"))][:10]

        for syms, mkt, dest_csv in [
            (nse_syms, "NSE", paths.TV_NSE_CSV),
            (asx_syms, "ASX", paths.TV_ASX_CSV),
            (us_syms,  "US",  paths.TV_US_CSV),
        ]:
            if not syms:
                continue
            log.info(f"  {mkt} ({len(syms)} symbols)...")
            df_tv = tv_client.fetch_screener_data(syms, mkt)
            if not df_tv.empty:
                df_tv.to_csv(dest_csv, index=False)
                log.info(f"    → {len(df_tv)} symbols → screeners/")
                tv_ok.append((mkt, len(df_tv)))

    except Exception as e:
        log.warning(f"TradingView screener failed: {e}")
        tv_fail.append(str(e))

    # ── Cleanup stale CSVs ─────────────────────────────────────────────────
    survivors = set(passed)
    removed   = remove_stale_csvs(survivors)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).seconds
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info(f"  Universe     : {len(tickers)} tickers")
    log.info(f"  Passed filter: {len(passed)}  → data/nse+asx+us/")
    log.info(f"  Filtered out : {len(filtered)}")
    log.info(f"  Failed dl    : {len(failed)}")
    log.info(f"  Benchmarks   : {len(bench_ok)} ok / {len(bench_fail)} failed")
    tv_syms = sum(c for _, c in tv_ok)
    log.info(f"  TradingView  : {len(tv_ok)} markets / {tv_syms} symbols → screeners/")
    log.info(f"  Stale removed: {removed}")
    log.info(f"  Duration     : {elapsed}s")
    log.info("=" * 60)

    # Write summary file
    with open(paths.SUMMARY_FILE, "w") as f:
        f.write(f"last_run={date.today()}\n")
        f.write(f"universe={len(tickers)}\n")
        f.write(f"passed={len(passed)}\n")
        f.write(f"filtered={len(filtered)}\n")
        f.write(f"failed={len(failed)}\n")
        f.write(f"benchmarks_ok={len(bench_ok)}\n")
        f.write(f"duration_sec={elapsed}\n")
        f.write("passed_tickers=" + ",".join(passed) + "\n")

    if bench_fail:
        log.warning(f"Benchmarks failed: {bench_fail}")
    log.info("Nightly download complete.")


if __name__ == "__main__":
    main()

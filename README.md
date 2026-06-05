# Edge Pro - Positional Trading System

A desktop application for multi-market positional trading analysis. Covers NSE/BSE (India), ASX (Australia), and US equities. The UI reads exclusively from local CSVs — no network calls at runtime.
Scripts need to be run in the order below:

a) Once--> python reorganize.py (Clean folder structure)
b) Sunday Morning  --> FetchAndDownload.bat (Download all stocks)
c) Sunday Morning --> EdgePro.bat (Launch trading app)

---

## Architecture

The system is split into two independent processes:

### 1. Nightly Downloader (`src/nightly_download.py`)

Runs offline after market close via Windows Task Scheduler. Does all network I/O so the GUI never waits on it.

**Pipeline:**

1. Load NSE tickers from `Tickers.txt`
2. Fetch ASX + US tickers from TradingView's Scanner API (top-volume movers near ATH/52W high)
3. Download 1-year daily OHLCV for the combined universe via `yfinance`
4. **ATH/52W filter** — drop any stock more than 10% below ATH and more than 5% below its 52-week high
5. Compute indicators (RSI-14, ADX-14, EMA 21/55/150/200, AvgVol-20, VolumeSpike, ATH, 52W high/low) and save per-ticker CSVs
6. Download 15 benchmark instruments (Nifty 50, Bank Nifty, S&P 500, Nasdaq, ASX 200, FTSE, Nikkei, HSI, DXY, BTC, Gold, Silver, Crude, Copper, Nat Gas)
7. Fetch TradingView screener data (RSI, MACD, SMAs, ATR) for passed symbols and save to `screeners/`
8. Purge stale CSVs (tickers no longer in the passed list)
9. Write `cache/last_run_summary.txt`

Logs to `logs/nightly_YYYYMMDD.log`. Skips re-download if a CSV was modified within the last 20 hours.

### 2. GUI Application (`src/edge_pro.py`)

Tkinter desktop app. Loads data once at startup (async thread), then all analysis is in-memory.

**Tabs:**

| Tab | Purpose |
|-----|---------|
| Dashboard | Watchlist sorted by RS score; price + EMA chart; RS line vs benchmark |
| Screener | Filter by template (Minervini Stage 2 / VCP / CAN SLIM / Near ATH+Momentum); export CSV |
| RS Analyser | Stock vs benchmark normalised chart; Market Matrix heatmap; Commodities 55d return table |
| Risk Sizer | Position size calculator: capital, risk %, entry, stop, target → qty and R:R |
| Nightly | Last run stats; trigger manual download |
| TV Screener | On-demand TradingView data fetch (RSI, MACD, SMA 20/50/200, ATR) |
| RS Rankings | Multi-period RS (1M/3M/6M/12M) + composite score + momentum + sector table |
| Price-Vol | Volume Conviction Score ranking; OBV, Money Flow, and breakout charts per stock |

---

## Module Reference

| File | Responsibility |
|------|---------------|
| `src/edge_pro.py` | Main app: UI, charting, data orchestration |
| `src/nightly_download.py` | Batch downloader + ATH filter + indicator computation |
| `src/paths.py` | Single source of truth for all directory and file paths |
| `src/tradingview_client.py` | yfinance wrapper that mimics a TradingView screener (OHLCV + indicator calculation) |
| `src/rs_rankings_module.py` | Multi-period RS score engine; sector ranking; RS Rankings tab |
| `src/volume_module.py` | Volume Conviction Score (VCS), OBV, Money Flow, breakout detection, A/D ratio |
| `src/fetch_tv_tickers.py` | TradingView Scanner API client for ASX/US market movers |
| `src/theme.py` | Tkinter theme, colour palette, header widget |
| `src/fetch_ath_tickers.py` | Standalone ATH/52W high scanner |

---

## Indicators

### Computed nightly and stored in CSV

| Indicator | Parameters |
|-----------|-----------|
| RSI | 14-period |
| ADX | 14-period |
| EMA | 21, 55, 150, 200 |
| Average Volume | 20-period |
| Volume Spike | volume > 1.5× AvgVol |
| ATH | All-time high (expanding max) |
| 52W High/Low | Rolling 252-bar |

### Computed at runtime (from CSV data)

**Relative Strength (RS) score** — 55-day percentile rank within market:

```
RS = clamp(50 + (stock_return / |benchmark_return|) × 25, 1, 99)
```

Benchmark routing: `.NS`/`.BO` → Nifty 50; banking tickers → Bank Nifty; `.AX` → ASX 200; US → S&P 500.

**Volume Conviction Score (VCS)** — composite 0–100:

| Component | Max pts |
|-----------|---------|
| Volume Surge (RVOL ≥ 1.5×) | 30 |
| OBV at 52W high | 25 |
| Accum/Dist ratio ≥ 2.0 | 20 |
| Volume Dry-Up at EMA21 support | 15 |
| Money Flow 20MA rising | 10 |

**Multi-Period RS (RS Rankings tab)** — percentile rank within market across 1M/3M/6M/12M windows, weighted composite (40/20/20/20), with 4-week momentum delta.

---

## Directory Layout

```
C:\StockData\
├── src\                    # all source modules
├── data\
│   ├── nse\                # NSE/BSE stock CSVs  (SYMBOL.NS.csv)
│   ├── asx\                # ASX stock CSVs      (SYMBOL.AX.csv)
│   ├── us\                 # US stock CSVs
│   └── benchmarks\         # Index/commodity CSVs (NSEI.csv, GSPC.csv, ...)
├── screeners\              # TradingView screener output CSVs
├── cache\
│   ├── last_run_summary.txt
│   ├── sector_cache.json
│   ├── tv_asx_tickers.txt
│   └── tv_us_tickers.txt
├── logs\                   # nightly_YYYYMMDD.log
├── exports\                # user-exported screener CSVs
├── Tickers.txt             # NSE watchlist (one symbol per line, # = comment)
└── pyproject.toml
```

---

## Requirements

- Python ≥ 3.14
- `uv` (package manager)

Dependencies (from `pyproject.toml`):

```
pandas>=3.0.2
yfinance>=1.2.1
ta>=0.11.0
matplotlib>=3.10.8
pillow>=12.2.0
tkcalendar>=1.6.1
```

---

## Setup

```powershell
# Install dependencies
uv sync

# Create required directories (done automatically on first nightly run)
# or manually:
python -c "import sys; sys.path.insert(0,'src'); import paths; paths.ensure_dirs()"
```

---

## Running

### GUI

```powershell
uv run src/edge_pro.py
```

Or via the provided launcher:

```powershell
.\EdgePro.bat
```

### Nightly download (manual)

```powershell
uv run src/nightly_download.py
```

### Schedule via Windows Task Scheduler

Create a task that runs after your target market closes:

- **Program:** `C:\StockData\.venv\Scripts\python.exe`
- **Arguments:** `C:\StockData\src\nightly_download.py`
- **Start in:** `C:\StockData`

The app's Nightly tab also has a "Run Nightly Download Now" button that spawns the script in a new console window.

---

## Tickers.txt Format

```
# NSE stocks — one Yahoo Finance symbol per line
RELIANCE.NS
INFY.NS
TCS.NS

# ASX stocks (also auto-populated from TradingView)
BHP.AX

# US stocks (also auto-populated from TradingView)
AAPL
NVDA
```

Lines starting with `#` are ignored. ASX and US tickers are supplemented automatically each nightly run from TradingView's Scanner API (top-volume stocks within 5–10% of highs).

---

## Screener Templates

| Template | Criteria |
|----------|---------|
| Minervini Stage 2 | RSI > 55, ADX > 26, full EMA stack aligned (price > EMA21 > EMA55 > EMA150 > EMA200), RS ≥ min |
| VCP Setup | EMA stack aligned, ATR% < 4%, relative volume < 0.8× (contraction) |
| CAN SLIM | Price ≥ 90% of 52W high, RSI > 55, EMA stack aligned |
| Near ATH + Momentum | Price ≥ 90% of ATH, RSI > 52, ADX > 20 |

All templates support additional minimum RS and minimum RSI filters. Results export to CSV via the Export button.

---

## Key Design Decisions

**No network calls in the GUI.** The GUI is purely read-from-CSV. This means the app starts in under a second and never hangs waiting on yfinance rate limits.

**ATH/52W filter in the downloader.** Only stocks within 10% of ATH or 5% of 52W high are kept on disk. This caps storage and keeps the watchlist focused on names with upside momentum.

**Benchmark routing by suffix.** Market detection is suffix-based (`.NS`/`.BO` → NSE, `.AX` → ASX, no suffix → US), with a hardcoded override for Indian banking stocks to route to Bank Nifty instead of Nifty 50.

**Sector data is seed-first, yfinance-fills-gaps.** A hardcoded `SEED_SECTORS` dict covers the most common symbols so the RS Rankings sector table renders immediately without waiting on API calls. Missing sectors are fetched in a background thread and written to `cache/sector_cache.json`.

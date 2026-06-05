# Edge Pro - Positional Trading System

A Python desktop application for multi-market positional stock trading across NSE (India), ASX (Australia), and US markets. Combines nightly data acquisition, relative strength analysis, volume conviction scoring, and sector rotation tracking in a single Tkinter interface.

---

## Quick Start

| When | Command | What it does |
|------|---------|-------------|
| **Once** (first time) | `python reorganize.py` | Creates folder structure, migrates files |
| **Once** (first time) | `uv run src\nightly_download.py` | First data download |
| **Every evening** | `FetchAndDownload.bat` | Downloads all stocks (NSE + ASX + US) |
| **Every morning** | `EdgePro.bat` | Launches the trading UI |

---

## Overview

**Markets covered:** NSE, ASX, US (NYSE/NASDAQ)  
**Trading style:** Positional (swing/trend following, multi-week holding periods)  
**Data source:** yfinance (OHLCV), TradingView Scanner API (market movers)  
**Filter logic:** ATH within 10% OR 52-week high within 5%  
**Benchmark set:** 15 indices including Nifty 50, Bank Nifty, S&P 500, ASX 200, Nasdaq, FTSE, Nikkei, gold, crude, BTC  

The system has two entry points:

| Script | Purpose | When to run |
|--------|---------|-------------|
| `src/nightly_download.py` | Fetches, filters, and stores all stock data | Every evening after market close |
| `src/edge_pro.py` | Launches the trading analysis UI | Every morning before market open |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      EDGE PRO — UI LAYER                        │
│  edge_pro.py  (Tkinter, 1410 lines, 8 tabs)                    │
│                                                                  │
│  Dashboard  │ Screener │ RS Analyser │ Risk Sizer               │
│  Nightly    │ TV Screener │ RS Rankings │ Price-Vol Analysis     │
└──────┬───────────┬──────────────┬──────────────┬───────────────┘
       │           │              │              │
       ▼           ▼              ▼              ▼
  theme.py   rs_rankings_    volume_       tradingview_
  (UI style)  module.py      module.py     client.py
                (RS + MF)    (VCS + OBV)   (screener)
       │
       ▼
  paths.py  ←──── single source of truth for all file paths
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                   DATA LAYER (C:\StockData\)                    │
│  data/nse/    data/asx/    data/us/    data/benchmarks/         │
│  screeners/   cache/       logs/       exports/                 │
└─────────────────────────────────────────────────────────────────┘
       ▲
       │
┌─────────────────────────────────────────────────────────────────┐
│                  NIGHTLY PIPELINE                                │
│  nightly_download.py                                            │
│    │                                                             │
│    ├── Step 0: fetch_tv_tickers.py  ← TradingView Scanner API  │
│    ├── Step 1: yfinance download + ATH/52W filter               │
│    ├── Step 2: benchmark download (15 indices)                  │
│    └── Step 3: tradingview_client.py ← indicator screener      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
C:\StockData\
│
├── src\                         ← all Python source
│   ├── edge_pro.py              ← main application (entry point)
│   ├── nightly_download.py      ← data pipeline (entry point)
│   ├── fetch_tv_tickers.py      ← TradingView market movers fetcher
│   ├── tradingview_client.py    ← yfinance-based screener client
│   ├── volume_module.py         ← volume analysis engine
│   ├── rs_rankings_module.py    ← relative strength ranking engine
│   ├── theme.py                 ← UI theme and style definitions
│   └── paths.py                 ← central path configuration
│
├── data\
│   ├── nse\                     ← RELIANCE.NS.csv, INFY.NS.csv …
│   ├── asx\                     ← BHP.AX.csv, CBA.AX.csv …
│   ├── us\                      ← AAPL.csv, NVDA.csv …
│   └── benchmarks\              ← NSEI.csv, GSPC.csv, AXJO.csv …
│
├── screeners\                   ← TradingView_NSE/ASX/US.csv
├── cache\                       ← sector_cache.json, last_run_summary.txt
├── logs\                        ← nightly_YYYYMMDD.log
├── exports\                     ← manual CSV exports from UI
├── launchers\                   ← original bat files (reference copies)
├── docs\                        ← documentation
├── archive\                     ← deprecated scripts
│
├── EdgePro.bat                  ← launch UI (double-click)
├── FetchAndDownload.bat         ← run nightly pipeline (double-click)
├── Tickers.txt                  ← master NSE ticker list (one per line)
├── pyproject.toml               ← uv project config
├── uv.lock                      ← dependency lock
└── .gitignore
```

---

## Modules

### `src/edge_pro.py` — Main Application
Tkinter desktop UI. 8 tabs, all auto-populated on startup from data in `data/`.

| Tab | Description |
|-----|-------------|
| Dashboard | Price chart (120d), EMA 21/55/150, RS line vs benchmark, key metrics |
| Screener | Filterable stock list with RSI, ADX, EMA stage, ATH proximity |
| RS Analyser | RS score matrix, RS line chart, commodity comparison |
| Risk Sizer | Position sizing calculator (risk %, ATR-based stop) |
| Nightly | Trigger nightly download from UI, view log output |
| TV Screener | On-demand TradingView indicator fetch per market |
| RS Rankings | Multi-period RS scores, momentum, MoneyFlow rank, sector ranking |
| Price-Vol Analysis | VCS scoring, breakout detection, OBV chart, MoneyFlow chart |

**Does not run standalone.** Requires `data/` to be populated by `nightly_download.py`.

---

### `src/nightly_download.py` — Data Pipeline
Batch downloader. Run every evening. Four sequential steps:

```
Step 0: fetch_tv_tickers.py  →  ASX + US ATH/52W movers from TradingView Scanner
Step 1: yfinance download     →  1 year daily OHLCV per ticker + indicator calc
Step 2: benchmark download    →  15 global indices
Step 3: tradingview_client    →  RSI, MACD, ATR, Bollinger, MAs for top symbols
```

**Filter logic (Step 1):**
- `ATH_PCT = 0.10` → include if close ≥ ATH × 0.90
- `HIGH_52W_PCT = 0.05` → include if close ≥ 52W high × 0.95
- `SKIP_IF_FRESH = 20` → skip re-download if CSV < 20 hours old

Saves CSVs to `data/nse/`, `data/asx/`, `data/us/`. Removes stale CSVs that no longer pass the filter. Writes `cache/last_run_summary.txt`.

---

### `src/fetch_tv_tickers.py` — TradingView Market Movers
Queries TradingView's internal Scanner API directly (no browser, no tvDatafeed). Returns ASX and US symbols currently near their ATH or 52-week high.

- Endpoint: `https://scanner.tradingview.com/{market}/scan`
- Markets: `australia` → `.AX` suffix, `america` → no suffix
- Filter thresholds mirror `nightly_download.py` (`ATH_PCT`, `HIGH_52W_PCT`)
- Saves ticker lists to `cache/tv_asx_tickers.txt` and `cache/tv_us_tickers.txt`

Called automatically by `nightly_download.py` at Step 0. Can also run standalone:
```powershell
uv run src\fetch_tv_tickers.py
```

---

### `src/tradingview_client.py` — Screener Client
Uses yfinance to calculate 16 technical indicators per symbol. No tvDatafeed dependency.

**Indicators returned:** Close, RSI(14), MACD, MACD Signal, MACD Histogram, SMA 20/50/200, EMA 12/26, Bollinger Bands (upper/middle/lower), ATR(14), 52W High, 52W Low.

**Symbol suffix handling:** Automatically adds/strips `.NS`, `.AX` based on market parameter. Handles MultiIndex columns from newer yfinance versions.

**Rate limiting:** 0.5s minimum between requests.

```python
from tradingview_client import TradingViewClient
client = TradingViewClient()
df = client.fetch_screener_data(['RELIANCE', 'INFY'], 'NSE')
```

---

### `src/volume_module.py` — Volume Analysis Engine
Core analytics class. All calculations from existing OHLCV data, no external API calls.

```python
from volume_module import VolumeAnalyser, batch_vcs
va = VolumeAnalyser(df)      # df: OHLCV DataFrame from data/
m  = va.metrics()            # returns all metrics as dict
```

**`VolumeAnalyser` methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `relative_volume()` | float | Today's volume / 20-day average volume |
| `volume_dry_up()` | bool | Volume < 0.5× avg for 5 days AND price within 3% of EMA21 |
| `accum_dist_days(25)` | dict | Accumulation/distribution day count over N sessions |
| `obv_analysis()` | dict | OBV trend (Rising/Flat/Falling) + new 52W high flag |
| `money_flow()` | dict | Close × Volume, 20-day MA, trend direction |
| `breakout_signal()` | dict | ATH/52W breakout with volume confirmation |
| `vcs()` | dict | Volume Conviction Score (0–100), component breakdown |
| `metrics()` | dict | All of the above in one call |

**VCS scoring:**

| Component | Max points |
|-----------|-----------|
| Volume surge (> 1.5× avg) | 30 |
| OBV at 52W high | 25 |
| Accumulation/Distribution ratio ≥ 2.0 | 20 |
| Volume Dry-Up at support | 15 |
| MoneyFlow 20MA rising | 10 |
| **Total** | **100** |

`batch_vcs(stocks)` processes all loaded stocks and returns a DataFrame sorted by VCS descending. Used by the Price-Vol Analysis tab.

---

### `src/rs_rankings_module.py` — RS Rankings Engine
Calculates multi-period relative strength scores and sector rankings.

**RS calculation:**
- Periods: 1M (21 bars), 3M (63), 6M (126), 12M (252 bars)
- Method: percentile rank of N-day return within same market (NSE vs NSE, ASX vs ASX, US vs US)
- Composite: `0.40 × RS_12M + 0.20 × RS_6M + 0.20 × RS_3M + 0.20 × RS_1M`
- Momentum: composite score now minus composite score 21 bars ago
- MoneyFlow Rank: percentile rank of `Close × Volume` 20-day MA within market

**Sector data:** Pre-seeded for 80+ common NSE/ASX/US stocks (`SEED_SECTORS` dict). Missing sectors fetched from yfinance in background thread and persisted to `cache/sector_cache.json`.

---

### `src/theme.py` — UI Theme
Applies global Tkinter/ttk styling. Contains `Header` widget (dark navbar with live market clocks), button factories, and color token definitions.

**Key exports:**
- `theme.apply(root)` — call once in `EdgePro.__init__`
- `theme.Header(root)` — dark header bar with NSE/ASX/NYSE clocks
- `theme.P` — color token dict
- `theme.btn_primary(parent, text, command)` — styled button
- `theme.zebra(tree)` — apply alternating row colors to any Treeview

Requires `pytz` for timezone-aware market open/close detection.

---

### `src/paths.py` — Central Path Configuration
Single source of truth for all file and directory paths. Every other module imports this.

```python
import paths
paths.ROOT          # C:\StockData
paths.NSE_DIR       # C:\StockData\data\nse
paths.BENCH_DIR     # C:\StockData\data\benchmarks
paths.SECTOR_CACHE  # C:\StockData\cache\sector_cache.json
paths.market_dir("RELIANCE.NS")   # returns NSE_DIR
paths.ticker_market("BHP.AX")     # returns "ASX"
paths.ensure_dirs()               # creates all directories
```

**To relocate the project:** change `ROOT` on line 9. All paths update automatically.

---

## Dependencies

**Runtime (installed via uv):**

| Package | Version | Used by |
|---------|---------|---------|
| `pandas` | ≥ 2.0 | all modules |
| `yfinance` | ≥ 0.2 | nightly_download, tradingview_client |
| `ta` | ≥ 0.10 | nightly_download (RSI, ADX, EMA) |
| `matplotlib` | ≥ 3.7 | edge_pro (charts) |
| `Pillow` | ≥ 10.0 | edge_pro (chart → canvas conversion) |
| `requests` | ≥ 2.31 | fetch_tv_tickers (Scanner API) |
| `pytz` | ≥ 2023.3 | theme (market clocks) |

**Standard library (no install needed):** `tkinter`, `threading`, `queue`, `json`, `os`, `time`, `logging`

---

## Setup

**Requirements:** Python 3.11+, [uv](https://docs.astral.sh/uv/) package manager, Windows (tested on Windows 10/11)

```powershell
# 1. Clone or extract to C:\StockData

# 2. Install uv if not already installed
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 3. Create virtual environment and install dependencies
cd C:\StockData
uv sync

# 4. Reorganise folder structure (first time only)
python reorganize.py

# 5. Populate Tickers.txt with NSE symbols (one per line)
#    Example:
#    RELIANCE.NS
#    INFY.NS
#    HDFC.NS

# 6. Run first nightly download
uv run src\nightly_download.py

# 7. Launch Edge Pro
uv run src\edge_pro.py
```

---

## Configuration

All tunable parameters are at the top of their respective scripts.

### `src/nightly_download.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ATH_PCT` | `0.10` | Include stock if close ≥ ATH × (1 − ATH_PCT) |
| `HIGH_52W_PCT` | `0.05` | Include stock if close ≥ 52W high × (1 − HIGH_52W_PCT) |
| `SKIP_IF_FRESH` | `20` | Skip download if CSV modified within N hours |
| `DOWNLOAD_PERIOD` | `"1y"` | yfinance period string |
| `DELAY_SECONDS` | `1.4` | Pause between ticker downloads (rate limiting) |
| `BENCHMARKS` | dict | 15 global indices — add/remove as needed |

### `src/fetch_tv_tickers.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SCAN_LIMIT` | `200` | Max stocks fetched per Scanner API call |
| `ATH_PCT` | `0.10` | Must match nightly_download.py |
| `HIGH_52W_PCT` | `0.05` | Must match nightly_download.py |

### `src/rs_rankings_module.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `PERIODS` | `{1M:21, 3M:63, 6M:126, 12M:252}` | Trading days per RS period |
| `WEIGHTS` | `{12M:0.40, 6M:0.20, 3M:0.20, 1M:0.20}` | Composite RS weights |
| `SHIFT` | `21` | Bars back for RS momentum calculation |

### `src/paths.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ROOT` | `C:\StockData` | Project root — change here to relocate entire project |

---

## Script Execution Sequence

### One-time (initial setup only)

```
1. python reorganize.py          → creates folder structure, moves files
2. uv run src\nightly_download.py → first data download
3. uv run src\edge_pro.py         → verify UI loads correctly
```

### Recurring (every evening, after market close)

```
uv run src\nightly_download.py
  └── calls fetch_tv_tickers.py  [Step 0]  fetch ASX+US symbols from TradingView
  └── yfinance download loop     [Step 1]  download + filter all tickers
  └── benchmark download         [Step 2]  15 global indices
  └── calls tradingview_client   [Step 3]  indicator screener CSVs
```

Single command. All sub-scripts are called internally. Do not run sub-scripts manually as part of the nightly routine.

### Recurring (every morning, before market open)

```
uv run src\edge_pro.py
```

Reads from `data/`, `screeners/`, `cache/`. Does not make network calls on startup.

### Standalone (on-demand only)

```
uv run src\fetch_tv_tickers.py    → test TradingView Scanner API, view tickers
uv run src\tradingview_client.py  → test indicator fetch for RELIANCE, BHP, AAPL
```

---

## Daily Workflow

```
18:00  Market closes (NSE)
18:30  Double-click FetchAndDownload.bat   → runs nightly_download.py
       └─ ~5–10 min depending on universe size
       └─ Check logs\nightly_YYYYMMDD.log for errors

08:30  Double-click EdgePro.bat            → launches UI
       └─ Dashboard auto-loads first stock from watchlist
       └─ RS Rankings tab populates in ~1 sec
       └─ Price-Vol Analysis tab populates in ~2 sec
```

---

## Data Flow

```
Tickers.txt (NSE)
    │
    ▼
nightly_download.py
    │
    ├── fetch_tv_tickers.py ──► TradingView Scanner API
    │       └── returns ASX + US symbols near ATH/52W high
    │
    ├── yfinance.download() ──► Yahoo Finance API
    │       └── 1y daily OHLCV per ticker
    │       └── filter: ATH_PCT / HIGH_52W_PCT
    │       └── add: RSI, ADX, EMA21/55/150/200, ATH, High52W
    │       └── save: data/{market}/{ticker}.csv
    │
    ├── yfinance.download() ──► 15 benchmarks
    │       └── save: data/benchmarks/{name}.csv
    │
    └── tradingview_client ──► yfinance (indicator calc)
            └── RSI, MACD, ATR, Bollinger, SMA/EMA
            └── save: screeners/TradingView_{NSE|ASX|US}.csv

edge_pro.py
    │
    ├── load_stocks()   ← reads all CSVs from data/{nse,asx,us}/
    ├── load_benchmarks() ← reads all CSVs from data/benchmarks/
    │
    ├── rs_rankings_module.calc_rs_df()
    │       └── percentile rank within market per period
    │       └── composite RS, momentum, MoneyFlow rank
    │       └── sector lookup from cache/sector_cache.json
    │
    └── volume_module.batch_vcs()
            └── VolumeAnalyser per stock
            └── VCS score, OBV, MoneyFlow, breakout, VDU
```

---

## Tab Reference

### Dashboard
- Stock list on left (watchlist filtered by ATH/52W proximity)
- Price chart: 120-day daily OHLCV + EMA 21/55/150
- RS line: stock vs benchmark (Nifty 50 for NSE, ASX 200 for ASX, S&P 500 for US), normalised to 1.0 at start of 55-day window
- Metrics: ticker, last close, % from ATH, RS score, RSI, ADX, Stage (Stage 2 = close > EMA21 > EMA55 > EMA150)

### RS Rankings
- **RS table:** Rank, Ticker, Market, Sector, RS_1M, RS_3M, RS_6M, RS_12M, Composite, Momentum, MF Rank, Signal
- **Sector table:** Sector, Market, Avg RS, stock count, best/worst stock
- Filters: market (All/NSE/ASX/US), sort by any column
- Momentum column: positive = RS improving vs 4 weeks ago, negative = deteriorating
- MF Rank: percentile rank of 20-day average money flow within market

### Price-Vol Analysis
- Left panel: all stocks ranked by VCS (green ≥ 70, yellow 45–69, red < 45)
- Right panel on selection:
  - 7 metric chips: VCS score, RVOL, breakout signal, A/D ratio, OBV trend, MoneyFlow trend
  - VCS breakdown bar: shows point contribution of each component
  - 3-panel chart: Price + Volume bars (green/red) → OBV + MA → MoneyFlow + MA

### Screener
- Full universe sortable by any column
- Columns: Ticker, Market, Close, RSI, ADX, EMA21, EMA55, EMA150, AvgVol20, VolumeSpike, High52W, Low52W, ATH
- Export to `exports/` as CSV

### Risk Sizer
- Inputs: portfolio size, risk %, entry price, stop price, commission
- Outputs: position size (shares), capital at risk, commission cost, reward/risk ratio

---

## Notes

**yfinance MultiIndex columns:** Newer versions return tuple columns `('Close', 'RELIANCE.NS')`. All modules handle this via explicit flattening before processing.

**TradingView Scanner API:** No authentication required. Returns `HTTP 400` if payload contains unsupported filter operations (e.g. `nempty`). Current implementation uses only `egreater` filters with client-side ATH/52W filtering.

**Sector cache:** Built progressively. First run shows `—` for unknown sectors. yfinance sector fetch runs in background thread (0.4s delay per ticker, capped at 60 tickers per session). Persisted to `cache/sector_cache.json` and seeded with 80+ pre-mapped common stocks.

**Windows Task Scheduler:** To automate nightly downloads, create a task pointing to:
- Program: `C:\StockData\.venv\Scripts\python.exe`
- Arguments: `C:\StockData\src\nightly_download.py`
- Start in: `C:\StockData`
- Trigger: Daily, 18:30

---

## License

Private use only.

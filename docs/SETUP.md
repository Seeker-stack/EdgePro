# Edge Pro — Setup Guide
# ============================================================

## 1. Install dependencies

Open Command Prompt and run:

    pip install pandas yfinance ta matplotlib pillow tkcalendar

---

## 2. Copy files to C:\StockData\

Place these files in C:\StockData\:

    C:\StockData\
    ├── edge_pro.py              ← main application
    ├── nightly_download.py      ← batch downloader
    ├── run_nightly.bat          ← scheduler launcher
    └── Tickers.txt              ← your master universe

The app will auto-create:
    C:\StockData\benchmarks\     ← benchmark CSVs
    C:\StockData\logs\           ← nightly log files

---

## 3. Edit Tickers.txt

Open Tickers.txt and add/remove tickers as needed.
- NSE stocks: add .NS suffix (e.g. HDFCBANK.NS)
- BSE stocks: add .BO suffix (e.g. 500325.BO)
- ASX stocks: add .AX suffix (e.g. CBA.AX)
- US stocks:  no suffix (e.g. AAPL)

---

## 4. Run the first download manually

Open Command Prompt:

    cd C:\StockData
    python nightly_download.py

This takes 3-5 minutes depending on universe size.
Check C:\StockData\logs\ for the log file.

---

## 5. Schedule via Windows Task Scheduler

Open Task Scheduler → Create Basic Task

    Name        : Edge Pro Nightly Download
    Trigger     : Daily
    Start time  : 16:30 (after NSE close 15:30 IST)
                  OR 18:00 AEST (after ASX close 16:00 AEST)
    Action      : Start a program
    Program     : C:\StockData\run_nightly.bat
    Start in    : C:\StockData

Under "Conditions":
    - Uncheck "Start only if computer is on AC power"
      (if using a laptop)

Under "Settings":
    - Check "Run task as soon as possible after scheduled
      start is missed" (catches up if PC was off)

---

## 6. Run the app

    cd C:\StockData
    python edge_pro.py

Or create a desktop shortcut pointing to:
    python C:\StockData\edge_pro.py

---

## ATH / 52W Filter thresholds

Edit these lines in nightly_download.py to adjust:

    ATH_PCT      = 0.10   # within 10% of all-time high
    HIGH_52W_PCT = 0.05   # within 5% of 52-week high

Tighter = fewer stocks, faster download
Looser  = more stocks, broader universe

---

## Rate limiting

Current settings (nightly_download.py):
    DELAY_SECONDS = 1.4   # between stock downloads
    BENCH_DELAY   = 1.0   # between benchmark downloads

With 100 tickers + 15 benchmarks this takes ~3.5 minutes.
With 200 tickers + 15 benchmarks this takes ~6.5 minutes.
Both are well within Yahoo Finance's tolerance.
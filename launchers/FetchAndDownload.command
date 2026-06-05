#!/bin/bash
cd ~/StockData

echo "============================================"
echo " Step 1: Fetching ATH tickers from TradingView"
echo "============================================"
uv run fetch_ath_tickers.py

echo ""
echo "============================================"
echo " Step 2: Downloading OHLCV data"
echo "============================================"
uv run nightly_download.py

echo ""
echo "============================================"
echo " All done."
echo "============================================"

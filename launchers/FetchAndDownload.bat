@echo off
:: FetchAndDownload.bat
:: Run nightly after market close to fetch TV tickers + download all stocks

title Edge Pro — Nightly Download
cd /d C:\StockData

echo ============================================
echo  Edge Pro — Nightly Download
echo  %date% %time%
echo ============================================
echo.

uv run nightly_download.py

echo.
echo ============================================
echo  Done! Check logs\ for details.
echo ============================================
pause

@echo off
REM ============================================================
REM  Edge Pro — Nightly Download Launcher
REM  Save this as: C:\StockData\run_nightly.bat
REM  Schedule via Windows Task Scheduler (see instructions below)
REM ============================================================

echo [%date% %time%] Starting Edge Pro nightly download...
cd /d C:\StockData
python nightly_download.py
echo [%date% %time%] Done.
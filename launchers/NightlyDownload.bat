@echo off
title Edge Pro — Nightly Download
cd /d C:\StockData
echo [%date% %time%] Starting nightly download...
uv run nightly_download.py
echo [%date% %time%] Done.
pause
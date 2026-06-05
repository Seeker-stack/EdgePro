@echo off
title Edge Pro — Nightly Download
cd /d C:\StockData
echo Running nightly download...
uv run src\nightly_download.py
echo.
echo Done! Check logs\ for details.
pause

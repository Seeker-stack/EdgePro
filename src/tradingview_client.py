import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
tradingview_client.py
---------------------
TradingView-style screener using yfinance. No external dependencies.
Saves screener CSVs to screeners/ folder.
"""

import pandas as pd
import yfinance as yf
import logging, time
from typing import Dict, List, Optional
from datetime import datetime
import paths

log = logging.getLogger("TradingViewClient")

SYMBOL_MAP = {"NSE": ".NS", "ASX": ".AX", "US": ""}


class TradingViewClient:

    def __init__(self):
        log.info("TradingView-style screener initialized (yfinance)")
        self._last = {}

    def _rate_limit(self, sym):
        elapsed = time.time() - self._last.get(sym, 0)
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        self._last[sym] = time.time()

    def _add_suffix(self, symbol: str, market: str) -> str:
        suffix = SYMBOL_MAP.get(market.upper(), "")
        for s in (".NS", ".BO", ".AX"):
            if symbol.endswith(s):
                symbol = symbol[:-len(s)]
                break
        return symbol + suffix

    def fetch_ohlcv(self, symbol: str, market: str,
                    period: str = "1y") -> Optional[pd.DataFrame]:
        try:
            self._rate_limit(symbol)
            full = self._add_suffix(symbol, market)
            log.info(f"Fetching {full}...")
            df = yf.download(full, period=period, interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty:
                log.warning(f"No data for {full}")
                return None

            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0].lower() for c in df.columns]
            else:
                df.columns = [c.lower() for c in df.columns]

            col_map = {"date": "date", "open": "open", "high": "high",
                       "low": "low", "close": "close", "volume": "volume"}
            df = df.rename(columns=col_map)
            needed = ["date", "open", "high", "low", "close", "volume"]
            df = df[[c for c in needed if c in df.columns]].copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
            log.info(f"Fetched {len(df)} bars for {full}")
            return df if len(df) >= 20 else None

        except Exception as e:
            log.warning(f"Error fetching {symbol}: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        if df is None or df.empty:
            return {}
        try:
            close = df["close"].astype(float)
            high  = df["high"].astype(float)
            low   = df["low"].astype(float)

            delta = close.diff()
            gain  = delta.where(delta > 0, 0).rolling(14).mean()
            loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi   = 100 - (100 / (1 + gain / loss))

            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd  = ema12 - ema26
            sig   = macd.ewm(span=9).mean()

            sma20  = close.rolling(20).mean()
            bb_std = close.rolling(20).std()

            tr   = pd.concat([high - low,
                               (high - close.shift()).abs(),
                               (low  - close.shift()).abs()], axis=1).max(axis=1)
            atr  = tr.rolling(14).mean()

            return {
                "Close":          float(close.iloc[-1]),
                "RSI_14":         float(rsi.iloc[-1]),
                "MACD":           float(macd.iloc[-1]),
                "MACD_Signal":    float(sig.iloc[-1]),
                "MACD_Histogram": float((macd - sig).iloc[-1]),
                "SMA_20":         float(sma20.iloc[-1]),
                "SMA_50":         float(close.rolling(50).mean().iloc[-1]),
                "SMA_200":        float(close.rolling(200).mean().iloc[-1]),
                "EMA_12":         float(ema12.iloc[-1]),
                "EMA_26":         float(ema26.iloc[-1]),
                "BB_Upper":       float((sma20 + 2 * bb_std).iloc[-1]),
                "BB_Middle":      float(sma20.iloc[-1]),
                "BB_Lower":       float((sma20 - 2 * bb_std).iloc[-1]),
                "ATR_14":         float(atr.iloc[-1]),
                "High_52w":       float(high.tail(252).max()),
                "Low_52w":        float(low.tail(252).min()),
            }
        except Exception as e:
            log.error(f"Indicator error: {e}")
            return {}

    def fetch_screener_data(self, symbols: List[str], market: str) -> pd.DataFrame:
        results = []
        for sym in symbols:
            df = self.fetch_ohlcv(sym, market)
            if df is not None and not df.empty:
                ind = self.calculate_indicators(df)
                row = {"Symbol": sym, "Market": market, **ind,
                       "Timestamp": datetime.now()}
                results.append(row)
        return pd.DataFrame(results) if results else pd.DataFrame()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    c = TradingViewClient()

    print("=" * 50)
    print("TradingView Client — Quick Test")
    print("=" * 50)
    for sym, mkt in [("RELIANCE", "NSE"), ("BHP", "ASX"), ("AAPL", "US")]:
        print(f"\n[{mkt}] {sym}")
        df = c.fetch_ohlcv(sym, mkt)
        if df is not None:
            ind = c.calculate_indicators(df)
            print(f"  Close  : {ind.get('Close', 0):.2f}")
            print(f"  RSI(14): {ind.get('RSI_14', 0):.1f}")
            print(f"  MACD   : {ind.get('MACD', 0):.4f}")
            print(f"  SMA200 : {ind.get('SMA_200', 0):.2f}")
            print(f"  ATR(14): {ind.get('ATR_14', 0):.2f}")
        else:
            print("  ✗ No data")
    print("\n" + "=" * 50)

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
volume_module.py
----------------
Volume analysis engine for Edge Pro.

Provides:
  1. Volume Conviction Score (VCS) — composite 0-100
  2. Breakout detection   (price near high + volume surge)
  3. Volume Dry-Up (VDU)  (low volume at moving average support)
  4. Accumulation / Distribution day count (25-day window)
  5. On-Balance Volume (OBV) with trend & new-high detection
  6. Money Flow (Close × Volume, 20-day MA, trend direction)
  7. Relative Volume (RVOL = today / 20-day avg volume)

Usage:
    from volume_module import VolumeAnalyser
    va  = VolumeAnalyser(df)          # df has CLOSE, HIGH, LOW, VOLUME, Date
    m   = va.metrics()                # returns dict of all metrics
    vcs = m["vcs"]                    # 0-100 conviction score
"""

import pandas as pd
import numpy as np


class VolumeAnalyser:
    """
    Calculates all volume-based metrics from an OHLCV DataFrame.
    Expects columns: Date, OPEN, HIGH, LOW, CLOSE, VOLUME
    """

    def __init__(self, df: pd.DataFrame, avg_period: int = 20):
        self.df  = df.copy().sort_values("Date").reset_index(drop=True)
        self.avg = avg_period
        self._prepare()

    # ── Internal prep ─────────────────────────────────────────────────────────

    def _prepare(self):
        d = self.df
        d["AvgVol"]    = d["VOLUME"].rolling(self.avg).mean()
        d["MoneyFlow"] = d["CLOSE"] * d["VOLUME"]
        d["MF_MA"]     = d["MoneyFlow"].rolling(self.avg).mean()

        # OBV
        obv = [0]
        for i in range(1, len(d)):
            prev_obv = obv[-1]
            if d["CLOSE"].iloc[i] > d["CLOSE"].iloc[i - 1]:
                obv.append(prev_obv + d["VOLUME"].iloc[i])
            elif d["CLOSE"].iloc[i] < d["CLOSE"].iloc[i - 1]:
                obv.append(prev_obv - d["VOLUME"].iloc[i])
            else:
                obv.append(prev_obv)
        d["OBV"] = obv

        # Daily direction
        d["Up"]   = d["CLOSE"] > d["CLOSE"].shift(1)
        d["Down"] = d["CLOSE"] < d["CLOSE"].shift(1)
        d["VolUp"]= d["VOLUME"] > d["VOLUME"].shift(1)

        self.df = d

    # ── Individual metrics ────────────────────────────────────────────────────

    def relative_volume(self) -> float:
        """RVOL: today's volume vs 20-day average."""
        d = self.df
        avg = d["AvgVol"].iloc[-1]
        vol = d["VOLUME"].iloc[-1]
        if avg and avg > 0:
            return round(float(vol) / float(avg), 2)
        return 1.0

    def volume_surge(self, threshold: float = 1.5) -> bool:
        """True if today's volume > threshold × 20-day average."""
        return self.relative_volume() >= threshold

    def volume_dry_up(self, threshold: float = 0.5, window: int = 5) -> bool:
        """
        True if volume has been < threshold × avg for last `window` days
        AND price is within 3% of EMA21 (at support).
        """
        d = self.df.tail(window + 1)
        avg_vol = d["AvgVol"].iloc[-1]
        if avg_vol is None or avg_vol == 0:
            return False

        vol_quiet = all(
            d["VOLUME"].iloc[i] < avg_vol * threshold
            for i in range(-window, 0)
        )
        if not vol_quiet:
            return False

        close  = float(self.df["CLOSE"].iloc[-1])
        ema21  = float(self.df["CLOSE"].ewm(span=21, adjust=False).mean().iloc[-1])
        near_support = abs(close - ema21) / ema21 < 0.03
        return near_support

    def accum_dist_days(self, window: int = 25) -> dict:
        """
        Count accumulation and distribution days over last `window` sessions.
        Accumulation: Close UP + Volume > prev day's volume
        Distribution: Close DOWN + Volume > prev day's volume
        """
        d = self.df.tail(window + 1).copy()
        accum = int(((d["Up"]) & (d["VolUp"])).sum())
        dist  = int(((d["Down"]) & (d["VolUp"])).sum())
        ratio = round(accum / dist, 2) if dist > 0 else float("inf")
        return {
            "accum_days": accum,
            "dist_days":  dist,
            "ad_ratio":   ratio,
            "ad_signal":  "Accumulating" if ratio >= 2.0 else
                          "Distributing" if ratio <= 0.5 else "Neutral",
        }

    def obv_analysis(self) -> dict:
        """OBV trend and new-high detection."""
        obv = self.df["OBV"]
        latest  = float(obv.iloc[-1])
        ma20    = float(obv.rolling(20).mean().iloc[-1])
        ma5     = float(obv.rolling(5).mean().iloc[-1])
        high52  = float(obv.tail(252).max())

        if ma5 > ma20:
            trend = "Rising"
        elif ma5 < ma20 * 0.98:
            trend = "Falling"
        else:
            trend = "Flat"

        new_high = latest >= high52 * 0.99   # within 1% of 52W OBV high

        return {
            "obv_latest":   latest,
            "obv_trend":    trend,
            "obv_new_high": new_high,
            "obv_series":   obv,              # full series for charting
        }

    def money_flow(self) -> dict:
        """Money Flow = Close × Volume, with 20-day MA and trend."""
        d = self.df
        mf_today = float(d["MoneyFlow"].iloc[-1])
        mf_ma    = float(d["MF_MA"].iloc[-1])
        mf_prev  = float(d["MF_MA"].iloc[-5]) if len(d) > 5 else mf_ma

        trend = "Rising" if mf_ma > mf_prev * 1.01 else (
                "Falling" if mf_ma < mf_prev * 0.99 else "Flat")

        return {
            "mf_today":  mf_today,
            "mf_ma20":   mf_ma,
            "mf_trend":  trend,
            "mf_series": d["MoneyFlow"],     # full series for charting
            "mf_ma_series": d["MF_MA"],
        }

    def breakout_signal(self) -> dict:
        """
        True when price is within 2% of 52W high AND volume >= 1.5× avg.
        Also catches ATH breakout.
        """
        close   = float(self.df["CLOSE"].iloc[-1])
        h52     = float(self.df["CLOSE"].tail(252).max())
        ath     = float(self.df["CLOSE"].max())
        rvol    = self.relative_volume()
        vol_ok  = rvol >= 1.5

        near_h52 = close >= h52 * 0.98
        near_ath = close >= ath * 0.98

        if near_ath and vol_ok:
            signal = "ATH Breakout 🔥"
            strength = "Strong"
        elif near_h52 and vol_ok:
            signal = "52W Breakout ✅"
            strength = "Strong"
        elif near_h52 and not vol_ok:
            signal = "Near High (Low Vol ⚠)"
            strength = "Weak"
        else:
            signal = "No Breakout"
            strength = "None"

        return {
            "breakout":          near_h52 or near_ath,
            "breakout_signal":   signal,
            "breakout_strength": strength,
            "near_ath":          near_ath,
            "near_52h":          near_h52,
            "rvol":              rvol,
        }

    # ── Volume Conviction Score ───────────────────────────────────────────────

    def vcs(self) -> dict:
        """
        Volume Conviction Score (0-100).

        Component                          Max pts
        ─────────────────────────────────────────
        Volume Surge (>1.5× avg)              30
        OBV at new 52W high                   25
        Accum days > Dist days (ratio ≥ 2)    20
        Volume Dry-Up at support              15
        MoneyFlow 20MA rising                 10
        ─────────────────────────────────────────
        Total                                100
        """
        score = 0
        breakdown = {}

        # 1. Volume Surge
        rvol = self.relative_volume()
        if rvol >= 2.0:
            pts = 30
        elif rvol >= 1.5:
            pts = 20
        elif rvol >= 1.2:
            pts = 10
        else:
            pts = 0
        score += pts
        breakdown["vol_surge"] = pts

        # 2. OBV at new high
        obv = self.obv_analysis()
        pts = 25 if obv["obv_new_high"] else (12 if obv["obv_trend"] == "Rising" else 0)
        score += pts
        breakdown["obv"] = pts

        # 3. Accumulation vs Distribution
        ad = self.accum_dist_days()
        ratio = ad["ad_ratio"]
        if ratio == float("inf") or ratio >= 3.0:
            pts = 20
        elif ratio >= 2.0:
            pts = 15
        elif ratio >= 1.2:
            pts = 8
        else:
            pts = 0
        score += pts
        breakdown["accum_dist"] = pts

        # 4. Volume Dry-Up at support
        pts = 15 if self.volume_dry_up() else 0
        score += pts
        breakdown["vdu"] = pts

        # 5. Money Flow rising
        mf = self.money_flow()
        pts = 10 if mf["mf_trend"] == "Rising" else (5 if mf["mf_trend"] == "Flat" else 0)
        score += pts
        breakdown["money_flow"] = pts

        label = ("🔥 High Conviction"   if score >= 70 else
                 "✅ Moderate"           if score >= 45 else
                 "⚠ Low Conviction"    if score >= 25 else
                 "❌ No Signal")

        return {
            "vcs":       score,
            "vcs_label": label,
            "breakdown": breakdown,
            "rvol":      rvol,
        }

    # ── All metrics in one call ───────────────────────────────────────────────

    def metrics(self) -> dict:
        """Return all volume metrics as a single dict."""
        vcs_data = self.vcs()
        bo       = self.breakout_signal()
        obv      = self.obv_analysis()
        mf       = self.money_flow()
        ad       = self.accum_dist_days()
        vdu      = self.volume_dry_up()
        rvol     = self.relative_volume()

        return {
            # Scores
            "vcs":              vcs_data["vcs"],
            "vcs_label":        vcs_data["vcs_label"],
            "vcs_breakdown":    vcs_data["breakdown"],
            # Breakout
            "breakout":         bo["breakout"],
            "breakout_signal":  bo["breakout_signal"],
            "breakout_strength":bo["breakout_strength"],
            "near_ath":         bo["near_ath"],
            "near_52h":         bo["near_52h"],
            # Volume
            "rvol":             rvol,
            "vol_surge":        rvol >= 1.5,
            "vdu":              vdu,
            # Accum/Dist
            "accum_days":       ad["accum_days"],
            "dist_days":        ad["dist_days"],
            "ad_ratio":         ad["ad_ratio"],
            "ad_signal":        ad["ad_signal"],
            # OBV
            "obv_trend":        obv["obv_trend"],
            "obv_new_high":     obv["obv_new_high"],
            "obv_series":       obv["obv_series"],
            # Money Flow
            "mf_today":         mf["mf_today"],
            "mf_ma20":          mf["mf_ma20"],
            "mf_trend":         mf["mf_trend"],
            "mf_series":        mf["mf_series"],
            "mf_ma_series":     mf["mf_ma_series"],
        }


# ── Convenience function ──────────────────────────────────────────────────────

def batch_vcs(stocks: dict) -> pd.DataFrame:
    """
    Calculate VCS and key metrics for all stocks.
    Returns DataFrame sorted by VCS descending.

    stocks: dict {ticker: df}
    """
    rows = []
    for ticker, df in stocks.items():
        try:
            va  = VolumeAnalyser(df)
            m   = va.metrics()
            mkt = ("NSE" if ticker.endswith((".NS",".BO")) else
                   "ASX" if ticker.endswith(".AX") else "US")
            rows.append({
                "Ticker":     ticker,
                "Market":     mkt,
                "VCS":        m["vcs"],
                "VCS_Label":  m["vcs_label"],
                "RVOL":       m["rvol"],
                "Breakout":   m["breakout_signal"],
                "VDU":        "Yes" if m["vdu"] else "—",
                "AD_Ratio":   m["ad_ratio"] if m["ad_ratio"] != float("inf") else 99,
                "AD_Signal":  m["ad_signal"],
                "OBV_Trend":  m["obv_trend"],
                "OBV_NewHigh":m["obv_new_high"],
                "MF_Trend":   m["mf_trend"],
            })
        except Exception as e:
            pass
    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.sort_values("VCS", ascending=False).reset_index(drop=True)
    return df_out

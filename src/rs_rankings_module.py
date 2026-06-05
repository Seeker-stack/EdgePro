import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
rs_rankings_module.py
---------------------
RS Rankings tab for Edge Pro.
Implements:
  1. Multi-Period RS Scores (1M / 3M / 6M / 12M + Composite) with heatmap
  2. RS Momentum (composite change over 4 weeks)
  3. Sector RS Ranking (best → worst sectors per market)
"""

import os, json, threading
import pandas as pd
import tkinter as tk
from tkinter import ttk
import paths

PERIODS = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}
WEIGHTS = {"12M": 0.40, "6M": 0.20, "3M": 0.20, "1M": 0.20}
SHIFT   = 21   # bars back for momentum (≈ 4 weeks)

# ── Pre-seeded sector map ─────────────────────────────────────────────────────
# Covers common ASX, NSE and US stocks so the sector table shows immediately.
# yfinance fills in any missing ones in the background.
SEED_SECTORS = {
    # ── ASX ──────────────────────────────────────────────────────────────────
    "BHP":"Basic Materials","RIO":"Basic Materials","FMG":"Basic Materials",
    "S32":"Basic Materials","MIN":"Basic Materials","VMM":"Basic Materials",
    "EUR":"Basic Materials","CUF":"Basic Materials","RMI":"Basic Materials",
    "MAH":"Basic Materials","MI6":"Basic Materials","LLM":"Basic Materials",
    "NWH":"Basic Materials","SHA":"Basic Materials","SNM":"Basic Materials",
    "IGO":"Basic Materials","PLS":"Basic Materials","DNL":"Basic Materials",
    "SKS":"Industrials","EOS":"Industrials","QUB":"Industrials",
    "AZJ":"Industrials","JGH":"Industrials","NWH":"Industrials",
    "CBA":"Financial Services","NAB":"Financial Services",
    "WBC":"Financial Services","ANZ":"Financial Services",
    "MQG":"Financial Services","MPL":"Financial Services",
    "IFL":"Financial Services","BBL":"Communication Services",
    "SLC":"Communication Services","TLC":"Consumer Cyclical",
    "WES":"Consumer Defensive","WOW":"Consumer Defensive",
    "COL":"Consumer Defensive","TCL":"Industrials",
    "APA":"Utilities","VNT":"Utilities",
    "CSL":"Healthcare","RMD":"Healthcare",
    "ELS":"Technology","XRO":"Technology",
    "TEA":"Basic Materials",
    # ── NSE ──────────────────────────────────────────────────────────────────
    "RELIANCE":"Energy","RELIANCE.NS":"Energy",
    "INFY":"Technology","INFY.NS":"Technology",
    "TCS":"Technology","TCS.NS":"Technology",
    "WIPRO":"Technology","WIPRO.NS":"Technology",
    "HDFCBANK":"Financial Services","HDFCBANK.NS":"Financial Services",
    "ICICIBANK":"Financial Services","ICICIBANK.NS":"Financial Services",
    "AXISBANK":"Financial Services","AXISBANK.NS":"Financial Services",
    "KOTAKBANK":"Financial Services","KOTAKBANK.NS":"Financial Services",
    "SBIN":"Financial Services","SBIN.NS":"Financial Services",
    "HDFC":"Financial Services","HDFC.NS":"Financial Services",
    "LT":"Industrials","LT.NS":"Industrials",
    "ITC":"Consumer Defensive","ITC.NS":"Consumer Defensive",
    "ASIANPAINT":"Basic Materials","ASIANPAINT.NS":"Basic Materials",
    "TITAN":"Consumer Cyclical","TITAN.NS":"Consumer Cyclical",
    "BAJAJFINSV":"Financial Services","BAJAJFINSV.NS":"Financial Services",
    "BAJFINANCE":"Financial Services","BAJFINANCE.NS":"Financial Services",
    "MARUTI":"Consumer Cyclical","MARUTI.NS":"Consumer Cyclical",
    "TATACONSUM":"Consumer Defensive","TATACONSUM.NS":"Consumer Defensive",
    "POLYCAB":"Industrials","POLYCAB.NS":"Industrials",
    "LAURUSLABS":"Healthcare","LAURUSLABS.NS":"Healthcare",
    "STLTECH":"Technology","STLTECH.NS":"Technology",
    "SYRMA":"Technology","SYRMA.NS":"Technology",
    "WELCORP":"Basic Materials","WELCORP.NS":"Basic Materials",
    "RRKABEL":"Industrials","RRKABEL.NS":"Industrials",
    # ── US ───────────────────────────────────────────────────────────────────
    "AAPL":"Technology","MSFT":"Technology","GOOGL":"Technology",
    "GOOG":"Technology","META":"Technology","NVDA":"Technology",
    "AMD":"Technology","INTC":"Technology","QCOM":"Technology",
    "AVGO":"Technology","CSCO":"Technology","IBM":"Technology",
    "AMAT":"Technology","LRCX":"Technology","MRVL":"Technology",
    "KEYS":"Technology","FTNT":"Technology","DDOG":"Technology",
    "MPWR":"Technology","LSCC":"Technology","FFIV":"Technology",
    "FLEX":"Technology","MXL":"Technology","ICHR":"Technology",
    "AMZN":"Consumer Cyclical","TSLA":"Consumer Cyclical",
    "DELL":"Technology","HPE":"Technology",
    "AMZN":"Consumer Cyclical","F":"Consumer Cyclical",
    "KO":"Consumer Defensive","CSX":"Industrials",
    "MU":"Technology","RKLB":"Industrials",
    "SPY":"ETF","QQQ":"ETF","TQQQ":"ETF","SOXL":"ETF",
    "XLF":"ETF","EEM":"ETF","IWM":"ETF","IEMG":"ETF",
    "SGOV":"ETF","HYG":"ETF","LQD":"ETF",
}


def _ticker_market(t):
    if t.endswith((".NS", ".BO")): return "NSE"
    if t.endswith(".AX"):          return "ASX"
    return "US"

def _strip(t):
    for s in (".NS", ".BO", ".AX"):
        if t.endswith(s): return t[:-len(s)]
    return t

def _row_bg(score):
    if score is None:  return ""
    if score >= 80:    return "s_strong"
    if score >= 60:    return "s_good"
    if score >= 40:    return "s_ok"
    if score >= 20:    return "s_weak"
    return                    "s_poor"

def _fetch_sector_yf(ticker: str) -> str:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return info.get("sector") or info.get("industry") or "Unknown"
    except Exception:
        return "Unknown"

def _load_sector_cache() -> dict:
    """Load JSON cache and merge with pre-seeded sectors (seed = fallback)."""
    cache = dict(SEED_SECTORS)          # start with seeds
    if os.path.exists(paths.SECTOR_CACHE):
        try:
            with open(paths.SECTOR_CACHE) as f:
                fetched = json.load(f)
            cache.update(fetched)       # yfinance results override seeds
        except Exception:
            pass
    return cache

def _save_sector_cache(cache: dict):
    try:
        with open(paths.SECTOR_CACHE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def calc_rs_df(stocks: dict) -> pd.DataFrame:
    """Build RS DataFrame from loaded stock dict {ticker: df}."""
    rows = []
    for ticker, df in stocks.items():
        close = df["CLOSE"].dropna()
        n     = len(close)
        row   = {"Ticker": ticker, "Market": _ticker_market(ticker)}

        for label, days in PERIODS.items():
            # Current return
            if n >= days + 1:
                row[f"ret_{label}"] = (float(close.iloc[-1]) /
                                       float(close.iloc[-days - 1]) - 1) * 100
            else:
                row[f"ret_{label}"] = None

            # 4-week-ago return (shifted back SHIFT bars)
            idx, idx0 = -1 - SHIFT, -1 - SHIFT - days
            if n >= abs(idx0):
                row[f"prev_{label}"] = (float(close.iloc[idx]) /
                                        float(close.iloc[idx0]) - 1) * 100
            else:
                row[f"prev_{label}"] = None

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df_all = pd.DataFrame(rows)

    for mkt, grp in df_all.groupby("Market"):
        idx = grp.index
        for label in PERIODS:
            for prefix, col_in, col_out in [
                ("",     f"ret_{label}",  f"RS_{label}"),
                ("prev", f"prev_{label}", f"pRS_{label}"),
            ]:
                valid = df_all.loc[idx, col_in].notna()
                if valid.sum() > 1:
                    df_all.loc[idx, col_out] = (
                        df_all.loc[idx, col_in]
                        .rank(pct=True, na_option="keep") * 100
                    ).round(1)
                else:
                    df_all.loc[idx, col_out] = None

    def composite(row, pfx="RS"):
        pairs = [(row.get(f"{pfx}_{l}"), w)
                 for l, w in WEIGHTS.items()
                 if row.get(f"{pfx}_{l}") is not None]
        if not pairs: return None
        tw = sum(w for _, w in pairs)
        return round(sum(v * w for v, w in pairs) / tw, 1)

    df_all["Composite"]  = df_all.apply(lambda r: composite(r, "RS"),  axis=1)
    df_all["pComposite"] = df_all.apply(lambda r: composite(r, "pRS"), axis=1)
    df_all["Momentum"]   = (df_all["Composite"] - df_all["pComposite"]).round(1)
    return df_all


class RsRankingsTab:

    def build(self, parent_nb, root):
        self.root          = root
        self._sector_cache = _load_sector_cache()
        self._rs_df        = pd.DataFrame()

        f = ttk.Frame(parent_nb)
        parent_nb.add(f, text="  RS Rankings  ")

        # ── Controls ───────────────────────────────────────────────────────
        ctrl = tk.Frame(f, bg="#ffffff", height=44)
        ctrl.pack(fill="x"); ctrl.pack_propagate(False)

        tk.Label(ctrl, text="RS Rankings", font=("Segoe UI", 10, "bold"),
                 bg="#ffffff", fg="#2C2C2A").pack(side="left", padx=12, pady=8)

        for lbl, var_name, values, default in [
            ("Market:", "_mkt_var",  ["All","NSE","ASX","US"], "All"),
            ("Sort:",   "_sort_var", ["Composite","Momentum","RS_12M",
                                      "RS_6M","RS_3M","RS_1M","MoneyFlow_Rank"],  "Composite"),
        ]:
            tk.Label(ctrl, text=lbl, font=("Segoe UI",9),
                     bg="#ffffff", fg="#888780").pack(side="left", padx=(10,2))
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            cb = ttk.Combobox(ctrl, textvariable=var,
                              values=values, state="readonly",
                              width=12 if "Sort" in lbl else 8)
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        self._status = tk.Label(ctrl, text="—", font=("Segoe UI",9),
                                bg="#ffffff", fg="#854F0B")
        self._status.pack(side="right", padx=12)

        # ── Paned: RS table (top) + Sector table (bottom) ─────────────────
        pw = tk.PanedWindow(f, orient="vertical", sashrelief="flat",
                            sashwidth=6, bg="#e8e6df")
        pw.pack(fill="both", expand=True)

        # ── TOP: RS table ──────────────────────────────────────────────────
        top = ttk.Frame(pw); pw.add(top, height=450)

        tk.Label(top, text="Multi-Period RS  ·  Composite  ·  Momentum",
                 font=("Segoe UI",9,"bold"), bg="#f1efe8", fg="#2C2C2A"
                 ).pack(fill="x", padx=4, pady=(4,0))

        cols = ("Rank","Ticker","Market","Sector",
                "RS_1M","RS_3M","RS_6M","RS_12M",
                "Composite","Momentum","mf_rank","Signal")
        self._tree = ttk.Treeview(top, columns=cols,
                                   show="headings", height=17)

        col_display = {
            "mf_rank": "MF Rank", "RS_1M": "RS 1M", "RS_3M": "RS 3M",
            "RS_6M": "RS 6M", "RS_12M": "RS 12M",
        }
        for col, w, anc in [
            ("Rank",80,"center"),("Ticker",75,"w"),("Market",55,"center"),
            ("Sector",140,"w"),("RS_1M",55,"center"),("RS_3M",55,"center"),
            ("RS_6M",55,"center"),("RS_12M",60,"center"),
            ("Composite",75,"center"),("Momentum",75,"center"),
            ("mf_rank",65,"center"),("Signal",95,"center"),
        ]:
            self._tree.heading(col, text=col_display.get(col, col),
                               command=lambda c=col: self._col_sort(c))
            self._tree.column(col, width=w, anchor=anc, stretch=False)

        for tag, bg in [
            ("s_strong","#C8E6C9"),("s_good","#EAF3DE"),
            ("s_ok","#FFF9C4"),("s_weak","#FAEEDA"),("s_poor","#FFCDD2"),
        ]:
            self._tree.tag_configure(tag, background=bg)

        sb_y = ttk.Scrollbar(top, command=self._tree.yview)
        sb_x = ttk.Scrollbar(top, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True, padx=4, pady=4)

        # ── BOTTOM: Sector table ───────────────────────────────────────────
        bot = ttk.Frame(pw); pw.add(bot, height=200)

        tk.Label(bot, text="Sector RS Rankings  (avg Composite per sector · market)",
                 font=("Segoe UI",9,"bold"), bg="#f1efe8", fg="#2C2C2A"
                 ).pack(fill="x", padx=4, pady=(4,0))

        scols = ("Rank","Sector","Market","Avg RS","# Stocks","Best","Worst")
        self._stree = ttk.Treeview(bot, columns=scols,
                                    show="headings", height=7)
        for col, w, anc in [
            ("Rank",45,"center"),("Sector",160,"w"),("Market",55,"center"),
            ("Avg RS",65,"center"),("# Stocks",65,"center"),
            ("Best",85,"w"),("Worst",85,"w"),
        ]:
            self._stree.heading(col, text=col)
            self._stree.column(col, width=w, anchor=anc, stretch=False)

        for tag, bg in [
            ("sec_top","#C8E6C9"),("sec_mid","#FFF9C4"),("sec_bot","#FFCDD2"),
        ]:
            self._stree.tag_configure(tag, background=bg)

        ssb = ttk.Scrollbar(bot, command=self._stree.yview)
        self._stree.configure(yscrollcommand=ssb.set)
        ssb.pack(side="right", fill="y")
        self._stree.pack(fill="both", expand=True, padx=4, pady=4)

    # ── Populate ──────────────────────────────────────────────────────────────

    def populate(self, stocks: dict, benchmarks: dict = None):
        if not stocks:
            self._status.config(text="No stocks", fg="#A32D2D"); return
        self._status.config(text="Calculating…", fg="#854F0B")

        def _work():
            df = calc_rs_df(stocks)

            # ── MoneyFlow percentile rank within market ────────────────────
            mf_rows = []
            for ticker, sdf in stocks.items():
                try:
                    mf = float((sdf["CLOSE"] * sdf["VOLUME"]).rolling(20).mean().iloc[-1])
                except Exception:
                    mf = 0.0
                mf_rows.append({"Ticker": ticker, "_mf": mf})
            mf_df = pd.DataFrame(mf_rows)
            df = df.merge(mf_df, on="Ticker", how="left")
            for mkt, grp in df.groupby("Market"):
                idx   = grp.index
                valid = df.loc[idx, "_mf"].notna() & (df.loc[idx, "_mf"] > 0)
                if valid.sum() > 1:
                    df.loc[idx, "MoneyFlow_Rank"] = (
                        df.loc[idx, "_mf"]
                        .rank(pct=True, na_option="keep") * 100
                    ).round(0)
                else:
                    df.loc[idx, "MoneyFlow_Rank"] = None
            df = df.drop(columns=["_mf"], errors="ignore")

            # ── Sector lookup ─────────────────────────────────────────────
            df["Sector"] = df["Ticker"].apply(
                lambda t: self._sector_cache.get(t)
                       or self._sector_cache.get(_strip(t))
                       or "Unknown"
            )
            self._rs_df = df
            self.root.after(0, self._refresh)

            missing = [t for t in df["Ticker"]
                       if self._sector_cache.get(t) in (None, "Unknown")
                       and self._sector_cache.get(_strip(t)) in (None, "Unknown")]
            if missing:
                threading.Thread(
                    target=self._bg_sectors, args=(missing,), daemon=True
                ).start()

        threading.Thread(target=_work, daemon=True).start()

    def _refresh(self):
        df  = self._rs_df
        if df.empty: return
        mkt = self._mkt_var.get()
        if mkt != "All":
            df = df[df["Market"] == mkt]
        srt = self._sort_var.get()
        df  = df.sort_values(srt, ascending=False, na_position="last"
                             ).reset_index(drop=True)
        self._fill_rs(df)
        self._fill_sectors(df)
        self._status.config(
            text=f"{len(df)} stocks · {self._mkt_var.get()}",
            fg="#3B6D11")

    def _fill_rs(self, df):
        for it in self._tree.get_children(): self._tree.delete(it)
        for rank, (_, row) in enumerate(df.iterrows(), 1):
            comp = row.get("Composite")
            mom  = row.get("Momentum")

            if comp is None:   sig = "—"
            elif comp >= 80:   sig = "🔥 Leader"
            elif comp >= 60:   sig = "✅ Strong"
            elif comp >= 40:   sig = "⚠ Average"
            else:              sig = "❌ Weak"

            mom_s = ("—" if mom is None else
                     f"+{mom:.1f}" if mom >= 0 else f"{mom:.1f}")

            fmt = lambda v: f"{v:.0f}" if v is not None else "—"

            self._tree.insert("", "end", tags=(_row_bg(comp),), values=(
                rank, _strip(row["Ticker"]), row["Market"],
                row.get("Sector","—").replace("Unknown","—"),
                fmt(row.get("RS_1M")),  fmt(row.get("RS_3M")),
                fmt(row.get("RS_6M")),  fmt(row.get("RS_12M")),
                fmt(comp), mom_s, fmt(row.get("MoneyFlow_Rank")), sig,
            ))

    def _fill_sectors(self, df):
        for it in self._stree.get_children():
            self._stree.delete(it)

        if "Sector" not in df.columns or df.empty:
            return

        # Only rows with a known sector and valid Composite
        valid = df[
            (df["Sector"] != "Unknown") &
            (df["Composite"].notna())
        ].copy()

        if valid.empty:
            return

        # Build sector summary manually — avoids idxmax/idxmin NaN issues
        rows = []
        for (sector, mkt), grp in valid.groupby(["Sector", "Market"]):
            grp_sorted = grp.sort_values("Composite", ascending=False)
            n      = len(grp_sorted)
            avg    = grp_sorted["Composite"].mean()
            best   = _strip(grp_sorted.iloc[0]["Ticker"])
            worst  = _strip(grp_sorted.iloc[-1]["Ticker"]) if n > 1 else "—"
            sector_label = sector + (" (solo)" if n == 1 else "")
            rows.append({
                "sector": sector_label, "mkt": mkt,
                "avg": avg, "n": n, "best": best, "worst": worst,
            })

        if not rows:
            return

        rows.sort(key=lambda r: r["avg"], reverse=True)
        n_total = len(rows)

        for rank, r in enumerate(rows, 1):
            pct = rank / n_total
            tag = "sec_top" if pct <= 0.25 else (
                  "sec_bot" if pct > 0.75 else "sec_mid")
            self._stree.insert("", "end", tags=(tag,), values=(
                rank, r["sector"], r["mkt"],
                f"{r['avg']:.0f}", r["n"], r["best"], r["worst"],
            ))

    def _col_sort(self, col):
        sort_map = {"mf_rank": "MoneyFlow_Rank"}
        sort_col = sort_map.get(col, col)
        valid = list(WEIGHTS.keys()) + ["Composite","Momentum","RS_1M",
                                         "RS_3M","RS_6M","RS_12M","MoneyFlow_Rank"]
        if sort_col in valid:
            self._sort_var.set(sort_col)
            self._refresh()

    def _bg_sectors(self, tickers):
        import time
        updated = False
        for t in tickers[:60]:
            sec = _fetch_sector_yf(t)
            if sec and sec != "Unknown":
                self._sector_cache[t] = sec
                self._sector_cache[_strip(t)] = sec
                updated = True
            time.sleep(0.4)
        if updated:
            _save_sector_cache(self._sector_cache)
            df = self._rs_df.copy()
            df["Sector"] = df["Ticker"].apply(
                lambda t: self._sector_cache.get(t)
                       or self._sector_cache.get(_strip(t))
                       or "Unknown"
            )
            self._rs_df = df
            self.root.after(0, self._refresh)

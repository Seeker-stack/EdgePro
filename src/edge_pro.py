import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
edge_pro.py
-----------
Edge Pro — Professional Positional Trading System
Reads exclusively from local CSVs in C:\\StockData\\
Never calls yfinance at runtime.

Requirements:
    uv add pandas ta matplotlib pillow tkcalendar

Run:
    uv run edge_pro.py
"""

import os
import threading
import queue
from datetime import date, datetime

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ta

# TradingView client (uses yfinance, always available)
import paths
import theme
from tradingview_client import TradingViewClient
from rs_rankings_module import RsRankingsTab
from volume_module import VolumeAnalyser, batch_vcs

# ── Paths ─────────────────────────────────────────────────────────────────────

# Paths now managed via paths.py
BASE_DIR     = paths.ROOT
BENCH_DIR    = paths.BENCH_DIR
SUMMARY_FILE = paths.SUMMARY_FILE

BENCHMARK_MAP = {
    ".NS": ("NSEI",  "Nifty 50"),
    ".BO": ("NSEI",  "Nifty 50"),
    ".AX": ("AXJO",  "ASX 200"),
    "":    ("GSPC",  "S&P 500"),
}

BANKING_TICKERS = {
    "HDFCBANK.NS","ICICIBANK.NS","AXISBANK.NS","SBIN.NS",
    "KOTAKBANK.NS","INDUSINDBK.NS","BANDHANBNK.NS",
    "FEDERALBNK.NS","IDFCFIRSTB.NS",
}

DAYS = 55

# ── Pure functions ────────────────────────────────────────────────────────────

def get_suffix(t):
    return ("." + t.split(".")[-1]) if "." in t else ""

def get_bench(ticker):
    if ticker in BANKING_TICKERS:
        return "NSEBANK", "Bank Nifty"
    return BENCHMARK_MAP.get(get_suffix(ticker), ("GSPC", "S&P 500"))

def load_csv(path):
    try:
        df = pd.read_csv(path, parse_dates=["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        return df if len(df) >= 20 else None
    except Exception:
        return None

def load_stocks():
    """Load all stock CSVs from data/nse, data/asx, data/us."""
    out = {}
    for data_dir in paths.ALL_DATA_DIRS:
        if not os.path.isdir(data_dir):
            continue
        for f in os.listdir(data_dir):
            if f.endswith(".csv"):
                df = load_csv(os.path.join(data_dir, f))
                if df is not None:
                    out[f.replace(".csv", "")] = df
    return out

def load_benchmarks():
    """Load benchmark CSVs from data/benchmarks/."""
    out = {}
    if not os.path.isdir(paths.BENCH_DIR):
        return out
    for f in os.listdir(paths.BENCH_DIR):
        if f.endswith(".csv"):
            df = load_csv(os.path.join(paths.BENCH_DIR, f))
            if df is not None:
                out[f.replace(".csv", "")] = df
    return out

def load_summary():
    info = {}
    if os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE) as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v
    return info

def indicators(df):
    df = df.copy()
    df["RSI"]    = ta.momentum.RSIIndicator(df["CLOSE"], 14).rsi()
    df["ADX"]    = ta.trend.ADXIndicator(df["HIGH"], df["LOW"], df["CLOSE"], 14).adx()
    df["EMA21"]  = df["CLOSE"].ewm(span=21,  adjust=False).mean()
    df["EMA55"]  = df["CLOSE"].ewm(span=55,  adjust=False).mean()
    df["EMA150"] = df["CLOSE"].ewm(span=150, adjust=False).mean()
    df["EMA200"] = df["CLOSE"].ewm(span=200, adjust=False).mean()
    df["ATH"]    = df["CLOSE"].expanding().max()
    return df

def rs_score(sdf, bdf):
    if bdf is None:
        return None
    try:
        s = sdf["CLOSE"].dropna().tail(DAYS+1)
        b = bdf["CLOSE"].dropna().tail(DAYS+1)
        if len(s) < 10 or len(b) < 10:
            return None
        sr = s.iloc[-1]/s.iloc[0] - 1
        br = b.iloc[-1]/b.iloc[0] - 1
        if br == 0:
            return None
        return min(99, max(1, round(50 + (sr/abs(br))*25)))
    except Exception:
        return None

def rs_line(sdf, bdf):
    if bdf is None:
        return None
    try:
        s = sdf[["Date","CLOSE"]].tail(DAYS+5).copy()
        b = bdf[["Date","CLOSE"]].tail(DAYS+5).rename(columns={"CLOSE":"BENCH"})
        m = pd.merge_asof(s.sort_values("Date"), b.sort_values("Date"), on="Date")
        m = m.dropna().tail(DAYS)
        if len(m) < 5:
            return None
        m["RS_norm"]    = (m["CLOSE"]/m["BENCH"]) / (m["CLOSE"].iloc[0]/m["BENCH"].iloc[0])
        m["STK_norm"]   = m["CLOSE"] / m["CLOSE"].iloc[0]
        m["BENCH_norm"] = m["BENCH"] / m["BENCH"].iloc[0]
        return m
    except Exception:
        return None

def ath_label(df):
    c   = df["CLOSE"].dropna()
    cur = float(c.iloc[-1])
    ath = float(c.max())
    h52 = float(c.tail(252).max())
    p   = (1 - cur/ath)*100 if ath > 0 else 100
    p52 = (1 - cur/h52)*100 if h52 > 0 else 100
    if p <= 2:   return "ATH"
    if p <= 10:  return f"{p:.1f}% ATH"
    return f"{p52:.1f}% 52W"

def sig_tag(rsi, adx):
    if rsi > 60 and adx > 28: return "strong"
    if rsi > 55 and adx > 22: return "watch"
    return "neutral"

def to_photo(fig):
    from PIL import Image, ImageTk
    fig.canvas.draw()
    img = Image.frombuffer("RGBA", fig.canvas.get_width_height(),
                           fig.canvas.buffer_rgba())
    return ImageTk.PhotoImage(img)

# ── Style ─────────────────────────────────────────────────────────────────────

# Chart colours — aligned with theme.P palette
C = dict(
    bg   = "#FFFFFF",       # chart face
    ax   = "#F8FAFC",       # axes background
    grid = "#E2E8F0",       # grid lines
    blue = "#1D4ED8",       # price line / primary
    grn  = "#15803D",       # bullish / positive
    red  = "#B91C1C",       # bearish / negative
    amb  = "#B45309",       # amber / warning
    gry  = "#94A3B8",       # muted / neutral
    txt  = "#0F172A",       # axis text
)

def axs(ax, title=""):
    ax.set_facecolor(C["ax"])
    ax.tick_params(colors=C["gry"], labelsize=8, length=0)
    ax.spines[["top","right"]].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(C["grid"])
    ax.grid(True, color=C["grid"], lw=0.4, ls="-", alpha=0.7)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=9, fontweight="600",
                     color=C["txt"], pad=8, loc="left")


# ══════════════════════════════════════════════════════════════════════════════

class EdgePro:
    def __init__(self, root):
        self.root = root
        self.stocks = {}
        self.benchmarks = {}
        self._p = {}           # PhotoImage refs

        root.title("Edge Pro — Positional Trading System")
        root.geometry("1400x860")
        theme.apply(root)   # apply global theme

        self._ui()
        self._load_async()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _ui(self):
        # ── Themed header ─────────────────────────────────────────────────
        self._hdr = theme.Header(self.root)
        # Back-compat shims so _post() can still call self._st / self._lr
        self._st = self._hdr._status_lbl
        self._lr = self._hdr._lastrun_lbl

        self._nb = ttk.Notebook(self.root)
        self._nb.pack(fill="both", expand=True)

        self._tab_dash()
        self._tab_scr()
        self._tab_rs()
        self._tab_risk()
        self._tab_nightly()
        self._tab_tradingview()
        self._tab_rs_rankings()
        self._tab_pricevol()

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _tab_dash(self):
        f = ttk.Frame(self._nb); self._nb.add(f, text="  📊  Dashboard  ")

        L = tk.Frame(f, bg="#ffffff", width=240)
        L.pack(side="left", fill="y"); L.pack_propagate(False)
        R = tk.Frame(f, bg=theme.P["body_bg"])
        R.pack(side="left", fill="both", expand=True)

        hdr = tk.Frame(L, bg="#ffffff"); hdr.pack(fill="x")
        tk.Label(hdr, text="Watchlist", font=("Segoe UI",10,"bold"),
                 bg="#ffffff", fg="#2C2C2A").pack(side="left", padx=12, pady=8)
        tk.Button(hdr, text="Refresh ↻", font=("Segoe UI",8),
                  bg="#EAF3DE", fg="#27500A", relief="flat",
                  command=self._load_async).pack(side="right", padx=8)

        fb = tk.Frame(L, bg=theme.P["body_bg"]); fb.pack(fill="x", padx=8, pady=(0,4))
        tk.Label(fb, text="Filter:", font=("Segoe UI",8),
                 bg=theme.P["body_bg"], fg="#888780").pack(side="left")
        self._wlf = tk.StringVar()
        tk.Entry(fb, textvariable=self._wlf, font=("Segoe UI",8),
                 width=14, relief="solid", bd=1).pack(side="left", padx=4)
        self._wlf.trace_add("write", lambda *_: self._pop_wl())

        tk.Frame(L, bg=theme.P["border"], height=1).pack(fill="x")

        cols = ("sym","near","rsi","adx","rs","sig")
        self._wl = ttk.Treeview(L, columns=cols, show="headings",
                                  selectmode="browse")
        for col, txt, w in [("sym","Ticker",72),("near","Level",54),
                              ("rsi","RSI",40),("adx","ADX",40),
                              ("rs","RS",36),("sig","Signal",54)]:
            self._wl.heading(col, text=txt)
            self._wl.column(col, width=w, anchor="center")
        self._wl.tag_configure("strong", background="#EAF3DE")
        self._wl.tag_configure("watch",  background="#FAEEDA")
        sb = ttk.Scrollbar(L, command=self._wl.yview)
        self._wl.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._wl.pack(fill="both", expand=True)
        self._wl.bind("<<TreeviewSelect>>", lambda _: self._wl_sel())

        mrow = tk.Frame(R, bg="#ffffff", height=60)
        mrow.pack(fill="x"); mrow.pack_propagate(False)
        self._ch = {}
        for key, lbl in [("ticker","Ticker"),("close","Last Close"),
                          ("ath","From ATH"),("rs","RS Score"),
                          ("rsi","RSI"),("adx","ADX"),("stage","Stage")]:
            m = tk.Frame(mrow, bg=theme.P["body_bg"])
            m.pack(side="left", padx=6, pady=8, ipadx=8, ipady=4)
            tk.Label(m, text=lbl, font=("Segoe UI",8),
                     bg=theme.P["body_bg"], fg="#888780").pack()
            v = tk.Label(m, text="—", font=("Segoe UI",11,"bold"),
                         bg=theme.P["body_bg"], fg="#2C2C2A")
            v.pack()
            self._ch[key] = v

        self._dc = tk.Canvas(R, bg=theme.P["body_bg"], highlightthickness=0)
        self._dc.pack(fill="both", expand=True, padx=8, pady=(0,8))

    def _wl_sel(self):
        s = self._wl.selection()
        if s: self._dash(self._wl.item(s[0])["values"][0])

    def _dash(self, ticker):
        df = self.stocks.get(ticker)
        if df is None: return
        df  = indicators(df)
        row = df.iloc[-1]
        rsi  = float(row.get("RSI",0)   or 0)
        adx  = float(row.get("ADX",0)   or 0)
        e21  = float(row.get("EMA21",0) or 0)
        e55  = float(row.get("EMA55",0) or 0)
        e150 = float(row.get("EMA150",0)or 0)
        cl   = float(row["CLOSE"])
        bk, bl = get_bench(ticker)
        bdf  = self.benchmarks.get(bk)
        rs   = rs_score(df, bdf)
        stage = "Stage 2" if cl > e21 > e55 > e150 else "Basing"

        self._ch["ticker"].config(
            text=ticker.replace(".NS","").replace(".AX",""))
        self._ch["close"].config(text=f"{cl:.3f}")
        self._ch["ath"].config(text=ath_label(df))
        self._ch["rs"].config(text=str(rs) if rs else "N/A",
            fg=C["grn"] if (rs and rs>=70) else C["red"])
        self._ch["rsi"].config(text=f"{rsi:.1f}",
            fg=C["grn"] if rsi>55 else C["red"])
        self._ch["adx"].config(text=f"{adx:.1f}",
            fg=C["grn"] if adx>26 else C["gry"])
        self._ch["stage"].config(text=stage)
        self._draw_dash(ticker, df, bdf, bl)

    def _draw_dash(self, ticker, df, bdf, bl):
        try:
            w = max(self._dc.winfo_width(), 600)
            h = max(self._dc.winfo_height(), 360)
            fig = plt.figure(figsize=(w/96, h/96), dpi=96, facecolor=C["bg"])
            gs  = GridSpec(3,1,figure=fig,hspace=0.45,top=0.93,bottom=0.1)

            ax1 = fig.add_subplot(gs[0:2,0])
            t   = df.tail(120)
            ax1.plot(t["Date"], t["CLOSE"], color=C["blue"], lw=1.4, label="Price")
            for col, clr, lbl in [("EMA21",C["grn"],"EMA21"),
                                   ("EMA55",C["amb"],"EMA55"),
                                   ("EMA150",C["red"],"EMA150")]:
                if col in t.columns:
                    ax1.plot(t["Date"], t[col], color=clr,
                             lw=0.8, ls="--", alpha=0.7, label=lbl)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            fig.autofmt_xdate(rotation=30, ha="right")
            ax1.legend(fontsize=7, loc="upper left", framealpha=0.7)
            axs(ax1, f"{ticker}  —  Daily Price + EMA")

            ax2 = fig.add_subplot(gs[2,0])
            rd  = rs_line(df, bdf)
            if rd is not None:
                clr = C["grn"] if rd["RS_norm"].iloc[-1] >= rd["RS_norm"].iloc[0] else C["red"]
                ax2.plot(rd["Date"], rd["RS_norm"], color=clr, lw=1.4)
                ax2.axhline(1.0, color=C["gry"], lw=0.7, ls=":")
                ax2.fill_between(rd["Date"], rd["RS_norm"], 1.0,
                                 where=(rd["RS_norm"]>=1.0), alpha=0.12, color=C["grn"])
                ax2.fill_between(rd["Date"], rd["RS_norm"], 1.0,
                                 where=(rd["RS_norm"]<1.0),  alpha=0.12, color=C["red"])
                ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            axs(ax2, f"RS Line — {ticker} vs {bl} (55d)")

            ph = to_photo(fig)
            self._dc.delete("all")
            self._dc.create_image(0,0, anchor="nw", image=ph)
            self._p["dash"] = ph
            plt.close(fig)
        except Exception as e:
            print(f"[Dash] {e}")

    def _pop_wl(self):
        for r in self._wl.get_children(): self._wl.delete(r)
        flt = self._wlf.get().upper()
        rows = []
        for sym, df in self.stocks.items():
            if flt and flt not in sym.upper(): continue
            df  = indicators(df)
            row = df.iloc[-1]
            rsi = float(row.get("RSI",0) or 0)
            adx = float(row.get("ADX",0) or 0)
            bk, _ = get_bench(sym)
            rs  = rs_score(df, self.benchmarks.get(bk))
            tag = sig_tag(rsi, adx)
            rows.append((sym, ath_label(df),
                         f"{rsi:.1f}", f"{adx:.1f}",
                         str(rs) if rs else "—",
                         tag.title(), tag))
        rows.sort(key=lambda r: int(r[4]) if r[4].isdigit() else 0, reverse=True)
        for r in rows:
            self._wl.insert("", "end", values=r[:-1], tags=(r[-1],))

    # ── Screener ──────────────────────────────────────────────────────────────

    def _tab_scr(self):
        f = ttk.Frame(self._nb); self._nb.add(f, text="  🔍  Screener  ")

        fb = tk.Frame(f, bg="#ffffff"); fb.pack(fill="x")
        tk.Label(fb, text="Template:", font=("Segoe UI",9),
                 bg="#ffffff").pack(side="left", padx=8, pady=8)
        self._tmpl = tk.StringVar(value="Near ATH + Momentum")
        ttk.Combobox(fb, textvariable=self._tmpl, width=22, state="readonly",
                     values=["Minervini Stage 2","VCP Setup","CAN SLIM",
                             "Near ATH + Momentum","All"]).pack(side="left", padx=4)

        tk.Label(fb, text="Min RS:",  font=("Segoe UI",9), bg="#ffffff").pack(side="left", padx=(12,4))
        self._mRS  = tk.StringVar(value="0")
        tk.Entry(fb, textvariable=self._mRS,  width=5, font=("Segoe UI",9)).pack(side="left")

        tk.Label(fb, text="Min RSI:", font=("Segoe UI",9), bg="#ffffff").pack(side="left", padx=(12,4))
        self._mRSI = tk.StringVar(value="0")
        tk.Entry(fb, textvariable=self._mRSI, width=5, font=("Segoe UI",9)).pack(side="left")

        tk.Button(fb, text="Run Screener", font=("Segoe UI",9,"bold"),
                  bg="#185FA5", fg="#ffffff", relief="flat",
                  cursor="hand2", padx=12, pady=4,
                  command=self._scr_run).pack(side="left", padx=16)
        self._scr_lbl = tk.Label(fb, text="", font=("Segoe UI",9),
                                  bg="#ffffff", fg="#854F0B")
        self._scr_lbl.pack(side="left", padx=8)
        tk.Button(fb, text="Export CSV", font=("Segoe UI",9),
                  bg=theme.P["body_bg"], relief="flat", cursor="hand2",
                  padx=8, pady=4, command=self._scr_export).pack(side="right", padx=8)

        tk.Frame(f, bg=theme.P["border"], height=1).pack(fill="x")

        cols   = ("ticker","market","close","ath","rsi","adx","ema",
                  "rs","vol","setup","rr","signal")
        hdrs   = ("Ticker","Market","Close","Level","RSI","ADX",
                  "EMA Stack","RS","Vol×","Setup","Est R:R","Signal")
        widths = (90,60,74,66,46,46,82,42,50,120,58,72)

        tf = tk.Frame(f, bg="#ffffff"); tf.pack(fill="both", expand=True)
        self._scr = ttk.Treeview(tf, columns=cols, show="headings",
                                   selectmode="browse")
        for col, hdr, w in zip(cols, hdrs, widths):
            self._scr.heading(col, text=hdr,
                command=lambda c=col: self._sort(self._scr, c, False))
            self._scr.column(col, width=w, anchor="center")
        self._scr.tag_configure("strong", background="#EAF3DE")
        self._scr.tag_configure("watch",  background="#FAEEDA")
        vsb = ttk.Scrollbar(tf, command=self._scr.yview)
        self._scr.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._scr.pack(fill="both", expand=True)
        self._scr.bind("<<TreeviewSelect>>", lambda _: self._scr_sel())

    def _scr_run(self):
        for r in self._scr.get_children(): self._scr.delete(r)
        try:
            min_rs  = float(self._mRS.get()  or 0)
            min_rsi = float(self._mRSI.get() or 0)
        except ValueError:
            min_rs = min_rsi = 0
        tmpl = self._tmpl.get()
        rows = []

        for sym, raw in self.stocks.items():
            try:
                df   = indicators(raw)
                row  = df.iloc[-1]
                rsi  = float(row.get("RSI",0)   or 0)
                adx  = float(row.get("ADX",0)   or 0)
                cl   = float(row["CLOSE"])
                e21  = float(row.get("EMA21",0) or 0)
                e55  = float(row.get("EMA55",0) or 0)
                e150 = float(row.get("EMA150",0)or 0)
                e200 = float(row.get("EMA200",0)or 0)
                avg_v = float(df["VOLUME"].rolling(20).mean().iloc[-1] or 1)
                vmul  = round(float(row["VOLUME"]) / avg_v, 1)

                bk, _ = get_bench(sym)
                rs    = rs_score(df, self.benchmarks.get(bk))
                rv    = rs if rs is not None else 0
                rs_ok = (rv >= min_rs) if min_rs > 0 else True

                ema_ok  = bool(cl > e21 > e55 > e150 > e200)
                ema_tag = "Aligned" if ema_ok else ("Partial" if cl > e21 else "Broken")

                if tmpl == "Minervini Stage 2":
                    ok = rsi>55 and adx>26 and ema_ok and rs_ok and rsi>=min_rsi
                elif tmpl == "VCP Setup":
                    atr_pct = float(df["CLOSE"].diff().abs().rolling(14).mean().iloc[-1])/cl*100
                    ok = ema_ok and atr_pct<4.0 and vmul<0.8 and rs_ok
                elif tmpl == "CAN SLIM":
                    h52 = float(df["CLOSE"].tail(252).max())
                    ok  = cl>=h52*0.9 and rsi>55 and rs_ok and ema_ok
                elif tmpl == "Near ATH + Momentum":
                    ath = float(df["CLOSE"].max())
                    ok  = cl>=ath*0.90 and rsi>52 and adx>20 and rsi>=min_rsi
                else:
                    ok = True

                if not ok: continue

                atr14 = float(df["CLOSE"].diff().abs().rolling(14).mean().iloc[-1])
                sl    = round(cl - atr14*2, 4)
                tgt   = round(cl + atr14*4, 4)
                rr    = round((tgt-cl)/(cl-sl), 1) if (cl-sl)>0 else 0
                mkt   = "NSE" if sym.endswith(".NS") else \
                        "BSE" if sym.endswith(".BO") else \
                        "ASX" if sym.endswith(".AX") else "US"
                tag   = sig_tag(rsi, adx)
                rows.append((sym, mkt, f"{cl:.3f}", ath_label(df),
                             f"{rsi:.1f}", f"{adx:.1f}", ema_tag,
                             str(rs) if rs else "—", f"{vmul:.1f}×",
                             tmpl, f"{rr}:1", tag.title(), tag))
            except Exception as e:
                print(f"[Scr] {sym}: {e}")

        rows.sort(key=lambda r: int(r[7]) if r[7].isdigit() else 0, reverse=True)
        for r in rows:
            self._scr.insert("", "end", values=r[:-1], tags=(r[-1],))
        self._scr_lbl.config(
            text=f"{len(rows)} results  ({len(self.stocks)} loaded)")

    def _scr_sel(self):
        s = self._scr.selection()
        if s:
            self._nb.select(0)
            self._dash(self._scr.item(s[0])["values"][0])

    def _scr_export(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".csv", initialdir=paths.EXPORT_DIR,
            filetypes=[("CSV","*.csv")])
        if not p: return
        rows = [self._scr.item(r)["values"] for r in self._scr.get_children()]
        cols = ("Ticker","Market","Close","Level","RSI","ADX","EMA Stack",
                "RS","Vol×","Setup","Est R:R","Signal")
        pd.DataFrame(rows, columns=cols).to_csv(p, index=False)
        messagebox.showinfo("Exported", f"Saved:\n{p}")

    # ── RS Analyser ───────────────────────────────────────────────────────────

    def _tab_rs(self):
        f = ttk.Frame(self._nb); self._nb.add(f, text="  📈  RS Analyser  ")
        sub = ttk.Notebook(f); sub.pack(fill="both", expand=True)
        self._rsnb = sub
        self._rs_stock_tab(sub)
        self._rs_matrix_tab(sub)
        self._rs_comm_tab(sub)

    def _rs_stock_tab(self, sub):
        f = ttk.Frame(sub); sub.add(f, text="  Stock RS  ")

        # LEFT listbox
        L = tk.Frame(f, bg="#ffffff", width=200)
        L.pack(side="left", fill="y"); L.pack_propagate(False)
        tk.Label(L, text="Select stock", font=("Segoe UI",9,"bold"),
                 bg="#ffffff", fg="#2C2C2A").pack(anchor="w", padx=10, pady=(8,4))

        lbf = tk.Frame(L, bg="#ffffff")
        lbf.pack(fill="both", expand=True, padx=(8,0), pady=(0,8))
        self._rslb = tk.Listbox(lbf, font=("Segoe UI",9),
                                  selectmode="browse", exportselection=False,
                                  activestyle="dotbox")
        sb = ttk.Scrollbar(lbf, command=self._rslb.yview)
        self._rslb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._rslb.pack(side="left", fill="both", expand=True)
        self._rslb.bind("<<ListboxSelect>>", lambda _: self._rs_sel())
        self._rslb.bind("<ButtonRelease-1>",  lambda _: self._rs_sel())

        # RIGHT
        R = tk.Frame(f, bg=theme.P["body_bg"]); R.pack(fill="both", expand=True)
        chips = tk.Frame(R, bg="#ffffff"); chips.pack(fill="x")
        self._rsc = {}
        for key, lbl in [("ticker","Ticker"),("bench","Benchmark"),
                          ("score","RS Score"),("alpha","Alpha"),
                          ("trend","RS Trend"),("ret","55d Return"),
                          ("bret","Bench Return")]:
            c = tk.Frame(chips, bg=theme.P["body_bg"])
            c.pack(side="left", padx=6, pady=8, ipadx=6, ipady=3)
            tk.Label(c, text=lbl, font=("Segoe UI",8),
                     bg=theme.P["body_bg"], fg="#888780").pack()
            v = tk.Label(c, text="—", font=("Segoe UI",10,"bold"),
                         bg=theme.P["body_bg"], fg="#2C2C2A"); v.pack()
            self._rsc[key] = v

        self._rsc_canvas = tk.Canvas(R, bg=theme.P["body_bg"], highlightthickness=0)
        self._rsc_canvas.pack(fill="both", expand=True, padx=8, pady=(0,8))

    def _rs_sel(self):
        sel = self._rslb.curselection()
        if not sel: return
        ticker = self._rslb.get(sel[0])
        df = self.stocks.get(ticker)
        if df is None: return
        df = indicators(df)
        bk, bl = get_bench(ticker)
        bdf = self.benchmarks.get(bk)
        rs  = rs_score(df, bdf)
        rd  = rs_line(df, bdf)

        if rd is not None:
            sr = round((rd["CLOSE"].iloc[-1]/rd["CLOSE"].iloc[0]-1)*100, 1)
            br = round((rd["BENCH"].iloc[-1] /rd["BENCH"].iloc[0] -1)*100, 1)
            al = round(sr-br, 1)
            up = rd["RS_norm"].iloc[-1] > rd["RS_norm"].iloc[0]
        else:
            sr = br = al = 0; up = False

        self._rsc["ticker"].config(text=ticker)
        self._rsc["bench"].config(text=bl)
        self._rsc["score"].config(text=str(rs) if rs else "—",
            fg=C["grn"] if (rs and rs>=70) else C["red"])
        self._rsc["alpha"].config(text=f"{al:+.1f}%",
            fg=C["grn"] if al>=0 else C["red"])
        self._rsc["trend"].config(text="Rising" if up else "Falling",
            fg=C["grn"] if up else C["red"])
        self._rsc["ret"].config(text=f"{sr:+.1f}%",
            fg=C["grn"] if sr>=0 else C["red"])
        self._rsc["bret"].config(text=f"{br:+.1f}%")
        self._draw_rs(ticker, df, bdf, bl, rd)

    def _draw_rs(self, ticker, df, bdf, bl, rd):
        try:
            w = max(self._rsc_canvas.winfo_width(), 600)
            h = max(self._rsc_canvas.winfo_height(), 380)
            fig = plt.figure(figsize=(w/96,h/96), dpi=96, facecolor=C["bg"])
            gs  = GridSpec(3,1,figure=fig,hspace=0.5,top=0.93,bottom=0.08)

            ax1 = fig.add_subplot(gs[0:2,0])
            if rd is not None:
                ax1.plot(rd["Date"], rd["STK_norm"]*100,
                         color=C["blue"], lw=1.6, label=ticker)
                ax1.plot(rd["Date"], rd["BENCH_norm"]*100,
                         color=C["gry"], lw=1.0, ls="--", alpha=0.8, label=bl)
                ax1.axhline(100, color=C["gry"], lw=0.5, ls=":")
            ax1.legend(fontsize=8)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            axs(ax1, f"{ticker} vs {bl} — Normalised (55d)")

            ax2 = fig.add_subplot(gs[2,0])
            if rd is not None:
                up  = rd["RS_norm"].iloc[-1] >= rd["RS_norm"].iloc[0]
                clr = C["grn"] if up else C["red"]
                ax2.plot(rd["Date"], rd["RS_norm"], color=clr, lw=1.6)
                ax2.axhline(1.0, color=C["gry"], lw=0.7, ls=":")
                ax2.fill_between(rd["Date"], rd["RS_norm"], 1.0,
                                 where=(rd["RS_norm"]>=1.0), alpha=0.15, color=C["grn"])
                ax2.fill_between(rd["Date"], rd["RS_norm"], 1.0,
                                 where=(rd["RS_norm"]<1.0),  alpha=0.15, color=C["red"])
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            axs(ax2, f"RS Ratio Line — {ticker} / {bl}")

            ph = to_photo(fig)
            self._rsc_canvas.delete("all")
            self._rsc_canvas.create_image(0,0, anchor="nw", image=ph)
            self._p["rs"] = ph
            plt.close(fig)
        except Exception as e:
            print(f"[RS] {e}")

    def _pop_rslb(self):
        self._rslb.delete(0,"end")
        for sym in sorted(self.stocks):
            self._rslb.insert("end", sym)

    def _rs_matrix_tab(self, sub):
        f = ttk.Frame(sub); sub.add(f, text="  Market Matrix  ")
        tk.Button(f, text="Refresh Matrix", font=("Segoe UI",9,"bold"),
                  bg="#185FA5", fg="#ffffff", relief="flat",
                  cursor="hand2", padx=12, pady=4,
                  command=self._draw_matrix).pack(anchor="w", padx=12, pady=8)
        self._mc = tk.Canvas(f, bg=theme.P["body_bg"], highlightthickness=0)
        self._mc.pack(fill="both", expand=True, padx=8, pady=(0,8))

    def _draw_matrix(self):
        LABELS = {"NSEI":"Nifty 50","NSEBANK":"Bank Nifty","GSPC":"S&P 500",
                  "IXIC":"Nasdaq","AXJO":"ASX 200","FTSE":"FTSE 100",
                  "N225":"Nikkei","BTCUSD":"BTC/USD","GOLD":"Gold","DXY":"DXY"}
        keys   = [k for k in LABELS if k in self.benchmarks]
        labels = [LABELS[k] for k in keys]
        rets   = []
        for k in keys:
            t = self.benchmarks[k]["CLOSE"].dropna().tail(DAYS+1)
            rets.append(round((t.iloc[-1]/t.iloc[0]-1)*100,2) if len(t)>5 else 0)
        n = len(keys)
        if n == 0: return
        try:
            w = max(self._mc.winfo_width(), 600)
            h = max(self._mc.winfo_height(), 460)
            fig,(ax,ax2) = plt.subplots(1,2,figsize=(w/96,h/96),dpi=96,
                                         facecolor=C["bg"],
                                         gridspec_kw={"width_ratios":[1,1.6]})
            si = sorted(range(n), key=lambda i: rets[i])
            ax.barh([labels[i] for i in si],[rets[i] for i in si],
                    color=[C["grn"] if rets[i]>=0 else C["red"] for i in si],
                    height=0.6)
            ax.axvline(0, color=C["gry"], lw=0.8)
            for i, v in enumerate([rets[j] for j in si]):
                ax.text(v+(0.2 if v>=0 else -0.2), i, f"{v:+.1f}%",
                        va="center", ha="left" if v>=0 else "right",
                        fontsize=7, color=C["txt"])
            axs(ax, "55d Return Ranking")

            ax2.set_facecolor(C["ax"])
            ax2.set_xticks(range(n)); ax2.set_yticks(range(n))
            ax2.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
            ax2.set_yticklabels(labels, fontsize=7)
            for yi in range(n):
                for xi in range(n):
                    d = rets[yi]-rets[xi]
                    if yi==xi:
                        col, txt = C["ax"], "—"
                    else:
                        t = min(abs(d)/15, 0.7)
                        col = ((1-t*0.6,1-t*0.3,1-t*0.6) if d>0
                               else (1-t*0.3,1-t*0.6,1-t*0.6))
                        txt = f"{d:+.1f}"
                    ax2.add_patch(plt.Rectangle((xi-.5,yi-.5),1,1,
                                  facecolor=col,edgecolor=C["grid"],lw=0.3))
                    ax2.text(xi,yi,txt,ha="center",va="center",
                             fontsize=6.5,color=C["txt"])
            ax2.set_xlim(-.5,n-.5); ax2.set_ylim(-.5,n-.5)
            axs(ax2,"RS Heatmap — Row vs Column (55d)")
            fig.tight_layout(pad=1.2)
            ph = to_photo(fig)
            self._mc.delete("all")
            self._mc.create_image(0,0,anchor="nw",image=ph)
            self._p["matrix"] = ph
            plt.close(fig)
        except Exception as e:
            print(f"[Matrix] {e}")

    def _rs_comm_tab(self, sub):
        f = ttk.Frame(sub); sub.add(f, text="  Commodities  ")
        tk.Button(f, text="Refresh Commodities", font=("Segoe UI",9,"bold"),
                  bg="#185FA5", fg="#ffffff", relief="flat",
                  cursor="hand2", padx=12, pady=4,
                  command=self._draw_comm).pack(anchor="w", padx=12, pady=8)
        cols   = ("name","ret55","vsSP","vsGold","vsDXY","rank","sig")
        hdrs   = ("Commodity","55d Return","vs S&P 500","vs Gold","vs DXY","RS Rank","Signal")
        widths = (100,82,82,82,72,72,82)
        tf = tk.Frame(f, bg="#ffffff"); tf.pack(fill="x", padx=8, pady=(0,6))
        self._ct = ttk.Treeview(tf, columns=cols, show="headings", height=8)
        for col, hdr, w in zip(cols, hdrs, widths):
            self._ct.heading(col, text=hdr)
            self._ct.column(col, width=w, anchor="center")
        self._ct.tag_configure("strong", background="#EAF3DE")
        self._ct.tag_configure("weak",   background="#FCEBEB")
        self._ct.pack(fill="x")
        self._cc = tk.Canvas(f, bg=theme.P["body_bg"], highlightthickness=0, height=210)
        self._cc.pack(fill="x", padx=8, pady=(0,8))

    def _draw_comm(self):
        COMM = {"GOLD":"Gold","SILVER":"Silver","CRUDE":"Crude Oil",
                "NATGAS":"Nat Gas","COPPER":"Copper","BTCUSD":"Bitcoin"}
        def r55(df):
            if df is None: return None
            t = df["CLOSE"].dropna().tail(DAYS+1)
            return round((t.iloc[-1]/t.iloc[0]-1)*100,2) if len(t)>5 else None
        sp = r55(self.benchmarks.get("GSPC")) or 0
        dx = r55(self.benchmarks.get("DXY"))  or 0
        gd = r55(self.benchmarks.get("GOLD")) or 0
        rows = []
        for key, label in COMM.items():
            r = r55(self.benchmarks.get(key))
            if r is None: continue
            rank = min(99, max(1, round(50+r*2)))
            sig  = "Leader" if rank>=70 else "Neutral" if rank>=40 else "Laggard"
            rows.append((label,r,round(r-sp,2),round(r-gd,2),round(r-dx,2),rank,sig))
        rows.sort(key=lambda x: x[1], reverse=True)
        for r in self._ct.get_children(): self._ct.delete(r)
        for label,r,vs,vg,vd,rank,sig in rows:
            tag = "strong" if rank>=70 else ("weak" if rank<40 else "")
            self._ct.insert("","end",tags=(tag,),
                values=(label,f"{r:+.2f}%",f"{vs:+.2f}%",
                        f"{vg:+.2f}%",f"{vd:+.2f}%",rank,sig))
        try:
            w = max(self._cc.winfo_width(), 600)
            fig, ax = plt.subplots(figsize=(w/96,200/96), dpi=96, facecolor=C["bg"])
            names  = [r[0] for r in rows]
            values = [r[1] for r in rows]
            bars = ax.bar(names, values,
                color=[C["grn"] if v>=0 else C["red"] for v in values],
                width=0.55)
            ax.axhline(0, color=C["gry"], lw=0.8)
            for bar, v in zip(bars, values):
                ax.text(bar.get_x()+bar.get_width()/2,
                        v+(0.15 if v>=0 else -0.4),
                        f"{v:+.1f}%", ha="center", fontsize=7.5, color=C["txt"])
            axs(ax, "Commodity 55d Returns")
            fig.tight_layout(pad=0.8)
            ph = to_photo(fig)
            self._cc.delete("all")
            self._cc.create_image(0,0,anchor="nw",image=ph)
            self._p["comm"] = ph
            plt.close(fig)
        except Exception as e:
            print(f"[Comm] {e}")

    # ── Risk ──────────────────────────────────────────────────────────────────

    def _tab_risk(self):
        f = ttk.Frame(self._nb); self._nb.add(f, text="  ⚖  Risk Sizer  ")
        L = tk.Frame(f, bg="#ffffff", width=340)
        L.pack(side="left", fill="y"); L.pack_propagate(False)
        R = tk.Frame(f, bg=theme.P["body_bg"]); R.pack(fill="both", expand=True)

        tk.Label(L, text="Position Sizer", font=("Segoe UI",11,"bold"),
                 bg="#ffffff", fg="#2C2C2A").pack(anchor="w", padx=14, pady=(12,6))
        self._sz = {}
        for key, lbl, val in [
            ("cap","Account Capital (₹)","1800000"),
            ("risk","Risk per Trade (%)","1.0"),
            ("entry","Entry Price","0"),
            ("sl","Stop Loss","0"),
            ("tgt","Target Price","0")]:
            row = tk.Frame(L, bg="#ffffff"); row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=lbl, font=("Segoe UI",9), bg="#ffffff",
                     fg="#5F5E5A", width=22, anchor="w").pack(side="left")
            v = tk.StringVar(value=val); self._sz[key] = v
            tk.Entry(row, textvariable=v, width=14,
                     font=("Segoe UI",9)).pack(side="right")
        tk.Button(L, text="Calculate", font=("Segoe UI",9,"bold"),
                  bg="#185FA5", fg="#ffffff", relief="flat",
                  cursor="hand2", padx=10, pady=5,
                  command=self._calc).pack(anchor="w", padx=14, pady=(10,4))
        self._szr = tk.Text(L, height=10, width=36, font=("Consolas",9),
                             bg=theme.P["body_bg"], relief="flat", state="disabled")
        self._szr.pack(padx=14, pady=(4,12), fill="x")

        tk.Label(R, text="Data health", font=("Segoe UI",10,"bold"),
                 bg=theme.P["body_bg"], fg="#2C2C2A").pack(anchor="w", padx=14, pady=(12,4))
        self._ht = tk.Text(R, height=14, font=("Consolas",9), bg="#ffffff",
                            relief="flat", state="disabled")
        self._ht.pack(fill="x", padx=14)
        tk.Button(R, text="Reload data", font=("Segoe UI",9),
                  bg=theme.P["body_bg"], relief="flat", cursor="hand2",
                  padx=8, pady=4, command=self._load_async).pack(
                      anchor="w", padx=14, pady=8)

    def _calc(self):
        try:
            cap  = float(self._sz["cap"].get().replace(",",""))
            risk = float(self._sz["risk"].get())/100
            ent  = float(self._sz["entry"].get())
            sl   = float(self._sz["sl"].get())
            tgt  = float(self._sz["tgt"].get())
            if ent<=0 or sl<=0: return
            ra   = cap*risk
            dist = abs(ent-sl)
            qty  = int(ra/dist) if dist>0 else 0
            rr   = round((tgt-ent)/dist,2) if dist>0 else 0
            txt  = (f"─────────────────────────────\n"
                    f"  Risk Amount   : ₹{ra:,.0f}\n"
                    f"  Entry         : {ent:.4f}\n"
                    f"  Stop Loss     : {sl:.4f}\n"
                    f"  Distance      : {dist:.4f}  ({dist/ent*100:.2f}%)\n"
                    f"─────────────────────────────\n"
                    f"  Qty to Buy    : {qty}\n"
                    f"  Position Size : ₹{qty*ent:,.0f} ({qty*ent/cap*100:.1f}% cap)\n"
                    f"  Max Loss      : ₹{qty*dist:,.2f}\n"
                    f"  Target        : {tgt:.4f}\n"
                    f"  Risk / Reward : {rr}:1\n"
                    f"─────────────────────────────\n")
            self._szr.config(state="normal")
            self._szr.delete("1.0","end")
            self._szr.insert("1.0", txt)
            self._szr.config(state="disabled")
        except ValueError:
            pass

    def _upd_health(self):
        self._ht.config(state="normal")
        self._ht.delete("1.0","end")
        txt = (f"Stocks     : {len(self.stocks)}\n"
               f"Benchmarks : {len(self.benchmarks)}\n"
               f"Data dir   : {paths.DATA_DIR}\n\n"
               "Benchmarks:\n")
        for k in sorted(self.benchmarks):
            df   = self.benchmarks[k]
            last = df["Date"].iloc[-1].strftime("%Y-%m-%d") if len(df) else "—"
            txt += f"  {k:<12} {len(df):>4} rows  {last}\n"
        self._ht.insert("1.0", txt)
        self._ht.config(state="disabled")

    # ── Nightly ───────────────────────────────────────────────────────────────

    def _tab_nightly(self):
        f = ttk.Frame(self._nb); self._nb.add(f, text="  🌙  Nightly  ")
        tk.Label(f, text="Nightly batch downloader", font=("Segoe UI",11,"bold"),
                 bg=theme.P["body_bg"], fg="#2C2C2A").pack(anchor="w", padx=14, pady=(12,2))
        tk.Label(f, text=("Schedule nightly_download.py via Windows Task Scheduler "
                          "after market close.\n"
                          "The app reads only local CSVs — yfinance never called at runtime."),
                 font=("Segoe UI",9), bg=theme.P["body_bg"], fg="#5F5E5A",
                 justify="left").pack(anchor="w", padx=14)
        tk.Frame(f, bg=theme.P["border"], height=1).pack(fill="x", padx=14, pady=8)
        tk.Label(f, text="Last run summary", font=("Segoe UI",10,"bold"),
                 bg=theme.P["body_bg"], fg="#2C2C2A").pack(anchor="w", padx=14)
        self._nt = tk.Text(f, height=14, font=("Consolas",9), bg="#ffffff",
                            relief="flat", state="disabled")
        self._nt.pack(fill="x", padx=14, pady=6)
        br = tk.Frame(f, bg=theme.P["body_bg"]); br.pack(anchor="w", padx=14, pady=4)
        tk.Button(br, text="Run Nightly Download Now", font=("Segoe UI",9,"bold"),
                  bg="#185FA5", fg="#ffffff", relief="flat",
                  cursor="hand2", padx=12, pady=5,
                  command=self._run_nightly).pack(side="left", padx=(0,8))
        tk.Button(br, text="Open Data Folder",
                  font=("Segoe UI",9), bg=theme.P["body_bg"], relief="flat",
                  cursor="hand2", padx=8, pady=5,
                  command=lambda: os.startfile(paths.DATA_DIR)
                      if os.path.exists(paths.DATA_DIR) else None).pack(side="left")

    def _refresh_nightly(self):
        info = load_summary()
        self._nt.config(state="normal"); self._nt.delete("1.0","end")
        if info:
            txt = (f"Last run      : {info.get('last_run','—')}\n"
                   f"Universe      : {info.get('universe','—')} tickers\n"
                   f"Passed filter : {info.get('passed','—')} (ATH/52W)\n"
                   f"Filtered out  : {info.get('filtered','—')}\n"
                   f"Failed dl     : {info.get('failed','—')}\n"
                   f"Benchmarks    : {info.get('benchmarks_ok','—')} ok\n"
                   f"Duration      : {info.get('duration_sec','—')}s\n\n"
                   f"Tickers saved :\n")
            for i, t in enumerate(info.get("passed_tickers","").split(",")):
                if t.strip():
                    txt += f"  {t.strip()}"
                    if (i+1)%5==0: txt+="\n"
            self._nt.insert("1.0", txt)
        else:
            self._nt.insert("1.0","No summary found.\nRun nightly_download.py first.")
        self._nt.config(state="disabled")

    def _run_nightly(self):
        script = os.path.join(paths.ROOT, "nightly_download.py")
        if not os.path.exists(script):
            messagebox.showerror("Not found",
                f"nightly_download.py not found in {paths.ROOT}"); return
        import subprocess
        messagebox.showinfo("Started",
            "Nightly download running in background.\n"
            f"Check {paths.LOG_DIR} for progress.")
        threading.Thread(
            target=lambda: subprocess.Popen(
                ["python", script],
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name=="nt" else 0),
            daemon=True).start()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_async(self):
        self._hdr.set_status("Loading…", color="#F59E0B")
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        s = load_stocks()
        b = load_benchmarks()
        m = load_summary()
        self.root.after(0, lambda: self._post(s, b, m))

    def _post(self, stocks, benchmarks, summary):
        self.stocks     = stocks
        self.benchmarks = benchmarks
        n  = len(stocks)
        ok = n > 0
        self._hdr.set_status(
            f"✓  {n} stocks  ·  {len(benchmarks)} benchmarks",
            color="#34D399" if ok else "#F87171")
        self._hdr.set_lastrun(
            f"Last download: {summary.get('last_run','never')}")
        self._pop_wl()
        self._pop_rslb()
        self._upd_health()
        self._refresh_nightly()
        if stocks:
            self._dash(next(iter(stocks)))
            def _auto():
                if self._rslb.size()>0:
                    self._rslb.selection_set(0)
                    self._rs_sel()
            self.root.after(600, _auto)
        self.root.after(1000, self._pop_rs_rankings)
        self.root.after(1200, self._pop_pricevol)

    # ── TradingView Screener ──────────────────────────────────────────────────

    def _tab_tradingview(self):
        """TradingView Screener tab — fetch real-time screener data."""
        f = ttk.Frame(self._nb)
        self._nb.add(f, text="  🔄  TV Screener  ")
        
        # Control panel
        ctrl = tk.Frame(f, bg="#ffffff", height=50)
        ctrl.pack(fill="x"); ctrl.pack_propagate(False)
        
        tk.Label(ctrl, text="TradingView Screener", font=("Segoe UI",10,"bold"),
                 bg="#ffffff", fg="#2C2C2A").pack(side="left", padx=12, pady=8)
        
        tk.Label(ctrl, text="Market:", font=("Segoe UI",9),
                 bg="#ffffff", fg="#888780").pack(side="left", padx=4)
        self._tv_market = tk.StringVar(value='NSE')
        market_combo = ttk.Combobox(ctrl, textvariable=self._tv_market,
                                     values=['NSE', 'ASX', 'US'],
                                     state='readonly', width=8)
        market_combo.pack(side="left", padx=4)
        market_combo.bind('<<ComboboxSelected>>', lambda _: self._tv_refresh())
        
        tk.Label(ctrl, text="Symbols:", font=("Segoe UI",9),
                 bg="#ffffff", fg="#888780").pack(side="left", padx=4)
        self._tv_symbols = tk.StringVar(value='RELIANCE,INFY,HDFC,ITC,BAJAJFINSV')
        tk.Entry(ctrl, textvariable=self._tv_symbols, font=("Segoe UI",9),
                 width=40).pack(side="left", padx=4)
        
        tk.Button(ctrl, text="Fetch Data", font=("Segoe UI",9),
                  bg="#EAF3DE", fg="#27500A", relief="flat",
                  command=self._tv_fetch).pack(side="left", padx=4)
        
        tk.Button(ctrl, text="Export CSV", font=("Segoe UI",9),
                  bg="#F0E8DC", fg="#2C2C2A", relief="flat",
                  command=self._tv_export).pack(side="left", padx=4)
        
        self._tv_status = tk.Label(ctrl, text="Ready", font=("Segoe UI",8),
                                    bg="#ffffff", fg="#888780")
        self._tv_status.pack(side="right", padx=12)
        
        # Data display
        cols = ('Symbol', 'Close', 'RSI', 'MACD', 'SMA20', 'SMA50', 'SMA200', 'ATR', 'Timestamp')
        self._tv_tree = ttk.Treeview(f, columns=cols, show="headings", height=20)
        
        widths = {'Symbol': 80, 'Close': 80, 'RSI': 60, 'MACD': 80, 'SMA20': 70,
                  'SMA50': 70, 'SMA200': 80, 'ATR': 60, 'Timestamp': 150}
        
        for col in cols:
            self._tv_tree.heading(col, text=col)
            self._tv_tree.column(col, width=widths.get(col, 70), anchor="center")
        
        sb = ttk.Scrollbar(f, command=self._tv_tree.yview)
        self._tv_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv_tree.pack(fill="both", expand=True, padx=4, pady=4)
        
        self._tv_client = None
        self._tv_data = {}
    
    def _tv_fetch(self):
        """Fetch TradingView screener data."""
        def worker():
            try:
                self._tv_status.config(text="Fetching...", fg="#854F0B")
                self.root.update_idletasks()
                
                if self._tv_client is None:
                    self._tv_client = TradingViewClient()
                
                market = self._tv_market.get()
                symbols_str = self._tv_symbols.get()
                symbols = [s.strip().upper() for s in symbols_str.split(',')]
                
                df = self._tv_client.fetch_screener_data(symbols, market)
                self._tv_data[market] = df
                
                self.root.after(0, self._tv_refresh)
                self._tv_status.config(text=f"Fetched {len(df)} symbols", fg="#27500A")
            
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("TradingView Error", str(e)))
                self._tv_status.config(text="Error", fg="#B82500")
        
        threading.Thread(target=worker, daemon=True).start()
    
    def _tv_refresh(self):
        """Refresh TradingView tree display."""
        market = self._tv_market.get()
        
        # Clear tree
        for item in self._tv_tree.get_children():
            self._tv_tree.delete(item)
        
        # Populate with current data
        if market in self._tv_data:
            df = self._tv_data[market]
            for idx, row in df.iterrows():
                values = [
                    row.get('Symbol', ''),
                    f"{row.get('Close', 0):.2f}",
                    f"{row.get('RSI_14', 0):.1f}",
                    f"{row.get('MACD', 0):.4f}",
                    f"{row.get('SMA_20', 0):.2f}",
                    f"{row.get('SMA_50', 0):.2f}",
                    f"{row.get('SMA_200', 0):.2f}",
                    f"{row.get('ATR_14', 0):.2f}",
                    str(row.get('Timestamp', '')).split('.')[0]
                ]
                self._tv_tree.insert('', tk.END, values=values)
    
    def _tv_export(self):
        """Export TradingView data to CSV."""
        market = self._tv_market.get()
        if market not in self._tv_data:
            messagebox.showwarning("Export", "No data to export")
            return
        
        df = self._tv_data[market]
        filename = os.path.join(paths.EXPORT_DIR, f"TradingView_{market}_{date.today()}.csv")
        
        try:
            df.to_csv(filename, index=False)
            messagebox.showinfo("Export", f"Exported to: {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ── RS Rankings ───────────────────────────────────────────────────────────

    def _tab_rs_rankings(self):
        """Create RS Rankings tab using the RsRankingsTab helper class."""
        self._rs_rank_tab = RsRankingsTab()
        self._rs_rank_tab.build(self._nb, self.root)

    def _pop_rs_rankings(self):
        """Populate RS Rankings tab from loaded stocks. Called after _post."""
        if hasattr(self, "_rs_rank_tab") and self.stocks:
            self._rs_rank_tab.populate(self.stocks, self.benchmarks)

    # ── Price-Vol Analysis ────────────────────────────────────────────────────

    def _tab_pricevol(self):
        """Price-Volume Analysis tab with VCS, Breakout, OBV, MoneyFlow charts."""
        f = ttk.Frame(self._nb)
        self._nb.add(f, text="  📊  Price-Vol  ")

        # ── Left panel: stock list with VCS ───────────────────────────────
        L = tk.Frame(f, bg="#ffffff", width=230)
        L.pack(side="left", fill="y"); L.pack_propagate(False)

        hdr = tk.Frame(L, bg="#ffffff"); hdr.pack(fill="x")
        tk.Label(hdr, text="Volume Rankings", font=("Segoe UI",10,"bold"),
                 bg="#ffffff", fg="#2C2C2A").pack(side="left", padx=10, pady=8)
        tk.Button(hdr, text="↻", font=("Segoe UI",9),
                  bg="#EAF3DE", fg="#27500A", relief="flat",
                  command=self._pop_pricevol).pack(side="right", padx=8)

        # Market filter
        mf = tk.Frame(L, bg=theme.P["body_bg"]); mf.pack(fill="x", padx=6, pady=(0,4))
        tk.Label(mf, text="Market:", font=("Segoe UI",8),
                 bg=theme.P["body_bg"], fg="#888780").pack(side="left")
        self._pv_mkt = tk.StringVar(value="All")
        ttk.Combobox(mf, textvariable=self._pv_mkt,
                     values=["All","NSE","ASX","US"],
                     state="readonly", width=8).pack(side="left", padx=4)
        self._pv_mkt.trace_add("write", lambda *_: self._pv_filter())

        tk.Frame(L, bg=theme.P["border"], height=1).pack(fill="x")

        # Stock list (Ticker | VCS | Signal)
        pv_cols = ("ticker","vcs","signal")
        self._pvlb = ttk.Treeview(L, columns=pv_cols, show="headings",
                                   selectmode="browse", height=30)
        for col, hdr_txt, w in [("ticker","Ticker",75),
                                  ("vcs","VCS",45),("signal","Signal",95)]:
            self._pvlb.heading(col, text=hdr_txt)
            self._pvlb.column(col, width=w, anchor="center")
        self._pvlb.tag_configure("high",  background="#C8E6C9")
        self._pvlb.tag_configure("mod",   background="#FFF9C4")
        self._pvlb.tag_configure("low",   background="#FFCDD2")
        pvlb_sb = ttk.Scrollbar(L, command=self._pvlb.yview)
        self._pvlb.configure(yscrollcommand=pvlb_sb.set)
        pvlb_sb.pack(side="right", fill="y")
        self._pvlb.pack(fill="both", expand=True)
        self._pvlb.bind("<<TreeviewSelect>>",
                        lambda _: self.root.after(100, self._pv_sel))

        # ── Right panel: metrics + charts ─────────────────────────────────
        R = tk.Frame(f, bg=theme.P["body_bg"])
        R.pack(side="left", fill="both", expand=True)

        # Metric chips row
        chips = tk.Frame(R, bg="#ffffff", height=64)
        chips.pack(fill="x"); chips.pack_propagate(False)
        self._pv_chips = {}
        for key, lbl in [("ticker","Ticker"),("vcs","VCS Score"),
                          ("rvol","Rel Volume"),("breakout","Signal"),
                          ("ad","A/D Ratio"),("obv","OBV Trend"),
                          ("mf","Money Flow")]:
            m = tk.Frame(chips, bg=theme.P["body_bg"])
            m.pack(side="left", padx=6, pady=8, ipadx=8, ipady=4)
            tk.Label(m, text=lbl, font=("Segoe UI",8),
                     bg=theme.P["body_bg"], fg="#888780").pack()
            v = tk.Label(m, text="—", font=("Segoe UI",11,"bold"),
                         bg=theme.P["body_bg"], fg="#2C2C2A")
            v.pack()
            self._pv_chips[key] = v

        # VCS breakdown bar
        vcs_row = tk.Frame(R, bg=theme.P["body_bg"], height=28)
        vcs_row.pack(fill="x"); vcs_row.pack_propagate(False)
        self._pv_breakdown = tk.Label(
            vcs_row, text="Select a stock to see volume analysis",
            font=("Segoe UI",8), bg=theme.P["body_bg"], fg="#888780")
        self._pv_breakdown.pack(side="left", padx=10, pady=4)

        # Chart canvas
        self._pv_canvas = tk.Canvas(R, bg=theme.P["body_bg"], highlightthickness=0)
        self._pv_canvas.pack(fill="both", expand=True, padx=4, pady=4)

        self._pv_df_all = pd.DataFrame()   # batch VCS results
        self._pv_photo  = None             # keep ref to avoid GC

    def _pop_pricevol(self):
        """Calculate batch VCS for all stocks and populate left panel."""
        if not self.stocks:
            return
        self._pv_breakdown.config(text="Calculating volume metrics…")

        def _worker():
            df = batch_vcs(self.stocks)
            self._pv_df_all = df
            self.root.after(0, self._pv_filter)

        threading.Thread(target=_worker, daemon=True).start()

    def _pv_filter(self):
        """Apply market filter and populate list."""
        df = self._pv_df_all
        if df.empty:
            return
        mkt = self._pv_mkt.get()
        if mkt != "All":
            df = df[df["Market"] == mkt]

        for it in self._pvlb.get_children():
            self._pvlb.delete(it)

        for _, row in df.iterrows():
            vcs = row["VCS"]
            tag = "high" if vcs >= 70 else ("mod" if vcs >= 45 else "low")
            from rs_rankings_module import _strip
            self._pvlb.insert("", "end", tags=(tag,), values=(
                _strip(row["Ticker"]), vcs, row["VCS_Label"][:12],
            ))

        self._pv_breakdown.config(
            text=f"{len(df)} stocks ranked by Volume Conviction Score")

    def _pv_sel(self):
        """Load selected stock into right panel."""
        s = self._pvlb.selection()
        if not s:
            return
        ticker_short = self._pvlb.item(s[0])["values"][0]

        # Find full ticker key in self.stocks
        full = None
        for k in self.stocks:
            from rs_rankings_module import _strip
            if _strip(k) == str(ticker_short):
                full = k
                break
        if full is None:
            return

        df = self.stocks[full]
        try:
            va = VolumeAnalyser(df)
            m  = va.metrics()
            self._pv_update_chips(full, m)
            self._pv_draw_charts(full, df, m)
        except Exception as e:
            print(f"[PV] {full}: {e}")

    def _pv_update_chips(self, ticker, m):
        """Update metric chip labels."""
        from rs_rankings_module import _strip
        self._pv_chips["ticker"].config(text=_strip(ticker))

        vcs = m["vcs"]
        vcs_color = (C["grn"] if vcs >= 70 else
                     C["amb"] if vcs >= 45 else C["red"])
        self._pv_chips["vcs"].config(text=f"{vcs}/100", fg=vcs_color)

        rvol = m["rvol"]
        rv_color = C["grn"] if rvol >= 1.5 else (C["amb"] if rvol >= 1.0 else C["red"])
        self._pv_chips["rvol"].config(text=f"{rvol:.1f}×", fg=rv_color)

        self._pv_chips["breakout"].config(text=m["breakout_signal"][:16])

        ad = m["ad_ratio"]
        ad_str = f"{ad:.1f}" if ad != float("inf") else "∞"
        ad_col = C["grn"] if m["ad_signal"] == "Accumulating" else (
                 C["red"] if m["ad_signal"] == "Distributing" else C["gry"])
        self._pv_chips["ad"].config(text=f"{ad_str}  ({m['ad_signal'][:5]})",
                                     fg=ad_col)

        obv_col = C["grn"] if m["obv_trend"] == "Rising" else (
                  C["red"] if m["obv_trend"] == "Falling" else C["gry"])
        obv_txt = m["obv_trend"] + (" ★" if m["obv_new_high"] else "")
        self._pv_chips["obv"].config(text=obv_txt, fg=obv_col)

        mf_col = C["grn"] if m["mf_trend"] == "Rising" else (
                 C["red"] if m["mf_trend"] == "Falling" else C["gry"])
        self._pv_chips["mf"].config(text=m["mf_trend"], fg=mf_col)

        bd = m["vcs_breakdown"]
        self._pv_breakdown.config(
            text=(f"VCS Breakdown:  "
                  f"VolSurge {bd['vol_surge']}pts  |  "
                  f"OBV {bd['obv']}pts  |  "
                  f"A/D {bd['accum_dist']}pts  |  "
                  f"VDU {bd['vdu']}pts  |  "
                  f"MoneyFlow {bd['money_flow']}pts"))

    def _pv_draw_charts(self, ticker, df, m):
        """Draw 3-panel chart: Price+Volume / OBV / MoneyFlow."""
        try:
            w = max(self._pv_canvas.winfo_width(), 600)
            h = max(self._pv_canvas.winfo_height(), 400)

            fig = plt.figure(figsize=(w/96, h/96), dpi=96, facecolor=C["bg"])
            fig.subplots_adjust(left=0.07, right=0.97,
                                top=0.93, bottom=0.08, hspace=0.35)

            tail = df.tail(120).copy().reset_index(drop=True)
            dates = tail["Date"]

            # ── Panel 1: Price + Volume bars ──────────────────────────────
            ax1 = fig.add_subplot(3, 1, 1)
            ax1v = ax1.twinx()

            # Volume bars coloured by direction
            colors = ["#3B6D11" if tail["CLOSE"].iloc[i] >= tail["CLOSE"].iloc[i-1]
                      else "#A32D2D"
                      for i in range(len(tail))]
            avg_vol = tail["VOLUME"].rolling(20).mean()
            ax1v.bar(range(len(tail)), tail["VOLUME"],
                     color=colors, alpha=0.35, width=0.8)
            ax1v.plot(range(len(tail)), avg_vol,
                      color=C["amb"], lw=0.8, ls="--", alpha=0.7)
            ax1v.set_yticks([])

            ax1.plot(range(len(tail)), tail["CLOSE"],
                     color=C["blue"], lw=1.4, label="Price")
            ema21 = tail["CLOSE"].ewm(span=21, adjust=False).mean()
            ax1.plot(range(len(tail)), ema21,
                     color=C["grn"], lw=0.9, ls="--", alpha=0.8, label="EMA21")
            ax1.set_xlim(0, len(tail))
            ax1.legend(fontsize=7, loc="upper left", framealpha=0.6)
            from rs_rankings_module import _strip
            axs(ax1, f"{_strip(ticker)}  —  Price + Volume")

            # ── Panel 2: OBV ──────────────────────────────────────────────
            ax2 = fig.add_subplot(3, 1, 2)
            obv_tail = m["obv_series"].tail(120).reset_index(drop=True)
            obv_ma   = obv_tail.rolling(20).mean()
            ax2.plot(range(len(obv_tail)), obv_tail,
                     color=C["blue"], lw=1.2, label="OBV")
            ax2.plot(range(len(obv_tail)), obv_ma,
                     color=C["amb"], lw=0.9, ls="--", alpha=0.8, label="OBV MA20")
            ax2.set_xlim(0, len(obv_tail))
            ax2.legend(fontsize=7, loc="upper left", framealpha=0.6)
            ax2.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))
            axs(ax2, "On-Balance Volume (OBV)")

            # ── Panel 3: Money Flow ───────────────────────────────────────
            ax3 = fig.add_subplot(3, 1, 3)
            mf_tail  = m["mf_series"].tail(120).reset_index(drop=True)
            mf_ma    = m["mf_ma_series"].tail(120).reset_index(drop=True)
            ax3.fill_between(range(len(mf_tail)), mf_tail,
                             alpha=0.25, color=C["blue"])
            ax3.plot(range(len(mf_tail)), mf_tail,
                     color=C["blue"], lw=0.8, alpha=0.6, label="Money Flow")
            ax3.plot(range(len(mf_tail)), mf_ma,
                     color=C["grn"], lw=1.2, label="MF MA20")
            ax3.set_xlim(0, len(mf_tail))
            ax3.legend(fontsize=7, loc="upper left", framealpha=0.6)
            ax3.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, _: f"{x/1e9:.1f}B"
                                  if abs(x) >= 1e9 else f"{x/1e6:.0f}M"))
            axs(ax3, "Money Flow (Close × Volume)  +  20-day MA")

            photo = to_photo(fig)
            plt.close(fig)
            self._pv_photo = photo
            self._pv_canvas.delete("all")
            self._pv_canvas.create_image(0, 0, anchor="nw", image=photo)

        except Exception as e:
            print(f"[PV chart] {e}")

    # ── Sort ──────────────────────────────────────────────────────────────────

    def _sort(self, tree, col, rev):
        data = [(tree.set(k,col),k) for k in tree.get_children("")]
        try:
            data.sort(key=lambda t: float(
                t[0].replace("%","").replace("×","")
                    .replace(":1","").replace("—","0")), reverse=rev)
        except ValueError:
            data.sort(reverse=rev)
        for i,(_,k) in enumerate(data): tree.move(k,"",i)
        tree.heading(col, command=lambda: self._sort(tree, col, not rev))


if __name__ == "__main__":
    root = tk.Tk()
    EdgePro(root)
    root.mainloop()
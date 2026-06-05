import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
"""
theme.py
--------
Edge Pro visual theme — professional trading terminal aesthetic.

Applies:
  - Refined color palette
  - Dark header with live market clocks (NSE / ASX / US)
  - Upgraded ttk.Style (tabs, treeview, scrollbars, buttons)
  - Zebra-stripe Treeview rows
  - Typography hierarchy
  - Consistent padding/spacing tokens

Usage in edge_pro.py:
    import theme
    theme.apply(root)           # call ONCE in EdgePro.__init__
    hdr = theme.Header(root)    # replaces the manual bar frame
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime
import pytz                    # pip install pytz  (usually already present)


# ── Color tokens ──────────────────────────────────────────────────────────────

P = dict(
    # Header (dark navy)
    hdr_bg       = "#0F172A",
    hdr_accent   = "#3B82F6",
    hdr_text     = "#F1F5F9",
    hdr_muted    = "#94A3B8",

    # Body
    body_bg      = "#F8FAFC",
    panel_bg     = "#FFFFFF",
    sidebar_bg   = "#FFFFFF",

    # Treeview rows
    row_even     = "#FFFFFF",
    row_odd      = "#F8FAFC",
    row_hover    = "#EFF6FF",

    # Borders & dividers
    border       = "#E2E8F0",
    divider      = "#CBD5E1",

    # Accent
    blue         = "#1D4ED8",
    blue_light   = "#DBEAFE",
    blue_mid     = "#3B82F6",

    # Semantic
    green        = "#15803D",
    green_light  = "#DCFCE7",
    red          = "#B91C1C",
    red_light    = "#FEE2E2",
    amber        = "#B45309",
    amber_light  = "#FEF3C7",

    # Text
    txt_primary  = "#0F172A",
    txt_secondary= "#475569",
    txt_muted    = "#94A3B8",

    # Tab bar
    tab_bg       = "#F1F5F9",
    tab_sel_bg   = "#FFFFFF",
    tab_sel_fg   = "#1D4ED8",
    tab_fg       = "#64748B",
)

# ── Typography ────────────────────────────────────────────────────────────────

FONT = dict(
    h1   = ("Segoe UI", 14, "bold"),
    h2   = ("Segoe UI", 11, "bold"),
    h3   = ("Segoe UI",  9, "bold"),
    body = ("Segoe UI",  9),
    sm   = ("Segoe UI",  8),
    mono = ("Consolas",  9),
    logo = ("Segoe UI", 15, "bold"),
)

# ── Market timezone helpers ───────────────────────────────────────────────────

MARKETS = [
    # (label, timezone, open_utc_h, close_utc_h)
    ("NSE",  "Asia/Kolkata",      3, 10),    # 09:15–15:30 IST → 03:45–10:00 UTC
    ("ASX",  "Australia/Sydney",  0,  7),    # 10:00–16:00 AEST → 00:00–06:00 UTC
    ("NYSE", "America/New_York",  13, 21),   # 09:30–16:00 ET  → 13:30–20:00 UTC
]

def _market_status(tz_name: str, open_h: int, close_h: int):
    """Returns (local_time_str, is_open)."""
    try:
        tz  = pytz.timezone(tz_name)
        now = datetime.now(tz)
        utc_now = datetime.now(pytz.utc)
        # Weekday check
        if utc_now.weekday() >= 5:   # Sat/Sun
            return now.strftime("%H:%M"), False
        utc_h = utc_now.hour + utc_now.minute / 60
        is_open = open_h <= utc_h < close_h
        return now.strftime("%H:%M"), is_open
    except Exception:
        return "--:--", False


# ── ttk Style application ─────────────────────────────────────────────────────

def apply(root: tk.Tk):
    """
    Apply the full Edge Pro theme to a Tk root.
    Call once before building any widgets.
    """
    root.configure(bg=P["body_bg"])
    s = ttk.Style(root)
    s.theme_use("clam")

    # ── Notebook (tabs) ───────────────────────────────────────────────────
    s.configure("TNotebook",
                background=P["tab_bg"],
                borderwidth=0,
                tabmargins=[0, 0, 0, 0])

    s.configure("TNotebook.Tab",
                font=FONT["body"],
                padding=[14, 7],
                background=P["tab_bg"],
                foreground=P["tab_fg"],
                borderwidth=0,
                focuscolor=P["tab_bg"])

    s.map("TNotebook.Tab",
          background=[("selected", P["tab_sel_bg"])],
          foreground=[("selected", P["tab_sel_fg"])],
          expand=[("selected", [1, 1, 1, 0])])

    # ── Treeview ─────────────────────────────────────────────────────────
    s.configure("Treeview",
                font=FONT["body"],
                rowheight=26,
                background=P["panel_bg"],
                foreground=P["txt_primary"],
                fieldbackground=P["panel_bg"],
                borderwidth=0,
                relief="flat")

    s.configure("Treeview.Heading",
                font=FONT["h3"],
                background=P["body_bg"],
                foreground=P["txt_secondary"],
                borderwidth=0,
                relief="flat",
                padding=[4, 6])

    s.map("Treeview",
          background=[("selected", P["blue_light"])],
          foreground=[("selected", P["blue"])],
          rowheight=[])

    s.map("Treeview.Heading",
          background=[("active", P["blue_light"])],
          foreground=[("active", P["blue"])])

    # ── Scrollbar ─────────────────────────────────────────────────────────
    s.configure("Vertical.TScrollbar",
                background=P["border"],
                troughcolor=P["body_bg"],
                arrowcolor=P["txt_muted"],
                relief="flat", arrowsize=12, width=12)

    s.configure("Horizontal.TScrollbar",
                background=P["border"],
                troughcolor=P["body_bg"],
                arrowcolor=P["txt_muted"],
                relief="flat", arrowsize=12, width=12)

    s.map("Vertical.TScrollbar",
          background=[("active", P["blue_mid"])])

    # ── Combobox ─────────────────────────────────────────────────────────
    s.configure("TCombobox",
                font=FONT["body"],
                padding=[4, 4],
                arrowsize=12,
                background=P["panel_bg"],
                fieldbackground=P["panel_bg"],
                foreground=P["txt_primary"],
                selectbackground=P["blue_light"],
                selectforeground=P["blue"])

    # ── Frame / Label ─────────────────────────────────────────────────────
    s.configure("TFrame", background=P["body_bg"])
    s.configure("TLabel", background=P["body_bg"],
                foreground=P["txt_primary"], font=FONT["body"])

    # ── PanedWindow ───────────────────────────────────────────────────────
    s.configure("TPanedwindow", background=P["border"])

    # ── Separator ─────────────────────────────────────────────────────────
    s.configure("TSeparator", background=P["border"])

    # ── Custom tag styles for treeviews ───────────────────────────────────
    # Applied globally — each Treeview must call tag_configure after creation


def zebra(tree: ttk.Treeview, items=None):
    """
    Apply alternating row colors to a Treeview.
    Call after inserting rows: zebra(self._tree)
    """
    items = items or tree.get_children("")
    for i, item in enumerate(items):
        bg = P["row_even"] if i % 2 == 0 else P["row_odd"]
        # Only apply if no existing meaningful tag
        tags = tree.item(item, "tags")
        if not tags or tags == ("",):
            tree.item(item, tags=("even" if i % 2 == 0 else "odd",))
    tree.tag_configure("even", background=P["row_even"])
    tree.tag_configure("odd",  background=P["row_odd"])


# ── Header widget ─────────────────────────────────────────────────────────────

class Header:
    """
    Dark professional header bar with:
    - Edge Pro logo + subtitle
    - Live market clocks (NSE / ASX / NYSE) with open/closed pill
    - Stock count + last download date
    - Live ticking clock (top-right)
    """

    def __init__(self, root: tk.Tk, height: int = 56):
        self.root   = root
        self._frame = tk.Frame(root, bg=P["hdr_bg"], height=height)
        self._frame.pack(fill="x")
        self._frame.pack_propagate(False)

        self._build()
        self._tick()

    @property
    def frame(self):
        return self._frame

    def _build(self):
        f = self._frame

        # ── LEFT: Logo ────────────────────────────────────────────────────
        left = tk.Frame(f, bg=P["hdr_bg"])
        left.pack(side="left", padx=16)

        logo = tk.Frame(left, bg=P["hdr_bg"])
        logo.pack(side="left", pady=10)

        tk.Label(logo, text="EDGE", font=("Segoe UI", 14, "bold"),
                 bg=P["hdr_bg"], fg=P["hdr_text"]).pack(side="left")
        tk.Label(logo, text="PRO", font=("Segoe UI", 14, "bold"),
                 bg=P["hdr_bg"], fg=P["hdr_accent"]).pack(side="left")

        tk.Label(left, text=" Positional Trading System",
                 font=("Segoe UI", 8), bg=P["hdr_bg"],
                 fg=P["hdr_muted"]).pack(side="left", padx=(6, 0), pady=2)

        # ── CENTER: Market clocks ─────────────────────────────────────────
        center = tk.Frame(f, bg=P["hdr_bg"])
        center.pack(side="left", padx=30)

        self._clocks = {}
        for label, tz, oh, ch in MARKETS:
            mf = tk.Frame(center, bg=P["hdr_bg"])
            mf.pack(side="left", padx=12)

            tk.Label(mf, text=label, font=("Segoe UI", 7, "bold"),
                     bg=P["hdr_bg"], fg=P["hdr_muted"]).pack()

            time_lbl = tk.Label(mf, text="--:--",
                                font=("Segoe UI", 11, "bold"),
                                bg=P["hdr_bg"], fg=P["hdr_text"])
            time_lbl.pack()

            status_lbl = tk.Label(mf, text="CLOSED",
                                  font=("Segoe UI", 7, "bold"),
                                  bg="#374151", fg="#9CA3AF",
                                  padx=5, pady=1)
            status_lbl.pack()

            self._clocks[label] = (time_lbl, status_lbl, tz, oh, ch)

        # ── RIGHT: Status + date/time ─────────────────────────────────────
        right = tk.Frame(f, bg=P["hdr_bg"])
        right.pack(side="right", padx=16)

        self._datetime_lbl = tk.Label(
            right, text="", font=("Segoe UI", 9),
            bg=P["hdr_bg"], fg=P["hdr_muted"])
        self._datetime_lbl.pack(anchor="e")

        self._status_lbl = tk.Label(
            right, text="Loading…", font=("Segoe UI", 9, "bold"),
            bg=P["hdr_bg"], fg="#F59E0B")
        self._status_lbl.pack(anchor="e")

        self._lastrun_lbl = tk.Label(
            right, text="", font=("Segoe UI", 7),
            bg=P["hdr_bg"], fg=P["hdr_muted"])
        self._lastrun_lbl.pack(anchor="e")

    def _tick(self):
        """Update clocks every 30 seconds."""
        now = datetime.now()
        self._datetime_lbl.config(
            text=now.strftime("%A, %d %b %Y  %H:%M"))

        for label, (tl, sl, tz, oh, ch) in self._clocks.items():
            t_str, is_open = _market_status(tz, oh, ch)
            tl.config(text=t_str,
                      fg="#34D399" if is_open else P["hdr_text"])
            sl.config(
                text=" OPEN " if is_open else "CLOSED",
                bg="#065F46" if is_open else "#374151",
                fg="#A7F3D0" if is_open else "#9CA3AF")

        self.root.after(30_000, self._tick)

    def set_status(self, text: str, color: str = "#F59E0B"):
        self._status_lbl.config(text=text, fg=color)

    def set_lastrun(self, text: str):
        self._lastrun_lbl.config(text=text)


# ── Styled button factory ─────────────────────────────────────────────────────

def btn_primary(parent, text, command, **kw):
    """Blue filled button."""
    b = tk.Button(parent, text=text, command=command,
                  font=FONT["body"], relief="flat", cursor="hand2",
                  bg=P["blue"], fg="#FFFFFF",
                  activebackground=P["blue_mid"],
                  activeforeground="#FFFFFF",
                  padx=14, pady=5, **kw)
    b.bind("<Enter>", lambda _: b.config(bg=P["blue_mid"]))
    b.bind("<Leave>", lambda _: b.config(bg=P["blue"]))
    return b


def btn_secondary(parent, text, command, **kw):
    """Ghost/outline style button."""
    b = tk.Button(parent, text=text, command=command,
                  font=FONT["body"], relief="flat", cursor="hand2",
                  bg=P["body_bg"], fg=P["txt_secondary"],
                  activebackground=P["blue_light"],
                  activeforeground=P["blue"],
                  padx=10, pady=5, **kw)
    b.bind("<Enter>", lambda _: b.config(bg=P["blue_light"], fg=P["blue"]))
    b.bind("<Leave>", lambda _: b.config(bg=P["body_bg"], fg=P["txt_secondary"]))
    return b


def btn_success(parent, text, command, **kw):
    """Green button."""
    b = tk.Button(parent, text=text, command=command,
                  font=FONT["body"], relief="flat", cursor="hand2",
                  bg="#166534", fg="#FFFFFF",
                  activebackground=P["green"],
                  padx=12, pady=5, **kw)
    b.bind("<Enter>", lambda _: b.config(bg=P["green"]))
    b.bind("<Leave>", lambda _: b.config(bg="#166534"))
    return b


# ── Section label factory ─────────────────────────────────────────────────────

def section_label(parent, text: str) -> tk.Label:
    """Styled section header label with left accent bar."""
    f = tk.Frame(parent, bg=P["panel_bg"])
    tk.Frame(f, bg=P["blue"], width=3).pack(side="left", fill="y")
    tk.Label(f, text=f"  {text}", font=FONT["h3"],
             bg=P["panel_bg"], fg=P["txt_primary"],
             pady=6).pack(side="left")
    return f


# ── Metric card factory ───────────────────────────────────────────────────────

def metric_card(parent, label: str, value: str = "—",
                bg=None, fg=None) -> dict:
    """
    Returns dict with 'frame', 'label_widget', 'value_widget'.
    Use value_widget.config(text=...) to update.
    """
    bg  = bg  or P["body_bg"]
    fg  = fg  or P["txt_primary"]

    outer = tk.Frame(parent, bg=P["border"], padx=1, pady=1)  # border via padding
    inner = tk.Frame(outer, bg=bg)
    inner.pack(fill="both", expand=True)

    lbl_w = tk.Label(inner, text=label, font=FONT["sm"],
                     bg=bg, fg=P["txt_muted"], pady=2)
    lbl_w.pack(pady=(6, 0), padx=10)

    val_w = tk.Label(inner, text=value, font=FONT["h2"],
                     bg=bg, fg=fg)
    val_w.pack(pady=(0, 6), padx=10)

    return {"frame": outer, "label": lbl_w, "value": val_w}


# ── Divider ───────────────────────────────────────────────────────────────────

def hdivider(parent, color=None):
    """Horizontal 1px divider."""
    tk.Frame(parent, bg=color or P["border"], height=1).pack(fill="x")


# ── Control bar (used at top of each tab) ─────────────────────────────────────

def control_bar(parent, height=46) -> tk.Frame:
    """Styled horizontal control bar with border bottom."""
    outer = tk.Frame(parent, bg=P["panel_bg"])
    outer.pack(fill="x")
    bar = tk.Frame(outer, bg=P["panel_bg"], height=height)
    bar.pack(fill="x"); bar.pack_propagate(False)
    hdivider(outer)
    return bar

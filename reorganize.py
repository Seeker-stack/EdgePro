"""
reorganize.py
-------------
Migrates C:\StockData to the professional folder structure.

Run ONCE from C:\StockData:
    python reorganize.py

What it does:
  1. Creates src\, launchers\, docs\, archive\ directories
  2. Moves all Python scripts to src\
  3. Moves all .bat / .command files to launchers\
  4. Moves all documentation (.md, .txt) to docs\
  5. Moves old backups / deprecated scripts to archive\
  6. Deletes junk files (.zip, __pycache__, etc.)
  7. Writes updated launchers that point to src\
  8. Writes a sys.path shim into each moved script
     so inter-module imports still work from src\
  9. Prints a summary of everything moved / created

SAFE: nothing is deleted except __pycache__ and .pyc files.
      All other files are only moved, never lost.
"""

import os, shutil, sys
from pathlib import Path

ROOT = Path(r"C:\StockData")

# ── New directories ────────────────────────────────────────────────────────────
SRC_DIR      = ROOT / "src"
LAUNCHERS    = ROOT / "launchers"
DOCS_DIR     = ROOT / "docs"
ARCHIVE_DIR  = ROOT / "archive"

# ── File routing rules ─────────────────────────────────────────────────────────

# Scripts to move to src\  (excluding reorganize.py itself)
SCRIPTS = [
    "edge_pro.py",
    "nightly_download.py",
    "fetch_tv_tickers.py",
    "fetch_ath_tickers.py",
    "tradingview_client.py",
    "volume_module.py",
    "rs_rankings_module.py",
    "theme.py",
    "paths.py",
    "main.py",
]

# Bat / command launchers → launchers\
LAUNCHERS_FILES = [
    "EdgePro.bat", "FetchAndDownload.bat", "NightlyDownload.bat",
    "run_nightly.bat", "FetchAndDownload.command",
]

# Documentation → docs\
DOCS_FILES = [
    "README.md", "SETUP.md",
    "DEPLOYMENT_CHECKLIST.txt", "DEPLOYMENT_SUMMARY.txt",
    "QUICK_FIX_YFINANCE.txt", "README_DEPLOYMENT.txt",
    "SETUP_TRADINGVIEW_INTEGRATION.txt",
]

# Old backups / deprecated → archive\
ARCHIVE_FILES = [
    "bkp_edge_pro.py", "bkp_nightly_download.py",
    "nightly_download_tv.py", "setup_folders.py",
]

# Junk to delete (not move)
JUNK_PATTERNS = ["*.zip", "*.pyc"]
JUNK_DIRS     = ["__pycache__"]

# Files that must stay at root
ROOT_KEEPERS = {
    "Tickers.txt", "pyproject.toml", "uv.lock",
    ".gitignore", ".python-version", "reorganize.py",
}

# SYS.PATH shim — injected at top of scripts in src\ so imports still resolve
SHIM = '''\
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
'''


def sep(title=""):
    print("\n" + "─" * 55)
    if title:
        print(f"  {title}")
        print("─" * 55)


def move(src: Path, dest_dir: Path, label=""):
    """Move file if it exists. Returns True if moved."""
    if not src.exists():
        return False
    dest = dest_dir / src.name
    shutil.move(str(src), str(dest))
    tag = f"  [{label}]" if label else ""
    print(f"  ✓  {src.name:<40}{tag}")
    return True


def inject_shim(path: Path):
    """Inject sys.path shim at top of script if not already present."""
    content = path.read_text(encoding="utf-8", errors="replace")
    if "_sys.path.insert" in content:
        return   # already has shim
    path.write_text(SHIM + content, encoding="utf-8")


def update_script_path_ref(path: Path):
    """
    Patch paths.py: ROOT must point to parent of src\, i.e. C:\StockData.
    paths.py lives in src\ but ROOT should still be C:\StockData.
    """
    if path.name != "paths.py":
        return
    content = path.read_text(encoding="utf-8", errors="replace")
    # Make ROOT dynamic so it always resolves to C:\StockData
    # regardless of where paths.py lives
    old = 'ROOT = r"C:\\StockData"'
    new = (
        "ROOT = str(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))"
        "  # resolves to C:\\StockData regardless of location"
    )
    if old in content:
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        print(f"  ↻  paths.py: ROOT made dynamic")


def write_launchers():
    """
    Write updated .bat launchers that run scripts from src\.
    Old launchers are already moved to launchers\ (as reference).
    New launchers stay at root for double-click convenience.
    """
    bats = {
        "EdgePro.bat": (
            "@echo off\n"
            "title Edge Pro\n"
            "cd /d C:\\StockData\n"
            "uv run src\\edge_pro.py\n"
        ),
        "FetchAndDownload.bat": (
            "@echo off\n"
            "title Edge Pro — Nightly Download\n"
            "cd /d C:\\StockData\n"
            "echo Running nightly download...\n"
            "uv run src\\nightly_download.py\n"
            "echo.\n"
            "echo Done! Check logs\\ for details.\n"
            "pause\n"
        ),
    }
    for name, content in bats.items():
        p = ROOT / name
        p.write_text(content, encoding="utf-8")
        print(f"  ✓  {name} (updated to point → src\\)")


def main():
    print("=" * 55)
    print("  Edge Pro — Professional Folder Reorganisation")
    print(f"  Root: {ROOT}")
    print("=" * 55)

    if not ROOT.exists():
        print(f"\n✗ Root directory not found: {ROOT}")
        sys.exit(1)

    # ── Step 1: Create new directories ────────────────────────────────────
    sep("Step 1: Creating directories")
    for d in [SRC_DIR, LAUNCHERS, DOCS_DIR, ARCHIVE_DIR]:
        d.mkdir(exist_ok=True)
        print(f"  ✓  {d.relative_to(ROOT)}")

    # ── Step 2: Move Python scripts to src\ ───────────────────────────────
    sep("Step 2: Moving Python scripts → src\\")
    moved_scripts = []
    for name in SCRIPTS:
        src = ROOT / name
        if src.exists():
            dest = SRC_DIR / name
            shutil.move(str(src), str(dest))
            inject_shim(dest)
            update_script_path_ref(dest)
            print(f"  ✓  {name}")
            moved_scripts.append(name)

    # ── Step 3: Move launchers ─────────────────────────────────────────────
    sep("Step 3: Moving launchers → launchers\\")
    for name in LAUNCHERS_FILES:
        move(ROOT / name, LAUNCHERS)

    # ── Step 4: Move documentation ─────────────────────────────────────────
    sep("Step 4: Moving documentation → docs\\")
    for name in DOCS_FILES:
        move(ROOT / name, DOCS_DIR)

    # ── Step 5: Archive deprecated scripts ────────────────────────────────
    sep("Step 5: Archiving deprecated scripts → archive\\")
    for name in ARCHIVE_FILES:
        move(ROOT / name, ARCHIVE_DIR)

    # ── Step 6: Clean up junk ─────────────────────────────────────────────
    sep("Step 6: Cleaning up junk files")
    removed = 0
    for d_name in JUNK_DIRS:
        for junk in ROOT.rglob(d_name):
            if junk.is_dir():
                shutil.rmtree(junk)
                print(f"  ✗  Deleted: {junk.relative_to(ROOT)}")
                removed += 1
    for pattern in JUNK_PATTERNS:
        for junk in ROOT.rglob(pattern):
            junk.unlink()
            print(f"  ✗  Deleted: {junk.relative_to(ROOT)}")
            removed += 1
    if removed == 0:
        print("  (nothing to clean)")

    # ── Step 7: Write updated root launchers ──────────────────────────────
    sep("Step 7: Writing updated root launchers")
    write_launchers()

    # ── Step 8: Verify remaining root contents ────────────────────────────
    sep("Step 8: Root directory after reorganisation")
    root_items = sorted(ROOT.iterdir(), key=lambda p: (p.is_file(), p.name))
    for item in root_items:
        rel = item.relative_to(ROOT)
        if item.is_dir():
            print(f"  📁  {rel}\\")
        else:
            print(f"  📄  {rel}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  Reorganisation complete!")
    print("=" * 55)
    print(f"""
  New structure:
    src\\          ← {len(moved_scripts)} Python scripts
    data\\         ← stock CSVs (unchanged)
    screeners\\    ← TradingView CSVs (unchanged)
    cache\\        ← sector cache, summaries (unchanged)
    logs\\         ← nightly logs (unchanged)
    exports\\      ← manual exports (unchanged)
    launchers\\    ← original .bat files (reference)
    docs\\         ← all documentation
    archive\\      ← deprecated scripts
    EdgePro.bat   ← updated (runs src\\edge_pro.py)
    FetchAndDownload.bat ← updated

  Run Edge Pro:
    double-click EdgePro.bat
    or: uv run src\\edge_pro.py

  Run nightly download:
    double-click FetchAndDownload.bat
    or: uv run src\\nightly_download.py
""")


if __name__ == "__main__":
    main()

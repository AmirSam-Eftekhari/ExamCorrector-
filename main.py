#!/usr/bin/env python3
"""
ExamCorrector entry point.

Launches the local web UI (webapp/server.py) -- a real, tested, browser-based
GUI that needs only Flask (already in requirements.txt) and opens
automatically. This is the primary way to use ExamCorrector day to day.

Falls back to explaining what's missing rather than crashing if Flask isn't
installed yet, and mentions the CLI/console alternatives that need even
fewer dependencies.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(BASE_DIR))


def main() -> int:
    try:
        from webapp.server import main as run_web
    except ImportError as exc:
        print("Couldn't start the web UI -- a dependency is missing.")
        print(f"  ({exc})")
        print()
        print("Install dependencies with:  pip install -r requirements.txt")
        print()
        print("Lighter-weight alternatives that need less installed:")
        print("  python app_launcher.py                 -- interactive console menu")
        print("  python scripts/calibrate_template.py <clean_sheet.png> --name \"My Template\"")
        print("  python scripts/run_single_sheet.py <sheet.png> --template resources/templates/<file>.json "
              "--answer-key key.json")
        return 1

    run_web()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

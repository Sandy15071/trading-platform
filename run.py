#!/usr/bin/env python3
"""
Option Chain Momentum Indicator Launcher
Zerodha Kite Connect Standalone Analytics & Alert Dashboard
"""

import sys
import os
import argparse
import webbrowser
import threading
import time
import uvicorn
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import config

def open_browser_delayed(url: str, delay: float = 1.2):
    def _open():
        time.sleep(delay)
        print(f"\n[+] Launching dashboard in browser: {url}")
        webbrowser.open(url)
    t = threading.Thread(target=_open, daemon=True)
    t.start()

def main():
    parser = argparse.ArgumentParser(description="Zerodha Option Chain Momentum Indicator Dashboard")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", config.port)), help=f"Bind port (default: {config.port})")
    parser.add_argument("--mock", action="store_true", help="Force Simulation / Mock Data mode")
    parser.add_argument("--live", action="store_true", help="Force Live Kite Connect mode")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")

    args = parser.parse_args()

    if args.mock:
        config.update_env("MOCK_MODE", "true")
    elif args.live:
        config.update_env("MOCK_MODE", "false")

    url = f"http://{args.host}:{args.port}"
    print("=" * 65)
    print("[*] OPTION CHAIN MOMENTUM INDICATOR (ZERODHA KITE CONNECT)")
    print(f"[*] Mode: {'SIMULATION / MOCK DATA' if config.mock_mode else 'LIVE KITE CONNECT REST'}")
    print(f"[*] Dashboard URL: {url}")
    print("=" * 65)

    if not args.no_browser:
        open_browser_delayed(url)

    uvicorn.run(
        "backend.app:app",
        host=args.host,
        port=args.port,
        log_level="info",
        reload=False
    )

if __name__ == "__main__":
    main()

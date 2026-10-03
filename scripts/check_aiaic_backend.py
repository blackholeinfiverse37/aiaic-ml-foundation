"""Quick reachability check of an AIAIC server (its /health and /catalog), from this machine.

    AIAIC_API_BASE=http://<host>:<port> python scripts/check_aiaic_backend.py

There is no default address on purpose: this repository is public, and a server or tunnel address written here is
an address anyone can call. Pass it when you run the check.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urljoin

import requests


def fetch(base: str, path: str) -> int:
    resp = requests.get(urljoin(base + "/", path), timeout=20, headers={"ngrok-skip-browser-warning": "true"})
    print(f"{path}: HTTP {resp.status_code} :: {resp.text[:200].replace(chr(10), ' ')}")
    return resp.status_code


def main() -> int:
    base = (os.getenv("AIAIC_API_BASE") or "").strip().rstrip("/")
    if not base:
        print("Set AIAIC_API_BASE to the AIAIC server's address (e.g. http://127.0.0.1:8017).")
        return 2
    codes = [fetch(base, "health"), fetch(base, "catalog?state=maharashtra")]
    return 0 if all(c < 400 for c in codes) else 1


if __name__ == "__main__":
    sys.exit(main())

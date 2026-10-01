"""Quick health check against the external AIAIC backend.

Use:
    AIAIC_API_BASE=https://disarm-scrubbed-pushiness.ngrok-free.dev python scripts/check_aiaic_ngrok.py
    python scripts/check_aiaic_ngrok.py
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urljoin

import requests

DEFAULT_BASE = "https://disarm-scrubbed-pushiness.ngrok-free.dev"
BASE = os.getenv("AIAIC_API_BASE", os.getenv("VITE_AQIAIC_BASE_URL", DEFAULT_BASE)).rstrip("/")


def fetch(url: str, label: str) -> None:
    try:
        resp = requests.get(url, timeout=20)
        body = resp.text[:200].replace("\n", " ")
        print(f"{label}: HTTP {resp.status_code} :: {body}")
        if resp.status_code >= 400:
            raise RuntimeError(f"{label} failed with status {resp.status_code}")
    except Exception as exc:  # pragma: no cover - operational helper
        print(f"{label}: ERROR :: {exc}")
        raise


def main() -> int:
    print(f"AIAIC backend base: {BASE}")
    fetch(urljoin(BASE + "/", "health"), "health")
    fetch(urljoin(BASE + "/", "catalog?state=maharashtra"), "catalog")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1)

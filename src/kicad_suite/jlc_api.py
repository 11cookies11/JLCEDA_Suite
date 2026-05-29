"""JLC/LCSC component search and download via EasyEDA API.

Pure Python — no Node.js dependency.  Used by hwtool.exe directly.
Rate-limited at 1 call / *RATE_LIMIT_INTERVAL* seconds to mimic browser use.
"""

from __future__ import annotations

import json
import random
import re
import time as _time
import urllib.error
import urllib.request
from typing import Any

_SEARCH_URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList/v2"
_PRODUCT_URL = "https://lceda.cn/api/products/{lcsc_id}/components?version=6.4.19.5"

# Minimum interval between API calls (seconds).  Normal humans browse at
# roughly one click every second or two; we add slight jitter below.
_RATE_LIMIT_INTERVAL = 3.0
_last_call_time: float = 0.0

# Browser-like headers — no "ai" or "bot" markers.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

_LCSC_ID_RE = re.compile(r"/([A-Z]\d+)(?:\.html)?")


def _rate_limit() -> None:
    """Ensure minimum interval between API calls."""
    global _last_call_time
    now = _time.monotonic()
    wait = _last_call_time + _RATE_LIMIT_INTERVAL - now
    if wait > 0:
        _time.sleep(wait + random.uniform(0, 2.0))
    _last_call_time = _time.monotonic()


def _headers() -> dict[str, str]:
    """Build request headers that look like a normal browser."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://lceda.cn/",
        "Origin": "https://lceda.cn",
        "Cache-Control": "no-cache",
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search JLC/LCSC for components matching *query*.

    Returns a list of dicts with keys: ``lcsc_id``, ``name``, ``package``,
    ``stock``, ``price``, ``is_basic``.
    """
    _rate_limit()

    body = json.dumps({
        "keyword": query,
        "currentPage": 1,
        "pageSize": min(limit, 50),
        "searchType": 2,
    }).encode()

    req = urllib.request.Request(
        _SEARCH_URL,
        data=body,
        headers={**_headers(), "Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as exc:
        # 429 / 503 → back off and retry once
        if exc.code in (429, 503):
            _time.sleep(5 + random.uniform(0, 3))
            try:
                resp = urllib.request.urlopen(req, timeout=15)
            except OSError:
                return []
        else:
            return []
    except (OSError, urllib.error.URLError):
        return []

    try:
        payload = json.loads(resp.read())
    except (json.JSONDecodeError, OSError):
        return []

    results: list[dict[str, Any]] = []
    items = payload.get("data", {}).get("componentPageInfo", {}).get("list", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        lcsc_id = str(item.get("componentCode", ""))
        if not lcsc_id:
            url = str(item.get("lcscGoodsUrl", ""))
            m = _LCSC_ID_RE.search(url)
            if not m:
                continue
            lcsc_id = m.group(1)
        results.append({
            "lcsc_id": lcsc_id,
            "name": str(item.get("erpComponentName", "")),
            "package": str(item.get("componentTypeEn", "")),
            "stock": item.get("stockCount", 0),
            "price": _cheapest_price(item.get("componentPrices")),
            "is_basic": item.get("componentLibraryType") == "base",
        })
    return results[:limit]


def _cheapest_price(prices: Any) -> float | None:
    if not isinstance(prices, list) or not prices:
        return None
    best = None
    for p in prices:
        if isinstance(p, dict):
            pr = p.get("productPrice")
            if isinstance(pr, (int, float)) and (best is None or pr < best):
                best = float(pr)
    return best


# ---------------------------------------------------------------------------
# Component details
# ---------------------------------------------------------------------------


def get_component(lcsc_id: str, retries: int = 3, delay: float = 2.0) -> dict[str, Any] | None:
    """Fetch full component data from EasyEDA, including symbol and footprint shapes.

    Retries up to *retries* times with exponential backoff.  On HTTP 429
    the backoff is longer (starting at 10 s) because the server explicitly
    asked us to slow down.
    """
    _rate_limit()

    url = _PRODUCT_URL.format(lcsc_id=lcsc_id)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_headers())
            resp = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                backoff = 10 * (2 ** attempt)
                _time.sleep(backoff + random.uniform(0, 5))
            elif attempt < retries - 1:
                _time.sleep(delay * (2 ** attempt))
            else:
                return None
            continue
        except (OSError, urllib.error.URLError):
            if attempt < retries - 1:
                _time.sleep(delay * (2 ** attempt))
                continue
            return None

        try:
            payload = json.loads(resp.read())
        except (json.JSONDecodeError, OSError):
            if attempt < retries - 1:
                _time.sleep(delay * (2 ** attempt))
                continue
            return None

        if payload.get("success"):
            break
        if attempt < retries - 1:
            _time.sleep(delay * (2 ** attempt))
    else:
        return None

    result = payload.get("result", {})
    if not isinstance(result, dict):
        return None

    package = result.get("packageDetail") or {}
    return {
        "lcsc_id": lcsc_id,
        "title": str(result.get("title", "")),
        "package_title": str(package.get("title", "") if isinstance(package, dict) else ""),
        "data_str": result.get("dataStr", {}),
        "package_data_str": package.get("dataStr", {}) if isinstance(package, dict) else {},
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def extract_lcsc_id(text: str) -> str | None:
    """Extract LCSC ID from a URL or raw string like 'C1002'."""
    if text.startswith("C") and text[1:].isdigit():
        return text
    m = _LCSC_ID_RE.search(text)
    if m:
        return f"C{m.group(1)}"
    return None

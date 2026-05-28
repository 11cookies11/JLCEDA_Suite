"""JLC/LCSC component search and download via EasyEDA API.

Pure Python — no Node.js dependency.  Used by hwtool.exe directly.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

_SEARCH_URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList/v2"
_PRODUCT_URL = "https://easyeda.com/api/products/{lcsc_id}/components?version=6.4.19.5"
_HEADERS = {
    "User-Agent": "ai-eda-lcsc-mcp/1.0.0",
    "Accept": "application/json",
}
_LCSC_ID_RE = re.compile(r"/([A-Z]\d+)(?:\.html)?")


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search JLC/LCSC for components matching *query*.

    Returns a list of dicts with keys: ``lcsc_id``, ``name``, ``package``,
    ``stock``, ``price``, ``is_basic``.
    """
    body = json.dumps({"keyword": query, "currentPage": 1, "pageSize": min(limit, 50), "searchType": 2}).encode()
    req = urllib.request.Request(_SEARCH_URL, data=body, headers={**_HEADERS, "Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        payload = json.loads(resp.read())
    except (OSError, json.JSONDecodeError, urllib.error.URLError):
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


def get_component(lcsc_id: str, retries: int = 3, delay: float = 1.0) -> dict[str, Any] | None:
    """Fetch full component data from EasyEDA, including symbol and footprint shapes.

    Retries up to *retries* times with exponential backoff on failure.
    Returns a dict with ``data_str`` (symbol shapes) and ``package_detail`` (footprint).
    """
    import time as _time
    url = _PRODUCT_URL.format(lcsc_id=lcsc_id)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            resp = urllib.request.urlopen(req, timeout=15)
            payload = json.loads(resp.read())
        except (OSError, json.JSONDecodeError, urllib.error.URLError):
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


def extract_lcsc_id(text: str) -> str | None:
    """Extract LCSC ID from a URL or raw string like 'C1002'."""
    if text.startswith("C") and text[1:].isdigit():
        return text
    m = _LCSC_ID_RE.search(text)
    if m:
        return f"C{m.group(1)}"
    return None

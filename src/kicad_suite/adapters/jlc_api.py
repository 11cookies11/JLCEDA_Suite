"""JLC/LCSC component search and download via easyeda2kicad.

Delegates HTTP calls to the battle-tested easyeda2kicad library while keeping
our own rate limiting and caching layer on top.
"""

from __future__ import annotations

import random
import re
import time as _time
from typing import Any

_RATE_LIMIT_INTERVAL = 3.0
_last_call_time: float = 0.0

_LCSC_ID_RE = re.compile(r"/([A-Z]\d+)(?:\.html)?")


def _rate_limit() -> None:
    global _last_call_time
    now = _time.monotonic()
    wait = _last_call_time + _RATE_LIMIT_INTERVAL - now
    if wait > 0:
        _time.sleep(wait + random.uniform(0, 2.0))
    _last_call_time = _time.monotonic()


def _get_api():
    """Lazy-import the easyeda2kicad API client."""
    from easyeda2kicad.easyeda.easyeda_importer import EasyedaApi
    return EasyedaApi()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search JLC/LCSC for components matching *query*."""
    _rate_limit()
    api = _get_api()
    raw = api.search_jlcpcb_components(query, page_size=min(limit, 50))

    results: list[dict[str, Any]] = []
    for item in raw.get("results", []):
        results.append({
            "lcsc_id": str(item.get("lcsc", "")),
            "name": str(item.get("name", "")),
            "package": str(item.get("package", "")),
            "stock": item.get("stock", 0),
            "price": item.get("price"),
            "is_basic": item.get("type") == "Basic",
        })
    return results[:limit]


# ---------------------------------------------------------------------------
# Component details
# ---------------------------------------------------------------------------


def get_component(lcsc_id: str, retries: int = 3, delay: float = 2.0) -> dict[str, Any] | None:
    """Fetch full component data from EasyEDA (symbol + footprint shapes)."""
    _rate_limit()
    api = _get_api()

    for attempt in range(retries):
        try:
            cad_data = api.get_cad_data_of_component(lcsc_id)
            if cad_data:
                break
        except Exception:
            pass
        if attempt < retries - 1:
            _time.sleep(delay * (2 ** attempt))
    else:
        return None

    package = cad_data.get("packageDetail") or {}
    return {
        "lcsc_id": lcsc_id,
        "title": str(cad_data.get("title", "")),
        "package_title": str(package.get("title", "") if isinstance(package, dict) else ""),
        "data_str": cad_data.get("dataStr", {}),
        "package_data_str": package.get("dataStr", {}) if isinstance(package, dict) else {},
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def extract_lcsc_id(text: str) -> str | None:
    """Extract LCSC ID from a URL or raw string like C1002."""
    if text.startswith("C") and text[1:].isdigit():
        return text
    m = _LCSC_ID_RE.search(text)
    if m:
        return f"C{m.group(1)}"
    return None

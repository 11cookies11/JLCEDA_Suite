"""JLC/LCSC component search and download via easyeda2kicad.

Delegates HTTP calls to the battle-tested easyeda2kicad library while keeping
our own rate limiting and caching layer on top.

Rate-limiting design
--------------------
EasyEDA / JLCPCB APIs return 403 when they detect bot-like request patterns.
Key indicators that trigger their anti-scraping:
- Regular intervals between requests (a human pauses to read results)
- High request density over a sliding window (~10+ req/min)
- Identical User-Agent / headers on every call

Our countermeasures:
1. Minimum 8 s between calls with heavy jitter (0–5 s), yielding 8–13 s gaps
2. Consecutive-empty-result detection — when the API returns nothing for
   multiple calls in a row we suspect a block and escalate the backoff
3. Callers (jlc_installer) also insert per-component delays so a batch
   of 30 parts spreads across several minutes
"""

from __future__ import annotations

import logging
import random
import re
import time as _time
import urllib.error
from typing import Any

_RATE_LIMIT_INTERVAL = 8.0          # minimum seconds between API calls
_RATE_JITTER_MAX = 5.0              # extra random delay added on top
_BACKOFF_MULTIPLIER = 4.0           # multiplier applied when we suspect a block
_last_call_time: float = 0.0

# Consecutive-empty-result tracking: when the API returns nothing for multiple
# calls in a row we escalate the backoff (likely a 403 block that easyeda2kicad
# swallowed and returned as {}).
_empty_streak: int = 0
_MAX_EMPTY_BEFORE_ESCALATE = 3      # streak length that triggers escalated backoff
_ESCALATED_FAILURE_LIMIT = 3        # cap retries once we strongly suspect a block

_LCSC_ID_RE = re.compile(r"/([A-Z]\d+)(?:\.html)?")

logger = logging.getLogger(__name__)


def _rate_limit(*, escalated: bool = False) -> None:
    """Insert a delay before the next API call.

    *escalated* means we suspect the server is rate-limiting us; the delay
    is multiplied several-fold to let the block cool off.
    """
    global _last_call_time
    now = _time.monotonic()
    interval = _RATE_LIMIT_INTERVAL * (_BACKOFF_MULTIPLIER if escalated else 1.0)
    wait = _last_call_time + interval - now
    if wait > 0:
        jitter = random.uniform(0, _RATE_JITTER_MAX)
        _time.sleep(wait + jitter)
    _last_call_time = _time.monotonic()


def _note_result(got_data: bool) -> None:
    """Track consecutive empty results so we can escalate when needed."""
    global _empty_streak
    if got_data:
        _empty_streak = 0
    else:
        _empty_streak += 1


def _get_api():
    """Lazy-import the easyeda2kicad API client."""
    from easyeda2kicad.easyeda.easyeda_importer import EasyedaApi
    return EasyedaApi()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search JLC/LCSC for components matching *query*."""
    escalated = _empty_streak >= _MAX_EMPTY_BEFORE_ESCALATE
    _rate_limit(escalated=escalated)
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
    _note_result(len(results) > 0)
    if escalated and len(results) > 0:
        logger.info("API recovered after escalated backoff — block appears lifted")
    return results[:limit]


# ---------------------------------------------------------------------------
# Component details
# ---------------------------------------------------------------------------


def get_component(lcsc_id: str, retries: int = 3, delay: float = 2.0) -> dict[str, Any] | None:
    """Fetch full component data from EasyEDA (symbol + footprint shapes).

    When the EasyEDA API returns 403 the easyeda2kicad library swallows the
    HTTP status and returns an empty dict — so we treat consecutive empty
    results as a likely rate-limit signal and escalate the backoff.

    Once escalated, we cap the number of failed attempts so we do not burn
    time on a request that is very likely still blocked.
    """
    api = _get_api()
    escalated = _empty_streak >= _MAX_EMPTY_BEFORE_ESCALATE
    _escalated_failures = 0

    for attempt in range(retries):
        _rate_limit(escalated=escalated)
        try:
            cad_data = api.get_cad_data_of_component(lcsc_id)
        except Exception:
            cad_data = {}
        if cad_data:
            _note_result(True)
            if escalated:
                logger.info("API recovered after escalated backoff — block appears lifted")
            break
        _note_result(False)
        if escalated:
            _escalated_failures += 1
            if _escalated_failures >= _ESCALATED_FAILURE_LIMIT:
                logger.warning(
                    "Giving up on %s after %d escalated failures (streak=%d) – "
                    "server block likely requires minutes-long cooldown",
                    lcsc_id, _escalated_failures, _empty_streak,
                )
                return None
        if attempt < retries - 1:
            # Exponential backoff, multiplied when we suspect a 403 block
            backoff = delay * (2 ** attempt)
            if escalated:
                backoff *= _BACKOFF_MULTIPLIER
            logger.warning(
                "Empty response for %s (attempt %d/%d, empty_streak=%d)%s",
                lcsc_id, attempt + 1, retries, _empty_streak,
                " [escalated backoff — likely 403]" if escalated else "",
            )
            _time.sleep(backoff)
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

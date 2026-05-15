"""
LCSC Resolver — turns part requirements into ranked LCSC candidates.

Does NOT make final selection. Only searches + scores + organizes.
"""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import re
import time
import urllib.request
import urllib.parse
import urllib.error
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Protocol


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PartRequirement:
    """Input: what component we're looking for."""
    id: str                                    # "power_ldo"
    function: str                              # "3.3V LDO regulator"
    preferred_mpn: list[str] = field(default_factory=list)
    package_preferred: list[str] = field(default_factory=list)
    # Optional electrical constraints
    voltage_min: float | None = None
    current_min: float | None = None
    output_voltage: float | None = None        # e.g. 3.3 for a 3.3V regulator
    # Sourcing
    assembly: str = "JLCPCB"                   # assembly service, default JLCPCB
    price_max: float | None = None             # maximum acceptable unit price in USD
    # Search control
    category: str = ""                         # auto-inferred if empty; pass to override
    exclude_mpn: list[str] = field(default_factory=list)
    in_stock_only: bool = True
    basic_only: bool = False


@dataclass
class ResolvedPart:
    """Output: one candidate from LCSC (or EasyEDA community as fallback)."""
    lcsc_id: str                               # "C2040"
    mpn: str                                   # "AMS1117-3.3"
    manufacturer: str                          # "AMS"
    package: str                               # "SOT-223"
    description: str
    stock: int
    basic_or_extended: str                     # "Basic" | "Extended" | ""
    has_easyeda_symbol: bool
    has_easyeda_footprint: bool
    has_3d_model: bool
    source: str                                # "jlcpcb_parts" | "easyeda_community"
    confidence: float                          # 0.0 - 1.0
    price: float | None = None                 # unit price in USD from JLCPCB parts API


@dataclass
class ResolverResult:
    """Top-level output for a single requirement."""
    id: str
    candidates: list[ResolvedPart]
    query_context: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------


class SearchBackend(Protocol):
    """Protocol for search backends. Each result dict must include a '_source' key."""

    def search(self, query: str, limit: int, **kwargs: object) -> list[dict]:
        """Return raw search result dicts, each tagged with '_source'."""
        ...


# ---------------------------------------------------------------------------
# MCP HTTP backend — current HTTP API only serves EasyEDA community data
# ---------------------------------------------------------------------------


class McpHttpBackend:
    """Talks to the JLC MCP HTTP server at localhost:3847.

    The current HTTP API (/api/search) only returns EasyEDA community library
    results (user-uploaded symbols/footprints). JLCPCB parts store data (with
    stock, pricing, basic/extended status) requires the MCP stdio protocol.

    When the HTTP API gains JLCPCB parts search, this backend will detect the
    result format and tag accordingly.
    """

    def __init__(self, base_url: str = "http://localhost:3847", timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, query: str, limit: int = 10, **kwargs: object) -> list[dict]:
        url = f"{self._base_url}/api/search?q={urllib.parse.quote(query)}&limit={limit}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode())
            raw_results: list[dict] = body.get("results", [])
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []

        # Tag each result with its actual source based on data shape.
        # Community results have: uuid, packageUuid, owner, contributor, docType
        # JLCPCB parts results have: lcsc_id/lcsc, stock, part_type (future)
        for r in raw_results:
            if "lcsc_id" in r or "lcsc" in r or "stock" in r:
                r["_source"] = "jlcpcb_parts"
            elif "packageUuid" in r or "owner" in r:
                r["_source"] = "easyeda_community"
            else:
                r["_source"] = "easyeda_community"  # default
        return raw_results


class LcscOpenApiBackend:
    """Talks directly to LCSC's official OpenAPI product search.

    Required environment variables for normal CLI use:
    - LCSC_API_KEY
    - LCSC_API_SECRET

    Signature format follows LCSC documentation:
    sha1(key=xxx&nonce=xxx&secret=xxxx&timestamp=xxx)
    """

    def __init__(
        self,
        *,
        key: str = "",
        secret: str = "",
        base_url: str = "https://ips.lcsc.com",
        timeout: float = 15.0,
        currency: str = "USD",
    ) -> None:
        self._key = key or os.environ.get("LCSC_API_KEY", "")
        self._secret = secret or os.environ.get("LCSC_API_SECRET", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._currency = currency

    @property
    def configured(self) -> bool:
        return bool(self._key and self._secret)

    @property
    def base_url(self) -> str:
        return self._base_url

    def _signed_params(self) -> dict[str, str]:
        nonce = secrets.token_hex(8)[:16]
        timestamp = str(int(time.time() * 1000))
        payload = f"key={self._key}&nonce={nonce}&secret={self._secret}&timestamp={timestamp}"
        signature = hashlib.sha1(payload.encode("utf-8")).hexdigest()
        return {
            "key": self._key,
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": signature,
        }

    def search(self, query: str, limit: int = 10, **kwargs: object) -> list[dict]:
        if not self.configured:
            return []

        params: dict[str, object] = {
            **self._signed_params(),
            "keyword": query,
            "match_type": kwargs.get("match_type", "fuzzy"),
            "current_page": 1,
            "page_size": min(max(int(limit), 1), 30),
            "is_available": str(bool(kwargs.get("is_available", True))).lower(),
            "is_pre_sale": str(bool(kwargs.get("is_pre_sale", False))).lower(),
            "currency": kwargs.get("currency", self._currency),
        }
        url = f"{self._base_url}/rest/wmsc2agent/search/product?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []

        results = _extract_lcsc_product_dicts(body)
        for item in results:
            item["_source"] = "jlcpcb_parts"
        return results[:limit]


class JlcMcpCliBackend:
    """Search LCSC through the repository's @jlcpcb/mcp bridge script."""

    def __init__(
        self,
        *,
        bridge_script: str | Path | None = None,
        timeout: float = 30.0,
        source: str = "lcsc",
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self._bridge_script = Path(bridge_script) if bridge_script else repo_root / "scripts" / "jlc_mcp_bridge.mjs"
        self._timeout = timeout
        self._source = source

    @property
    def configured(self) -> bool:
        return self._bridge_script.exists()

    def search(self, query: str, limit: int = 10, **kwargs: object) -> list[dict]:
        if not self.configured:
            return []

        command = [
            "node",
            str(self._bridge_script),
            "search",
            "--query",
            query,
            "--source",
            self._source,
            "--limit",
            str(limit),
        ]
        if bool(kwargs.get("in_stock", kwargs.get("is_available", True))):
            command.append("--in-stock")
        if bool(kwargs.get("basic_only", False)):
            command.append("--basic-only")

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []

        if proc.returncode != 0:
            return []

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return []

        results = _extract_jlc_mcp_results(payload)
        for item in results:
            item["_source"] = "jlcpcb_parts"
        return results[:limit]


def _first_value(raw: dict, keys: list[str]) -> object:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    lowered = {str(k).lower(): v for k, v in raw.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return ""


def _extract_lcsc_product_dicts(payload: object) -> list[dict]:
    """Extract product-shaped dictionaries from flexible LCSC API JSON."""
    found: list[dict] = []

    def visit(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        if any(str(key).lower() in {
            "lcscpartnumber", "lcsc_part_number", "productnumber", "product_number",
            "productcode", "product_code", "productmodel", "product_model",
        } for key in value):
            found.append(value)
            return
        for child in value.values():
            visit(child)

    visit(payload)
    return found


def _extract_jlc_mcp_results(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result", payload)
    if isinstance(result, dict):
        raw_results = result.get("results", [])
        if isinstance(raw_results, list):
            return [item for item in raw_results if isinstance(item, dict)]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def get_default_backend(*, timeout: float = 15.0) -> SearchBackend:
    """Choose the best live search backend for the current environment.

    Prefer LCSC's official OpenAPI when credentials are configured. Otherwise
    fall back to the legacy local MCP HTTP backend.
    """
    jlc_mcp = JlcMcpCliBackend(timeout=timeout)
    if os.environ.get("KICAD_DISABLE_JLC_MCP", "").lower() not in {"1", "true", "yes"} and jlc_mcp.configured:
        return jlc_mcp

    openapi = LcscOpenApiBackend(
        base_url=os.environ.get("LCSC_OPENAPI_BASE_URL", "https://ips.lcsc.com"),
        timeout=timeout,
        currency=os.environ.get("LCSC_OPENAPI_CURRENCY", "USD"),
    )
    if openapi.configured:
        return openapi

    return McpHttpBackend(
        base_url=os.environ.get("LCSC_MCP_BASE_URL", "http://localhost:3847"),
        timeout=timeout,
    )


def describe_live_backend_status() -> dict[str, object]:
    """Return a small, serializable status object for CLI preflight checks."""
    jlc_mcp = JlcMcpCliBackend(timeout=float(os.environ.get("JLC_MCP_TIMEOUT_SEC", "30.0")))
    if os.environ.get("KICAD_DISABLE_JLC_MCP", "").lower() not in {"1", "true", "yes"} and jlc_mcp.configured:
        return {
            "ok": True,
            "backend": "jlc_mcp_cli",
            "bridge_script": str(jlc_mcp._bridge_script),
        }

    openapi = LcscOpenApiBackend(
        base_url=os.environ.get("LCSC_OPENAPI_BASE_URL", "https://ips.lcsc.com"),
        timeout=float(os.environ.get("LCSC_OPENAPI_TIMEOUT_SEC", "3.0")),
        currency=os.environ.get("LCSC_OPENAPI_CURRENCY", "USD"),
    )
    if openapi.configured:
        return {
            "ok": True,
            "backend": "lcsc_openapi",
            "base_url": openapi.base_url,
        }

    mcp_base_url = os.environ.get("LCSC_MCP_BASE_URL", "http://localhost:3847")
    return {
        "ok": False,
        "backend": "unconfigured",
        "base_url": mcp_base_url,
        "hint": (
            "Run npm install to enable the @jlcpcb/mcp bridge, set LCSC_API_KEY "
            "and LCSC_API_SECRET for LCSC official OpenAPI, or start a local MCP "
            "HTTP server that exposes /api/search."
        ),
    }


# ---------------------------------------------------------------------------
# Category auto-inference
# ---------------------------------------------------------------------------

# Keyword → (category, weight). Higher weight = more definitive component indicator.
# Generic words like "usb", "uart" get low weight; specific types like "diode", "mosfet" get high weight.
_CATEGORY_WEIGHTS: list[tuple[str, str, int]] = [
    # keyword               category              weight
    ("ldo",                 "voltage_regulator",   8),
    ("regulator",           "voltage_regulator",   7),
    ("buck",                "voltage_regulator",   8),
    ("boost",               "voltage_regulator",   8),
    ("dc-dc",               "voltage_regulator",   8),
    ("dc/dc",               "voltage_regulator",   8),
    ("pmic",                "voltage_regulator",   8),
    ("power management",    "voltage_regulator",   7),
    ("capacitor",           "capacitor",           8),
    ("electrolytic",        "capacitor",           8),
    ("tantalum",            "capacitor",           8),
    ("mlcc",                "capacitor",           8),
    ("ceramic cap",         "capacitor",           8),
    ("resistor",            "resistor",            8),
    ("inductor",            "inductor",            8),
    ("ferrite",             "inductor",            8),
    ("bead",                "inductor",            8),
    ("choke",               "inductor",            8),
    ("microcontroller",     "mcu",                 9),
    ("mcu",                 "mcu",                 8),
    ("stm32",               "mcu",                 9),
    ("esp32",               "mcu",                 9),
    ("nrf52",               "mcu",                 9),
    ("rp2040",              "mcu",                 9),
    ("risc-v",              "mcu",                 8),
    ("diode",               "diode",               9),
    ("led",                 "diode",               8),
    ("zener",               "diode",               9),
    ("schottky",            "diode",               9),
    ("tvs",                 "diode",               9),
    ("esd",                 "diode",               8),
    ("mosfet",              "transistor",          9),
    ("bjt",                 "transistor",          9),
    ("igbt",                "transistor",          9),
    ("transistor",          "transistor",          8),
    ("crystal",             "crystal",             9),
    ("oscillator",          "crystal",             8),
    ("xtal",                "crystal",             9),
    ("fuse",                "fuse",                9),
    ("ptc",                 "fuse",                9),
    ("polyfuse",            "fuse",                9),
    ("sensor",              "sensor",              8),
    ("accelerometer",       "sensor",              9),
    ("gyroscope",           "sensor",              9),
    ("imu",                 "sensor",              9),
    ("temperature sensor",  "sensor",              9),
    ("flash",               "memory",              8),
    ("eeprom",              "memory",              9),
    ("sd card",             "memory",              8),
    ("ethernet phy",        "interface",           8),
    ("usb to",              "interface",           7),
    ("usb-to",              "interface",           7),
    ("rs232",               "interface",           8),
    ("rs485",               "interface",           8),
    ("connector",           "connector",           8),
    ("header",              "connector",           7),
    ("socket",              "connector",           7),
    ("usb",                 "connector",           3),   # weak — often just context
    ("jst",                 "connector",           8),
    ("molex",               "connector",           8),
    ("rj45",                "connector",           8),
    ("fpc",                 "connector",           8),
    ("ffc",                 "connector",           8),
    ("switch",              "switch",              8),
    ("tactile",             "switch",              8),
    ("uart",                "interface",           4),   # weak — often just a peripheral
    ("spi",                 "interface",           4),
    ("i2c",                 "interface",           4),
    ("can",                 "interface",           4),
]


def infer_category(function: str) -> str:
    """Guess component category from the function description text.

    Uses weighted keyword matching — specific component-type words
    (diode, mosfet, capacitor) outweigh generic context words (usb, uart).
    """
    text = function.lower()
    best_weight = 0
    best_category = ""
    for keyword, category, weight in _CATEGORY_WEIGHTS:
        if keyword in text and weight > best_weight:
            best_weight = weight
            best_category = category
    return best_category


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------


def _normalize_pkg(s: str) -> str:
    """Normalize a package string for comparison: lowercase, strip hyphens/spaces."""
    return re.sub(r"[-_\s]+", "", s.lower())


def _score_candidate(
    candidate: ResolvedPart,
    preferred_mpns: list[str],
    preferred_packages: list[str],
) -> float:
    score = 0.0
    mpn_lower = candidate.mpn.lower()

    # Community results carry a _scan_text attribute with merged text fields
    scan_text: str = getattr(candidate, "_scan_text", "")

    # MPN match
    for mpn in preferred_mpns:
        mpn_norm = mpn.lower()
        if mpn_norm in mpn_lower or mpn_lower in mpn_norm:
            score += 0.30
            break

    # Package match — normalize hyphens/spaces before comparing
    for pkg in preferred_packages:
        pkg_norm = _normalize_pkg(pkg)
        pkg_field_norm = _normalize_pkg(candidate.package)
        # Exact match after normalization
        if pkg_norm == pkg_field_norm:
            score += 0.25
            break
        # Partial match after normalization
        if pkg_norm in pkg_field_norm or pkg_field_norm in pkg_norm:
            score += 0.15
            break
        # Fallback: scan merged text (community results often bury package in title)
        scan_norm = _normalize_pkg(scan_text) if scan_text else ""
        if scan_norm and pkg_norm in scan_norm:
            score += 0.10
            break

    # Basic / Extended
    if candidate.basic_or_extended == "Basic":
        score += 0.20

    # Stock depth
    if candidate.stock >= 1000:
        score += 0.15
    elif candidate.stock >= 100:
        score += 0.10

    # Library completeness
    if candidate.has_easyeda_symbol and candidate.has_easyeda_footprint and candidate.has_3d_model:
        score += 0.10
    elif candidate.has_easyeda_symbol and candidate.has_easyeda_footprint:
        score += 0.05

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def _build_queries(requirement: PartRequirement, category: str) -> list[tuple[str, str]]:
    """Build (query_string, source) pairs. First round = JLCPCB parts, second = community."""
    queries: list[tuple[str, str]] = []

    # Round 1: Exact MPN search against JLCPCB parts
    for mpn in requirement.preferred_mpn:
        q = mpn
        if requirement.package_preferred:
            q += " " + " ".join(requirement.package_preferred)
        queries.append((q, "jlcpcb_parts"))

    # Round 2: Function + package search against JLCPCB parts
    q = requirement.function
    if requirement.package_preferred:
        q += " " + " ".join(requirement.package_preferred)
    if category:
        q += " " + category.replace("_", " ")
    queries.append((q, "jlcpcb_parts"))

    # Round 3 (fallback): Community library
    for mpn in requirement.preferred_mpn:
        queries.append((mpn, "easyeda_community"))

    return queries


# ---------------------------------------------------------------------------
# Result normalization
# ---------------------------------------------------------------------------


def _normalize_result(raw: dict) -> ResolvedPart:
    """Convert a raw result dict → ResolvedPart, dispatching on _source tag."""
    source = raw.get("_source", "easyeda_community")

    if source == "jlcpcb_parts":
        price_raw = raw.get("price", raw.get("unit_price"))
        if price_raw is None:
            price_raw = _first_value(raw, ["price", "unit_price", "productPrice", "product_price"])
        try:
            price_val = float(price_raw) if price_raw is not None else None
        except (TypeError, ValueError):
            price_val = None
        return ResolvedPart(
            lcsc_id=str(_first_value(raw, ["lcsc_id", "lcsc", "lcscPartNumber", "lcsc_part_number", "productNumber", "product_number", "productCode", "product_code"])),
            mpn=str(_first_value(raw, ["mpn", "name", "productModel", "product_model", "productName", "product_name", "title"])),
            manufacturer=str(_first_value(raw, ["manufacturer", "brand_name", "brandName", "brand", "manufacturerName"])),
            package=str(_first_value(raw, ["package", "packageType", "package_type", "encapStandard", "encap_standard"])),
            description=str(_first_value(raw, ["description", "productDesc", "product_desc", "title", "productName", "product_name"])),
            stock=int(_first_value(raw, ["stock", "stock_number", "stockNumber", "quantity", "productStock"]) or 0),
            basic_or_extended=str(_first_value(raw, ["basic_or_extended", "library_type", "part_type", "productType", "componentType", "assemblyType"])).title(),
            price=price_val,
            has_easyeda_symbol=bool(raw.get("has_symbol", False)),
            has_easyeda_footprint=bool(raw.get("has_footprint", False)),
            has_3d_model=bool(raw.get("has_3d_model", False)),
            source="jlcpcb_parts",
            confidence=0.0,
        )

    # EasyEDA community
    raw_title = raw.get("title", "")
    raw_pkg = raw.get("package", "")
    raw_desc = raw.get("description", "")
    # Merge all text fields for package-match scanning — community "package"
    # field is the EasyEDA package name, not always the physical package.
    scan_text = f"{raw_title} {raw_pkg} {raw_desc}"

    part = ResolvedPart(
        lcsc_id="",
        mpn=raw_title,
        manufacturer=raw.get("manufacturer", ""),
        package=raw_pkg,
        description=raw_desc,
        stock=0,
        basic_or_extended="",
        has_easyeda_symbol=True,
        has_easyeda_footprint=True,
        has_3d_model=raw.get("has3DModel", False),
        source="easyeda_community",
        confidence=0.0,
    )
    part._scan_text = scan_text  # type: ignore[attr-defined]
    return part


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def resolve(
    requirement: PartRequirement,
    backend: SearchBackend | None = None,
    *,
    max_candidates: int = 5,
) -> ResolverResult:
    """Resolve a part requirement into ranked LCSC candidates.

    Args:
        requirement: What to search for.
        backend: Search backend. Uses McpHttpBackend by default.
        max_candidates: Max candidates to return (default 5).

    Returns:
        ResolverResult with ranked candidates.
    """
    if backend is None:
        backend = get_default_backend()

    category = requirement.category or infer_category(requirement.function)
    queries = _build_queries(requirement, category)

    all_candidates: list[ResolvedPart] = []
    seen_ids: set[str] = set()

    for query_str, _source_hint in queries:
        if len(all_candidates) >= max_candidates:
            break

        raw_results = backend.search(
            query_str,
            limit=10,
            in_stock=requirement.in_stock_only,
            basic_only=requirement.basic_only,
        )

        for raw in raw_results:
            candidate = _normalize_result(raw)

            # Deduplicate
            dedup_key = f"{candidate.lcsc_id}|{candidate.mpn}|{candidate.package}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            # Filter excluded MPNs
            if any(excl.lower() in candidate.mpn.lower() for excl in requirement.exclude_mpn):
                continue

            candidate.confidence = _score_candidate(
                candidate,
                requirement.preferred_mpn,
                requirement.package_preferred,
            )
            all_candidates.append(candidate)

    # Strip internal fields before returning
    for c in all_candidates:
        try:
            del c._scan_text  # type: ignore[attr-defined]
        except AttributeError:
            pass

    # Sort by confidence desc
    all_candidates.sort(key=lambda c: c.confidence, reverse=True)
    all_candidates = all_candidates[:max_candidates]

    return ResolverResult(
        id=requirement.id,
        candidates=all_candidates,
        query_context={
            "queries": [{"query": q, "source": s} for q, s in queries],
            "category_inferred": category,
            "in_stock_only": requirement.in_stock_only,
            "basic_only": requirement.basic_only,
        },
    )


# ---------------------------------------------------------------------------
# Batch resolve
# ---------------------------------------------------------------------------


def resolve_many(
    requirements: list[PartRequirement],
    backend: SearchBackend | None = None,
    *,
    max_candidates: int = 5,
) -> list[ResolverResult]:
    """Resolve multiple requirements. Each gets its own ResolverResult."""
    return [resolve(req, backend, max_candidates=max_candidates) for req in requirements]

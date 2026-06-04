"""
Part Selector — scores candidates and makes final component selection.

Takes ResolverResult + PartRequirement → produces SelectedPart with reasons, risks, and review flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...adapters.lcsc_resolver import PartRequirement, ResolvedPart, ResolverResult


# ---------------------------------------------------------------------------
# Complex package keywords that reduce score
# ---------------------------------------------------------------------------

_COMPLEX_PACKAGE_KEYWORDS: set[str] = {
    "bga", "qfn", "vqfn", "wqfn", "lga", "qfp", "tqfp",
    "dfn", "son", "wson", "csp", "wlcsp",
}

# ---------------------------------------------------------------------------
# EasyEDA import risk classification by package type
# ---------------------------------------------------------------------------

# Low risk: standard SMD passives and common IC packages
_LOW_RISK_PACKAGES: set[str] = {
    "0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512",
    "sot-23", "sot-323", "sot-363", "sot-523", "sot-223",
    "sop", "sop-8", "sop-16", "ssop", "tssop", "msop",
    "qfn", "vqfn", "dfn", "qfp", "tqfp", "lqfp",
    "3225", "5032", "2520", "2016",  # SMD crystal packages
}

# Medium risk: modules, edge-pad devices, large ICs, special headers
_MEDIUM_RISK_PACKAGES: set[str] = {
    "bga", "lga", "wlcsp", "csp",
    "to-252", "to-263", "d2pak", "dpak",
}

# High risk: keywords that indicate complex mechanical requirements
_HIGH_RISK_KEYWORDS: list[str] = [
    "usb", "usb-c", "usb-a", "micro-usb", "mini-usb",
    "fpc", "ffc",
    "tf-card", "tf card", "microsd", "sd-card", "sd card",
    "sim-card", "sim card",
    "dc jack", "dc-jack", "barrel jack", "barrel-jack",
    "rj45", "rj11", "rj12",
    "hdmi",
    "slotted", "slot", "oblong",
    "battery", "coin-cell", "coin cell",
    "edge-connector", "edge connector",
    "board-to-board", "board to board",
    "mezzanine",
]


def classify_package_risk(package: str) -> str:
    """Classify a package into EasyEDA import risk level.

    Returns "low", "medium", or "high".
    """
    pkg = _normalize_pkg(package)

    # Check high-risk keywords first (normalize to match normalized pkg)
    for keyword in _HIGH_RISK_KEYWORDS:
        if _normalize_pkg(keyword) in pkg:
            return "high"

    # Check medium-risk packages (normalize to match)
    for keyword in _MEDIUM_RISK_PACKAGES:
        if _normalize_pkg(keyword) in pkg:
            return "medium"

    # Check if module-like (contains "module" in name)
    if "module" in pkg:
        return "medium"

    # Check if it's a pin header / connector (generic catch)
    for keyword in ("header", "connector", "conn", "socket", "plug", "jack", "receptacle", "terminal"):
        if keyword in pkg:
            return "medium"

    # Check low-risk packages (normalize to match)
    for keyword in _LOW_RISK_PACKAGES:
        if _normalize_pkg(keyword) in pkg:
            return "low"

    # Default: unknown package → medium risk (needs evaluation)
    return "medium"


def package_risk_note(package: str, risk: str) -> str:
    """Generate a human-readable note explaining the risk classification."""
    if risk == "low":
        return "Standard package — low import risk"
    if risk == "high":
        pkg = _normalize_pkg(package)
        if any(k in pkg for k in ("usb",)):
            return "USB connector — may include shell pads, locating holes, or slot holes"
        if any(k in pkg for k in ("fpc", "ffc")):
            return "FPC/FFC connector — fine pitch, may need exact footprint matching"
        if any(k in pkg for k in ("tf", "sd", "microsd")):
            return "Card socket — mechanical complexity, may include locating pins and detection switches"
        if any(k in pkg for k in ("sim",)):
            return "SIM card socket — complex mechanical footprint"
        if any(k in pkg for k in ("jack", "dc", "barrel")):
            return "DC/barrel jack — through-hole alignment, mechanical mounting holes"
        if any(k in pkg for k in ("hdmi",)):
            return "HDMI connector — high pin count, mechanical alignment features"
        return "Complex mechanical package — KiCad → EasyEDA Pro conversion may fail"
    if risk == "medium":
        pkg = _normalize_pkg(package)
        if "module" in pkg:
            return "Module package — edge pads may need manual verification"
        if "bga" in pkg:
            return "BGA package — requires X-ray inspection, complex footprint"
        if "header" in pkg or "conn" in pkg:
            return "Header/connector — verify pin pitch and count match"
        return "Non-standard package — recommend manual review of footprint"
    return ""

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RiskItem:
    """A single risk flagged during part selection."""
    category: str          # e.g. "score_too_low", "package_risk", "stock_risk", "price_risk", "missing_data", "source_risk"
    message: str
    level: str             # "low", "medium", "high"


@dataclass
class SelectedPart:
    """The final selected part for a requirement with rationale."""
    requirement_id: str
    lcsc_id: str
    mpn: str
    manufacturer: str
    package: str
    description: str
    price: float | None
    stock: int
    basic_or_extended: str
    has_easyeda_symbol: bool
    has_easyeda_footprint: bool
    has_3d_model: bool
    source: str
    confidence: float          # inherited from ResolverResult
    composite_score: float     # 0-100, calculated by part_selector
    reasons: list[str]
    risks: list[RiskItem]
    needs_review: bool
    part_id: str = ""
    display_name: str = ""
    ref: str = ""              # reference designator, e.g. "U1", "R1" — filled by schematic
    value: str = ""            # e.g. "10k", "100nF" for passives
    note: str = ""             # human note, e.g. "模块封装需要人工检查边缘焊盘"


@dataclass
class SelectionResult:
    """Top-level output for a single requirement selection."""
    requirement_id: str
    selected: SelectedPart | None
    all_candidates: list[SelectedPart]
    summary: str


# ---------------------------------------------------------------------------
# Package normalization
# ---------------------------------------------------------------------------


def _normalize_pkg(s: str) -> str:
    """Normalize a package string: lowercase, strip hyphens/spaces."""
    return re.sub(r"[-_\s]+", "", s.lower())


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


def _score_part(
    candidate: ResolvedPart,
    requirement: PartRequirement,
) -> tuple[float, list[str]]:
    """Calculate composite score (0-100) and build selection reasons.

    Scoring rules:
    1. MPN exact match +50, partial +30
    2. Package exact match +25, partial +15
    3. JLCPCB Basic Part +15
    4. Stock depth (+10 max)
    5. Library completeness (+10 full, +5 partial)
    6. Price within budget (+10 max, proportional)
    7. Complex package penalty -15
    """
    reasons: list[str] = []
    score = 0.0

    # 1. MPN match
    for mpn in requirement.preferred_mpn:
        if candidate.mpn.strip().lower() == mpn.strip().lower():
            score += 50.0
            reasons.append(f"MPN exact match: {candidate.mpn}")
            break
        elif mpn.strip().lower() in candidate.mpn.strip().lower():
            score += 30.0
            reasons.append(f"MPN partial match: {candidate.mpn}")
            break

    # 2. Package match
    pkg_norm = _normalize_pkg(candidate.package)
    for pkg in requirement.package_preferred:
        req_pkg_norm = _normalize_pkg(pkg)
        if req_pkg_norm == pkg_norm:
            score += 25.0
            reasons.append(f"Package exact match: {candidate.package}")
            break
        elif req_pkg_norm in pkg_norm or pkg_norm in req_pkg_norm:
            score += 15.0
            reasons.append(f"Package partial match: {candidate.package}")
            break

    # 3. JLCPCB Basic Part
    if candidate.basic_or_extended == "Basic":
        score += 15.0
        reasons.append("JLCPCB Basic Part")

    # 4. Stock depth
    if candidate.stock >= 10000:
        score += 10.0
        reasons.append(f"Very high stock: {candidate.stock}")
    elif candidate.stock >= 1000:
        score += 7.0
        reasons.append(f"High stock: {candidate.stock}")
    elif candidate.stock >= 100:
        score += 4.0
        reasons.append(f"Adequate stock: {candidate.stock}")

    # 5. Library completeness
    if candidate.has_easyeda_symbol and candidate.has_easyeda_footprint and candidate.has_3d_model:
        score += 10.0
        reasons.append("Complete EasyEDA library: symbol + footprint + 3D model")
    elif candidate.has_easyeda_symbol and candidate.has_easyeda_footprint:
        score += 5.0
        reasons.append("EasyEDA symbol + footprint available")

    # 6. Price within budget
    if candidate.price is not None and requirement.price_max is not None and requirement.price_max > 0:
        if candidate.price <= requirement.price_max:
            price_ratio = candidate.price / requirement.price_max
            price_score = 10.0 * (1.0 - min(price_ratio, 1.0))
            score += price_score
            reasons.append(f"Price ${candidate.price:.4f} within budget ${requirement.price_max:.4f}")

    # 7. Complex package penalty
    for keyword in _COMPLEX_PACKAGE_KEYWORDS:
        if keyword in pkg_norm:
            score -= 15.0
            reasons.append(f"Complex package penalty: {candidate.package}")
            break

    return min(max(score, 0.0), 100.0), reasons


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------


def _assess_risks(
    candidate: ResolvedPart,
    requirement: PartRequirement,
    composite_score: float,
) -> list[RiskItem]:
    """Identify risk flags for a candidate part."""
    risks: list[RiskItem] = []

    # Score too low
    if composite_score < 30.0:
        risks.append(RiskItem("score_too_low", f"Selection score only {composite_score:.1f}/100 — verify suitability", "high"))
    elif composite_score < 50.0:
        risks.append(RiskItem("score_too_low", f"Selection score {composite_score:.1f}/100 below optimal threshold", "medium"))

    # Complex package
    pkg_lower = _normalize_pkg(candidate.package)
    if "bga" in pkg_lower:
        risks.append(RiskItem("package_risk", f"BGA package ({candidate.package}) requires X-ray inspection", "high"))
    for keyword in ("qfn", "lga", "dfn", "wlcsp", "csp"):
        if keyword in pkg_lower:
            risks.append(RiskItem("package_risk", f"Complex package ({candidate.package}) requires careful reflow soldering", "medium"))
            break

    # Low stock
    if candidate.stock < 100:
        risks.append(RiskItem("stock_risk", f"Low stock ({candidate.stock}) — may become unavailable before production", "high"))
    elif candidate.stock < 1000:
        risks.append(RiskItem("stock_risk", f"Limited stock ({candidate.stock}) — monitor availability", "low"))

    # Missing price
    if candidate.price is None:
        risks.append(RiskItem("missing_data", "Price not available — cannot evaluate budget compliance", "medium"))

    # No 3D model
    if not candidate.has_3d_model:
        risks.append(RiskItem("missing_data", "No 3D model — cannot verify mechanical fit", "low"))

    # Community source
    if candidate.source != "jlcpcb_parts":
        risks.append(RiskItem("source_risk", "Community-sourced part — verify authenticity and availability", "medium"))

    # Price exceeds budget
    if requirement.price_max is not None and candidate.price is not None and candidate.price > requirement.price_max:
        risks.append(RiskItem("price_risk", f"Price ${candidate.price:.4f} exceeds budget ${requirement.price_max:.4f}", "medium"))

    return risks


# ---------------------------------------------------------------------------
# Needs-review determination
# ---------------------------------------------------------------------------


def _needs_review(
    composite_score: float,
    risks: list[RiskItem],
    candidate: ResolvedPart,
    requirement: PartRequirement,
) -> bool:
    """Determine if this selection needs manual review."""
    if composite_score < 40.0:
        return True
    if any(r.level == "high" for r in risks):
        return True
    if not candidate.lcsc_id:
        return True
    if requirement.price_max is not None and candidate.price is not None and candidate.price > requirement.price_max * 1.5:
        return True
    if len(risks) >= 3:
        return True
    return False


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def select_part(
    requirement: PartRequirement,
    resolver_result: ResolverResult,
    *,
    min_score: float = 0.0,
) -> SelectionResult:
    """Select the best part from resolver candidates for a requirement.

    Args:
        requirement: Original part requirement.
        resolver_result: Ranked candidates from LCSC resolver.
        min_score: Minimum composite score (0-100) to accept any part.

    Returns:
        SelectionResult with best candidate or None.
    """
    scored: list[SelectedPart] = []
    for candidate in resolver_result.candidates:
        score, reasons = _score_part(candidate, requirement)
        risks = _assess_risks(candidate, requirement, score)
        review = _needs_review(score, risks, candidate, requirement)

        selected = SelectedPart(
            requirement_id=requirement.id,
            lcsc_id=candidate.lcsc_id,
            mpn=candidate.mpn,
            manufacturer=candidate.manufacturer,
            package=candidate.package,
            description=candidate.description,
            price=candidate.price,
            stock=candidate.stock,
            basic_or_extended=candidate.basic_or_extended,
            has_easyeda_symbol=candidate.has_easyeda_symbol,
            has_easyeda_footprint=candidate.has_easyeda_footprint,
            has_3d_model=candidate.has_3d_model,
            source=candidate.source,
            confidence=candidate.confidence,
            composite_score=score,
            reasons=reasons,
            risks=risks,
            needs_review=review,
            part_id=candidate.lcsc_id or requirement.id,
            display_name=candidate.description or candidate.mpn or requirement.function,
            value=requirement.function,  # rough initial value; refined later in pipeline
            note="",
        )
        scored.append(selected)

    scored = [s for s in scored if s.composite_score >= min_score]
    scored.sort(key=lambda s: (s.composite_score, s.confidence), reverse=True)

    best = scored[0] if scored else None

    if best is None:
        summary = f"[{requirement.id}] No acceptable part found (min_score={min_score})"
    elif best.needs_review:
        summary = f"[{requirement.id}] Selected {best.mpn} ({best.lcsc_id}) score={best.composite_score:.0f}/100 — REVIEW NEEDED ({len(best.risks)} risk(s))"
    else:
        summary = f"[{requirement.id}] Selected {best.mpn} ({best.lcsc_id}) score={best.composite_score:.0f}/100"

    return SelectionResult(
        requirement_id=requirement.id,
        selected=best,
        all_candidates=scored,
        summary=summary,
    )


def select_parts(
    requirements: list[PartRequirement],
    resolver_results: list[ResolverResult],
    *,
    min_score: float = 0.0,
) -> list[SelectionResult]:
    """Select best parts for multiple requirements.

    Matches requirements to resolver results by id.
    """
    results_by_id: dict[str, ResolverResult] = {r.id: r for r in resolver_results}
    selections: list[SelectionResult] = []
    for req in requirements:
        res = results_by_id.get(req.id)
        if res is None:
            selections.append(SelectionResult(
                requirement_id=req.id,
                selected=None,
                all_candidates=[],
                summary=f"[{req.id}] No resolver result found",
            ))
        else:
            selections.append(select_part(req, res, min_score=min_score))
    return selections

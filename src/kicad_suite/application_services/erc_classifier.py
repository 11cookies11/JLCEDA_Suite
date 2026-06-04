"""Classify KiCad ERC findings into agent-actionable buckets."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ERC_CLASSIFICATION_SCHEMA_VERSION = "erc-classification.v1"

BUCKET_MUST_FIX = "must_fix"
BUCKET_LIBRARY_NOISE = "library_noise"
BUCKET_REVIEW_REQUIRED = "review_required"

PASSIVE_REFS = ("R", "C", "D", "L", "Y", "J", "SW")

_PIN_TYPE_PATTERN = re.compile(r"\[([^\]]+)\]")
_SYMBOL_REF_PATTERN = re.compile(r"Symbol\s+([#A-Za-z]+\d*)")


def classify_erc_file(path: str | Path) -> dict[str, Any]:
    """Read a KiCad ERC JSON file and classify its findings."""
    erc_data = json.loads(Path(path).read_text(encoding="utf-8"))
    return classify_erc_report(erc_data)


def classify_erc_report(erc_data: dict[str, Any]) -> dict[str, Any]:
    """Classify KiCad ERC report data into stable agent buckets."""
    findings = _flatten_findings(erc_data)
    buckets: dict[str, list[dict[str, Any]]] = {
        BUCKET_MUST_FIX: [],
        BUCKET_LIBRARY_NOISE: [],
        BUCKET_REVIEW_REQUIRED: [],
    }
    type_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()

    for finding in findings:
        type_counts[str(finding.get("type", "?"))] += 1
        severity_counts[str(finding.get("severity", "?"))] += 1
        bucket, reason, action = _classify_finding(finding)
        item = {
            "sheet": finding.get("sheet", ""),
            "type": finding.get("type", ""),
            "severity": finding.get("severity", ""),
            "description": finding.get("description", ""),
            "items": finding.get("items", []),
            "reason": reason,
            "suggested_action": action,
        }
        buckets[bucket].append(item)

    return {
        "schema_version": ERC_CLASSIFICATION_SCHEMA_VERSION,
        "finding_count": len(findings),
        "counts": {
            "must_fix": len(buckets[BUCKET_MUST_FIX]),
            "library_noise": len(buckets[BUCKET_LIBRARY_NOISE]),
            "review_required": len(buckets[BUCKET_REVIEW_REQUIRED]),
        },
        "by_type": dict(type_counts),
        "by_severity": dict(severity_counts),
        "buckets": buckets,
    }


def _flatten_findings(erc_data: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for sheet in erc_data.get("sheets", []):
        if not isinstance(sheet, dict):
            continue
        sheet_path = str(sheet.get("path", ""))
        for violation in sheet.get("violations", []):
            if not isinstance(violation, dict):
                continue
            items = [
                str(item.get("description", ""))
                for item in violation.get("items", [])
                if isinstance(item, dict)
            ]
            findings.append({
                "sheet": sheet_path,
                "type": str(violation.get("type", "")),
                "severity": str(violation.get("severity", "")),
                "description": str(violation.get("description", "")),
                "items": items,
            })
    return findings


def _classify_finding(finding: dict[str, Any]) -> tuple[str, str, str]:
    finding_type = str(finding.get("type", ""))
    severity = str(finding.get("severity", ""))
    text = _finding_text(finding)
    pin_types = _pin_types(text)
    refs = _symbol_refs(text)

    if _looks_like_generated_symbol_pin_noise(finding_type, pin_types, refs):
        return (
            BUCKET_LIBRARY_NOISE,
            "Generated or imported symbol pin types look too generic for ERC.",
            "Normalize symbol pin types before treating this as a circuit error.",
        )

    if finding_type == "pin_not_driven" and _all_refs_look_passive(refs):
        return (
            BUCKET_LIBRARY_NOISE,
            "Passive-style component pin is marked as input, which is usually a library metadata issue.",
            "Normalize passive component pins to passive.",
        )

    if severity == "error":
        return (
            BUCKET_MUST_FIX,
            "KiCad reported an ERC error that does not match a known library-noise pattern.",
            "Inspect the model net membership and generated schematic.",
        )

    return (
        BUCKET_REVIEW_REQUIRED,
        "KiCad reported a warning that needs domain review.",
        "Review the connected pins and decide whether to fix the model or normalize the symbol.",
    )


def _finding_text(finding: dict[str, Any]) -> str:
    parts = [str(finding.get("description", ""))]
    parts.extend(str(item) for item in finding.get("items", []))
    return " ".join(parts)


def _pin_types(text: str) -> set[str]:
    pin_types: set[str] = set()
    for bracket in _PIN_TYPE_PATTERN.findall(text):
        parts = [part.strip() for part in bracket.split(",")]
        for part in parts:
            if part in {"Input", "Output", "Bidirectional", "Passive", "Unspecified", "Power input", "Power output"}:
                pin_types.add(part)
    return pin_types


def _symbol_refs(text: str) -> list[str]:
    return [match.group(1) for match in _SYMBOL_REF_PATTERN.finditer(text)]


def _looks_like_generated_symbol_pin_noise(finding_type: str, pin_types: set[str], refs: list[str]) -> bool:
    if finding_type != "pin_to_pin":
        return False
    if "Unspecified" in pin_types:
        return True
    if "Input" in pin_types and any(_is_passive_ref(ref) for ref in refs):
        return True
    return False


def _all_refs_look_passive(refs: list[str]) -> bool:
    return bool(refs) and all(_is_passive_ref(ref) for ref in refs)


def _is_passive_ref(ref: str) -> bool:
    return ref.startswith(PASSIVE_REFS)

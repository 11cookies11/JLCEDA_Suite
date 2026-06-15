"""Heuristics for checking whether a source model expresses enough design intent."""

from __future__ import annotations

import json
from typing import Any


BASELINE_SECTIONS = ("design_decisions", "risks", "constraints")

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "power": (
        "power",
        "charger",
        "regulator",
        "battery",
        "lipo",
        "usb-c",
        "usb",
        "3v3",
        "vin",
        "vout",
    ),
    "mcu": (
        "mcu",
        "controller",
        "esp32",
        "stm32",
        "rp2040",
        "gd32",
        "bare soc",
    ),
    "rf": (
        "rf",
        "antenna",
        "wifi",
        "lna",
        "match",
        "u.fl",
        "ipex",
    ),
    "audio": (
        "audio",
        "mic",
        "microphone",
        "record",
        "vad",
    ),
    "storage": (
        "storage",
        "flash",
        "sd",
        "microsd",
        "psram",
        "nand",
        "emmc",
    ),
    "ui": (
        "button",
        "switch",
        "led",
        "vibration",
        "motor",
        "mark",
        "mute",
    ),
    "security": (
        "security",
        "secure",
        "encrypt",
        "privacy",
        "key",
        "identity",
    ),
    "debug": (
        "debug",
        "boot",
        "reset",
        "uart",
        "jtag",
        "swd",
        "test",
    ),
}

PLACEHOLDER_HINTS = (
    "placeholder",
    "tbd",
    "to be confirmed",
    "tentative",
    "verify later",
    "verify",
    "unknown",
)


def check_design_intent(model: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    """Check whether a circuit model captures enough design intent."""
    if not isinstance(model, dict):
        return {
            "attempted": True,
            "success": False,
            "status": "error",
            "issues": [{"severity": "error", "code": "MODEL_TYPE", "message": "model must be an object"}],
            "active_domains": [],
            "baseline_counts": {},
        }

    components = _list_items(model.get("components", []))
    decisions = _list_items(model.get("design_decisions", []))
    risks = _list_items(model.get("risks", []))
    constraints = _list_items(model.get("constraints", []))

    baseline_counts = {
        "design_decisions": len(decisions),
        "risks": len(risks),
        "constraints": len(constraints),
    }

    if not components:
        return {
            "attempted": True,
            "success": True,
            "status": "info",
            "issues": [],
            "active_domains": [],
            "baseline_counts": baseline_counts,
            "missing_baseline_sections": [],
            "domain_coverage": [],
        }

    issues: list[dict[str, Any]] = []
    missing_baseline_sections: list[str] = []

    for section in BASELINE_SECTIONS:
        if baseline_counts.get(section, 0) == 0:
            missing_baseline_sections.append(section)
            issues.append(_issue(
                strict=strict,
                code=f"MISSING_{section.upper()}",
                message=f"design intent section '{section}' is empty",
                suggestion=_baseline_suggestion(section),
            ))

    active_domains = _detect_active_domains(model)
    domain_coverage = _domain_coverage(active_domains, decisions, risks, constraints)
    for item in domain_coverage:
        if item["evidence_count"] > 0:
            continue
        issues.append(_issue(
            strict=strict,
            code=f"MISSING_{str(item['domain']).upper()}_INTENT",
            message=f"no design intent evidence found for active domain '{item['domain']}'",
            suggestion=_domain_suggestion(str(item["domain"])),
        ))

    placeholder_hits = _collect_placeholder_hits(model)
    if placeholder_hits:
        issues.append({
            "severity": "warning",
            "code": "PLACEHOLDER_SIGNAL",
            "message": "model still contains placeholder or tentative intent markers",
            "details": placeholder_hits,
            "suggestion": "Convert placeholder markers into explicit decisions, risks, or constraints before release.",
        })

    worst = "info"
    for issue in issues:
        severity = str(issue.get("severity", "warning"))
        if severity == "error":
            worst = "error"
            break
        if severity == "warning" and worst != "error":
            worst = "warning"

    return {
        "attempted": True,
        "success": not any(issue.get("severity") == "error" for issue in issues),
        "status": worst,
        "issues": issues,
        "active_domains": active_domains,
        "baseline_counts": baseline_counts,
        "missing_baseline_sections": missing_baseline_sections,
        "domain_coverage": domain_coverage,
        "placeholder_hits": placeholder_hits,
    }


def _list_items(items: Any) -> list[Any]:
    if not isinstance(items, list):
        return []
    return [item for item in items if item not in (None, "")]


def _text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _model_corpus(model: dict[str, Any], *, include_intent_sections: bool = False) -> str:
    parts: list[str] = []
    for component in _list_items(model.get("components", [])):
        if isinstance(component, dict):
            for key in ("ref", "role", "value", "package", "sheet"):
                parts.append(_text_blob(component.get(key, "")))
            parts.extend(_string_list(component.get("notes", [])))
            parts.extend(_string_list(component.get("search_hints", [])))
            pinmap = component.get("pinmap", {})
            if isinstance(pinmap, dict):
                parts.append(_text_blob(pinmap))
        else:
            parts.append(_text_blob(component))
    for net in _list_items(model.get("nets", [])):
        if isinstance(net, dict):
            parts.append(_text_blob(net.get("name", "")))
            parts.append(_text_blob(net.get("kind", "")))
        else:
            parts.append(_text_blob(net))
    for sheet in _list_items(model.get("sheets", [])):
        if isinstance(sheet, dict):
            parts.append(_text_blob(sheet.get("name", "")))
            parts.extend(_string_list(sheet.get("notes", [])))
        else:
            parts.append(_text_blob(sheet))
    if include_intent_sections:
        for key in BASELINE_SECTIONS:
            for item in _list_items(model.get(key, [])):
                parts.append(_text_blob(item))
    return " ".join(part.lower() for part in parts if part)


def _string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif item is not None:
            result.append(str(item))
    return result


def _detect_active_domains(model: dict[str, Any]) -> list[str]:
    corpus = _model_corpus(model, include_intent_sections=False)
    active: list[str] = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in corpus for keyword in keywords):
            active.append(domain)
    return active


def _domain_coverage(
    domains: list[str],
    decisions: list[Any],
    risks: list[Any],
    constraints: list[Any],
) -> list[dict[str, Any]]:
    evidence_texts = {
        "design_decisions": [_text_blob(item) for item in decisions],
        "risks": [_text_blob(item) for item in risks],
        "constraints": [_text_blob(item) for item in constraints],
    }
    coverage: list[dict[str, Any]] = []
    for domain in domains:
        keywords = DOMAIN_KEYWORDS[domain]
        matched_items: list[dict[str, str]] = []
        for section, items in evidence_texts.items():
            for index, text in enumerate(items):
                if any(keyword in text.lower() for keyword in keywords):
                    matched_items.append({"section": section, "index": str(index)})
        coverage.append({
            "domain": domain,
            "evidence_count": len(matched_items),
            "evidence": matched_items,
        })
    return coverage


def _collect_placeholder_hits(model: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    texts = [
        _model_corpus(model, include_intent_sections=False),
        _model_corpus(model, include_intent_sections=True),
    ]
    for text in texts:
        for hint in PLACEHOLDER_HINTS:
            if hint in text and hint not in hits:
                hits.append(hint)
    return hits


def _issue(
    *,
    strict: bool,
    code: str,
    message: str,
    suggestion: str,
) -> dict[str, Any]:
    return {
        "severity": "error" if strict else "warning",
        "code": code,
        "message": message,
        "suggestion": suggestion,
    }


def _baseline_suggestion(section: str) -> str:
    return {
        "design_decisions": "Record the main architecture and tradeoffs that define this revision.",
        "risks": "List the risks you already know about so later automation does not guess.",
        "constraints": "Capture hard constraints such as size, power, RF, safety, or privacy limits.",
    }.get(section, "Add the missing design intent section.")


def _domain_suggestion(domain: str) -> str:
    return {
        "power": "Add power-tree decisions, battery/charger risks, and power constraints.",
        "mcu": "Record the MCU choice, boot strategy, and any pin-closure constraints.",
        "rf": "Record antenna, matching, keepout, and RF layout decisions.",
        "audio": "Record microphone topology, placement, and voice-triggering constraints.",
        "storage": "Record storage medium, retention, and data-extraction decisions.",
        "ui": "Record user-input and feedback behavior decisions.",
        "security": "Record privacy, encryption, or secure-element decisions.",
        "debug": "Record bring-up and debug access decisions.",
    }.get(domain, "Add explicit decisions, risks, or constraints for this domain.")

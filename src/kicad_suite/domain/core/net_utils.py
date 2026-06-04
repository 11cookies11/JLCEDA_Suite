"""Shared netlist helpers."""

from __future__ import annotations


def normalize_net_kind(name: str) -> str:
    """Classify a net name into a KiCad-friendly net kind."""
    normalized = str(name).strip().upper()
    if normalized in {"GND", "AGND", "DGND", "PGND", "SGND"}:
        return "ground"
    if normalized.startswith("+") or any(
        token in normalized for token in ("VCC", "VDD", "VIN", "VOUT", "VBAT", "PWR")
    ):
        return "power"
    return "signal"

"""Application service for classifying ERC outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .erc_classifier import classify_erc_file, classify_erc_report


class ErcClassificationService:
    """Convert raw KiCad ERC reports into agent-actionable buckets."""

    def classify_file(self, path: str | Path) -> dict[str, Any]:
        return classify_erc_file(Path(path))

    def classify_report(self, report: dict[str, Any]) -> dict[str, Any]:
        return classify_erc_report(report)

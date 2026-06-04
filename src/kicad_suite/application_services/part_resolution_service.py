"""Application service for resolving selected parts and local libraries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.jlc_installer import resolve_missing_symbols


class PartResolutionService:
    """Resolve model components into project-local JLC symbols and footprints."""

    def resolve_symbols(
        self,
        project_path: str | Path,
        model: dict[str, Any],
        *,
        timeout: int = 120,
        delay: float = 0.8,
        model_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return resolve_missing_symbols(
            Path(project_path),
            model,
            timeout=timeout,
            delay=delay,
            model_path=Path(model_path) if model_path is not None else None,
        )

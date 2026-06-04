#!/usr/bin/env python3
"""Post-processing helpers for KiCad pipeline output."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def pin_project_libraries(project_dir: Path) -> dict[str, Any]:
    """Ensure KiCad's project JSON pins the project-local JLC libraries.

    Resolves both output-level and project-level ``libraries/`` directories
    and writes absolute-pathed ``sym-lib-table`` and ``fp-lib-table`` files
    so KiCad CLI and GUI can find JLC-MCP symbols and footprints.
    """
    from ..application_services.footprint_resolution_service import FootprintResolutionService

    return FootprintResolutionService().pin_project_libraries(project_dir)


def _inject_symbols_into_sheet(sch_path: Path, lib_name: str, lib_content: str) -> int:
    """Replace 2-pin stubs in one schematic file.  Returns number of replacements."""
    from ..application_services.symbol_normalization_service import _inject_symbols_into_sheet as inject_sheet

    return inject_sheet(sch_path, lib_name, lib_content)


def inject_jlc_symbols(schematic_path: Path) -> bool:
    """Replace JLC-MCP 2-pin stubs with full symbol definitions from library files.

    Processes the root schematic AND all hierarchical sub-sheets.
    """
    from ..application_services.symbol_normalization_service import SymbolNormalizationService

    return SymbolNormalizationService().inject_jlc_symbols(schematic_path)


def register_jlc_libraries(project_dir: Path) -> dict[str, Any]:
    """Register JLC-MCP libraries after schematic generation."""
    from ..application_services.footprint_resolution_service import FootprintResolutionService

    return FootprintResolutionService().register_jlc_libraries(project_dir)


def sync_cached_symbol_libraries(schematic_file: Path, project_dir: Path) -> dict[str, Any]:
    """Mirror generated schematic cache symbols into project-local libraries.

    KiCad ERC reports lib_symbol_mismatch when the schematic cache has been
    intentionally normalized (for example passive connector pins) but the
    referenced source library still has the original imported symbol.  For
    generated projects the cache is the source of truth, so keep the local
    symbol libraries aligned with it.
    """
    from ..application_services.symbol_normalization_service import SymbolNormalizationService

    return SymbolNormalizationService().sync_cached_symbol_libraries(schematic_file, project_dir)


def sync_source_libraries(project_dir: Path) -> dict[str, Any]:
    """Copy pre-imported EasyEDA/JLC assets from the source project into output."""
    from ..application_services.footprint_resolution_service import FootprintResolutionService

    return FootprintResolutionService().sync_source_libraries(project_dir)


def sanitize_copied_symbol_libraries(project_dir: Path) -> dict[str, Any]:
    """Remove invalid converter artifacts from project-local symbol libraries."""
    from ..application_services.symbol_normalization_service import SymbolNormalizationService

    return SymbolNormalizationService().sanitize_copied_symbol_libraries(project_dir)


def sanitize_footprint_libraries(project_dir: Path) -> dict[str, Any]:
    """Normalize copied footprint files so KiCad GUI can enumerate the library."""
    from ..application_services.footprint_resolution_service import FootprintResolutionService

    return FootprintResolutionService().sanitize_footprint_libraries(project_dir)


def upgrade_footprint_libraries(project_dir: Path) -> dict[str, Any]:
    """Best-effort KiCad CLI footprint library upgrade for copied local libs."""
    from ..application_services.footprint_resolution_service import FootprintResolutionService

    return FootprintResolutionService().upgrade_footprint_libraries(project_dir)


def validate_gui_assets(project_dir: Path) -> dict[str, Any]:
    """Check the assets KiCad GUI needs for update-PCB and 3D viewer workflows."""
    from ..application_services.footprint_resolution_service import FootprintResolutionService

    return FootprintResolutionService().validate_gui_assets(project_dir)


def patch_known_jlc_symbol_pin_types(project_dir: Path) -> dict[str, Any]:
    """Apply narrow ERC pin-type corrections for known EasyEDA/JLC symbol issues."""
    from ..application_services.symbol_normalization_service import SymbolNormalizationService

    return SymbolNormalizationService().patch_known_jlc_symbol_pin_types(project_dir)


def sanitize_generated_schematics(project_dir: Path) -> dict[str, Any]:
    """Final pass to keep generated schematic lib_symbols parseable by KiCad."""
    from ..application_services.symbol_normalization_service import SymbolNormalizationService

    return SymbolNormalizationService().sanitize_generated_schematics(project_dir)


def apply_postprocess(schematic_file: Path, project_dir: Path) -> dict[str, Any]:
    """Run post-processing after KiCad file generation."""
    from ..application_services.footprint_resolution_service import FootprintResolutionService
    from ..application_services.symbol_normalization_service import SymbolNormalizationService

    footprint_result = FootprintResolutionService().prepare_project_footprints(project_dir)
    symbol_result = SymbolNormalizationService().normalize_project_symbols(project_dir, schematic_file)
    return {**footprint_result, **symbol_result}

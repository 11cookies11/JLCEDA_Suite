"""Tests for application-service boundaries."""

from __future__ import annotations

from unittest.mock import patch

from kicad_suite.application_services.erc_classification_service import ErcClassificationService
from kicad_suite.application_services.footprint_resolution_service import FootprintResolutionService
from kicad_suite.application_services.part_resolution_service import PartResolutionService
from kicad_suite.application_services.symbol_normalization_service import SymbolNormalizationService
from kicad_suite.orchestration.pipeline_postprocess import apply_postprocess


def test_erc_classification_service_delegates_to_classifier() -> None:
    report = {
        "sheets": [
            {
                "path": "/",
                "violations": [
                    {
                        "type": "pin_to_pin",
                        "severity": "warning",
                        "description": "generic pin warning",
                        "items": [{"description": "Symbol U1 pin 1 [VDD, Unspecified, Line]"}],
                    }
                ],
            }
        ]
    }

    result = ErcClassificationService().classify_report(report)

    assert result["counts"]["library_noise"] == 1


def test_part_resolution_service_delegates_to_installer(tmp_path) -> None:
    with patch("kicad_suite.application_services.part_resolution_service.resolve_missing_symbols") as resolver:
        resolver.return_value = {"ok": True, "resolved": 0, "failed": 0}
        result = PartResolutionService().resolve_symbols(tmp_path, {}, timeout=1, delay=0)

    assert result["ok"] is True
    resolver.assert_called_once()


def test_postprocess_uses_named_services(tmp_path) -> None:
    schematic = tmp_path / "demo.kicad_sch"
    schematic.write_text("(kicad_sch)\n", encoding="utf-8")

    with patch.object(FootprintResolutionService, "prepare_project_footprints") as footprints:
        with patch.object(SymbolNormalizationService, "normalize_project_symbols") as symbols:
            footprints.return_value = {"footprint_step": {"ok": True}}
            symbols.return_value = {"symbol_step": {"ok": True}}

            result = apply_postprocess(schematic, tmp_path)

    assert result == {"footprint_step": {"ok": True}, "symbol_step": {"ok": True}}
    footprints.assert_called_once_with(tmp_path)
    symbols.assert_called_once_with(tmp_path, schematic)

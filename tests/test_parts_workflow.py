"""Tests for the parts workflow package."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.lcsc_resolver import PartRequirement, ResolvedPart, ResolverResult
from kicad_suite.part_selector import SelectedPart, SelectionResult, classify_package_risk, select_parts
from kicad_suite.parts.report import build_parts_summary
from kicad_suite.parts.resolve import (
    build_mock_resolver_results,
    build_part_requirements,
    enrich_selected_parts_with_refs,
)
from kicad_suite.parts.workflow import run_parts_pipeline


def _make_component(**overrides: object) -> dict[str, object]:
    component: dict[str, object] = {
        "role": "ldo",
        "ref": "U1",
        "value": "3.3V LDO",
        "selected_part": {
            "part_id": "P1",
            "lcsc_id": "C2040",
            "mpn": "AMS1117-3.3",
            "display_name": "AMS1117-3.3",
            "package": "SOT-223",
            "library_uuid": "lib-1",
            "place_uuid": "fp-1",
        },
    }
    component.update(overrides)
    return component


class TestPartsResolveHelpers(unittest.TestCase):
    def test_build_part_requirements_uses_role_and_selected_part(self):
        requirements = build_part_requirements([_make_component()])
        self.assertEqual(len(requirements), 1)
        req = requirements[0]
        self.assertEqual(req.id, "ldo")
        self.assertEqual(req.function, "3.3V LDO")
        self.assertEqual(req.preferred_mpn, ["AMS1117-3.3"])
        self.assertEqual(req.package_preferred, ["SOT-223"])

    def test_build_part_requirements_falls_back_to_ref(self):
        requirements = build_part_requirements([
            {"ref": "R1", "value": "10k", "selected_part": {}},
            "ignore-me",
        ])
        self.assertEqual(len(requirements), 1)
        self.assertEqual(requirements[0].id, "R1")
        self.assertEqual(requirements[0].function, "10k")

    def test_mock_resolver_results_uses_selected_part_data(self):
        requirements = [PartRequirement(id="ldo", function="3.3V LDO")]
        results = build_mock_resolver_results(requirements, [_make_component()])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "ldo")
        self.assertEqual(len(results[0].candidates), 1)
        self.assertEqual(results[0].candidates[0].lcsc_id, "C2040")

    def test_enrich_selected_parts_with_refs(self):
        candidate = ResolvedPart(
            lcsc_id="C2040",
            mpn="AMS1117-3.3",
            manufacturer="AMS",
            package="SOT-223",
            description="3.3V LDO",
            stock=1000,
            basic_or_extended="Basic",
            has_easyeda_symbol=True,
            has_easyeda_footprint=True,
            has_3d_model=False,
            source="jlcpcb_parts",
            confidence=0.9,
        )
        selection = select_parts([PartRequirement(id="ldo", function="3.3V LDO")], [ResolverResult(id="ldo", candidates=[candidate])])
        enriched = enrich_selected_parts_with_refs(selection, [_make_component(ref="U7", value="REG")])
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].ref, "U7")
        self.assertEqual(enriched[0].value, "REG")

    def test_part_risk_summary(self):
        parts = [
            SelectedPart(
                requirement_id="r1",
                lcsc_id="C1",
                mpn="R-1",
                manufacturer="YAGEO",
                package="0603",
                description="Resistor",
                price=0.01,
                stock=1000,
                basic_or_extended="Basic",
                has_easyeda_symbol=True,
                has_easyeda_footprint=True,
                has_3d_model=False,
                source="jlcpcb_parts",
                confidence=0.8,
                composite_score=10.0,
                reasons=[],
                risks=[],
                needs_review=False,
            ),
            SelectedPart(
                requirement_id="r2",
                lcsc_id="C2",
                mpn="MOD",
                manufacturer="MOD",
                package="USB-C 16P",
                description="Connector",
                price=1.0,
                stock=5,
                basic_or_extended="Extended",
                has_easyeda_symbol=False,
                has_easyeda_footprint=False,
                has_3d_model=False,
                source="easyeda_community",
                confidence=0.5,
                composite_score=20.0,
                reasons=[],
                risks=[],
                needs_review=True,
            ),
        ]
        summary = build_parts_summary(2, parts)
        self.assertEqual(summary["total_components"], 2)
        self.assertEqual(summary["resolved_parts"], 2)
        self.assertEqual(summary["low_risk"], 1)
        self.assertEqual(summary["high_risk"], 1)
        self.assertEqual(summary["needs_review"], 1)


class TestRunPartsPipeline(unittest.TestCase):
    def test_no_components_returns_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_parts_pipeline({"components": []}, tmpdir)
            self.assertEqual(result["lock_file"], "")
            self.assertEqual(result["risk_report_file"], "")
            self.assertIn("warning", result)

    def test_pipeline_generates_outputs_without_live_backend(self):
        model = {"components": [_make_component()]}
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("kicad_suite.parts.workflow.describe_live_backend_status", return_value={"ok": False}):
                result = run_parts_pipeline(model, tmpdir, project_name="demo")
            self.assertTrue(result["lock_file"])
            self.assertTrue(result["risk_report_file"])
            self.assertEqual(result["summary"]["resolved_parts"], 1)
            self.assertEqual(result["summary"]["low_risk"], 1)
            self.assertTrue(result["warnings"])
            self.assertTrue(Path(result["lock_file"]).exists())
            self.assertTrue(Path(result["risk_report_file"]).exists())

    def test_pipeline_can_run_importer_path(self):
        model = {"components": [_make_component()]}

        class DummyImportResult:
            imported_count = 1
            skipped_count = 0
            failed_lcsc_ids: list[str] = []
            symbol_lib_file = "symbols.kicad_sym"
            footprint_lib_dir = "footprints.pretty"
            model_dir = "models"
            lock_file = "lock.yaml"
            risk_report_file = "risk.md"
            errors: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("kicad_suite.parts.workflow.describe_live_backend_status", return_value={"ok": False}):
                with patch("kicad_suite.parts.workflow.import_parts", return_value=DummyImportResult()):
                    result = run_parts_pipeline(model, tmpdir, project_name="demo", run_importer=True)
            self.assertEqual(result["import_result"]["imported_count"], 1)
            self.assertEqual(result["lock_file"], "lock.yaml")
            self.assertEqual(result["risk_report_file"], "risk.md")


if __name__ == "__main__":
    unittest.main()

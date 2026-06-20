"""Tests for the project-level resolution manifest."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.domain.core.part_selector import SelectedPart
from kicad_suite.orchestration.project_resolution import _clean_part, build_project_resolution


class TestProjectResolution(unittest.TestCase):
    def test_clean_part_preserves_symbol_reference(self) -> None:
        cleaned = _clean_part({
            "display_name": "ESP32-S3-WROOM-1-N8R8",
            "symbol_ref": "ESP32-S3-WROOM-1",
            "kicad_footprint_hint": "WIRELM-SMD_ESP32-S3-WROOM-1",
        })

        self.assertEqual(cleaned["symbol_ref"], "ESP32-S3-WROOM-1")

    def test_build_project_resolution_merges_parts_pipeline_selection(self) -> None:
        model = {
            "schema_version": "circuit-model.v1",
            "request_id": "req-1",
            "project_id": "proj-1",
            "topology": "demo",
            "components": [
                {
                    "ref": "U1",
                    "role": "mcu",
                    "value": "STM32F103C8T6",
                    "selected_part": {
                        "part_id": "part-u1",
                        "display_name": "STM32F103C8T6",
                        "package": "LQFP-48",
                    },
                    "candidate_parts": [],
                    "availability_status": "unknown",
                }
            ],
            "nets": [],
        }
        parts_result = {
            "selections": [
                SelectedPart(
                    requirement_id="mcu",
                    lcsc_id="C12345",
                    mpn="STM32F103C8T6",
                    manufacturer="STMicroelectronics",
                    package="LQFP-48",
                    description="STM32F103C8T6",
                    price=None,
                    stock=1000,
                    basic_or_extended="Basic",
                    has_easyeda_symbol=True,
                    has_easyeda_footprint=True,
                    has_3d_model=False,
                    source="jlcpcb_parts",
                    confidence=0.95,
                    composite_score=88.0,
                    reasons=["test"],
                    risks=[],
                    needs_review=False,
                    ref="U1",
                    value="STM32F103C8T6",
                )
            ],
            "summary": {"resolved_parts": 1},
            "warnings": [],
            "requirements": [
                {
                    "id": "mcu",
                    "function": "STM32F103C8T6",
                    "preferred_mpn": ["STM32F103C8T6"],
                    "package_preferred": ["LQFP-48"],
                }
            ],
            "resolver_results": [
                {
                    "id": "mcu",
                    "candidates": [
                        {
                            "lcsc_id": "C12345",
                            "mpn": "STM32F103C8T6",
                            "manufacturer": "STMicroelectronics",
                            "package": "LQFP-48",
                        }
                    ],
                }
            ],
        }

        with patch("kicad_suite.orchestration.project_resolution.footprint_exists", return_value=True):
            with patch(
                "kicad_suite.orchestration.project_resolution.symbol_mapping_for",
                return_value=("MCU:STM32F103C8T6", "LQFP-48", []),
            ):
                manifest = build_project_resolution(model, parts_result=parts_result)

        self.assertEqual(manifest["summary"]["component_count"], 1)
        self.assertEqual(manifest["summary"]["search_queue_count"], 1)
        self.assertEqual(manifest["summary"]["resolver_request_count"], 1)
        self.assertEqual(manifest["summary"]["verified_count"], 1)
        self.assertEqual(manifest["summary"]["needs_reselection_count"], 0)
        self.assertEqual(manifest["search_queue"][0]["ref"], "U1")
        self.assertEqual(manifest["resolver_requests"][0]["component_ref"], "U1")
        self.assertEqual(manifest["components"][0]["selected_part"]["lcsc_id"], "C12345")
        self.assertEqual(manifest["components"][0]["verification"]["status"], "verified")
        self.assertEqual(manifest["components"][0]["verification"]["candidate_count"], 1)
        self.assertEqual(manifest["components"][0]["verification"]["best_candidate"]["lcsc_id"], "C12345")
        self.assertTrue(manifest["components"][0]["verification"]["reselect_suggestions"])
        self.assertEqual(manifest["components"][0]["resolution_result"]["candidate_count"], 1)
        self.assertTrue(manifest["components"][0]["resolution_result"]["recommended_candidates"])
        self.assertEqual(manifest["parts_pipeline"]["selection_count"], 1)
        self.assertEqual(manifest["parts_pipeline"]["selected_parts"][0]["lcsc_id"], "C12345")

    def test_build_project_resolution_ranks_candidates_for_reselection(self) -> None:
        model = {
            "schema_version": "circuit-model.v1",
            "request_id": "req-2",
            "project_id": "proj-2",
            "topology": "demo",
            "components": [
                {
                    "ref": "U1",
                    "role": "mcu",
                    "value": "STM32F103C8T6",
                    "selected_part": {
                        "part_id": "wrong-part",
                        "display_name": "Wrong Part",
                        "lcsc_id": "C00000",
                        "mpn": "BROKEN",
                        "package": "SOT-23",
                    },
                    "candidate_parts": [],
                    "availability_status": "unknown",
                }
            ],
            "nets": [],
        }
        parts_result = {
            "selections": [],
            "summary": {"resolved_parts": 0},
            "warnings": [],
            "resolver_results": [
                {
                    "id": "mcu",
                    "candidates": [
                        {
                            "part_id": "candidate-b",
                            "display_name": "Candidate B",
                            "lcsc_id": "C20000",
                            "mpn": "STM32F103C8T6TR",
                            "package": "LQFP-48",
                            "confidence": 0.95,
                        },
                        {
                            "part_id": "candidate-a",
                            "display_name": "Candidate A",
                            "lcsc_id": "C10000",
                            "mpn": "STM32F103C8T6",
                            "package": "LQFP-48",
                            "composite_score": 93.0,
                            "confidence": 0.40,
                        },
                    ],
                }
            ],
        }

        with patch("kicad_suite.orchestration.project_resolution.footprint_exists", return_value=False):
            with patch(
                "kicad_suite.orchestration.project_resolution.symbol_mapping_for",
                return_value=("JLC-MCP:STM32F103C8T6", "LQFP-48", []),
            ):
                manifest = build_project_resolution(model, parts_result=parts_result)

        self.assertEqual(manifest["components"][0]["resolution_result"]["recommended_candidates"][0]["part_id"], "candidate-a")
        self.assertEqual(manifest["components"][0]["verification"]["best_candidate"]["part_id"], "candidate-a")
        self.assertEqual(manifest["components"][0]["verification"]["status"], "reselect_required")
        self.assertTrue(manifest["components"][0]["verification"]["reselect_suggestions"])

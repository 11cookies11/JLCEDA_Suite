"""Tests for JLC installer resolution flow."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.jlc_installer import (
    _qualify_symbol_footprint_references,
    resolve_missing_symbols,
)


class TestResolveMissingSymbols(unittest.TestCase):
    def test_local_symbol_footprint_is_qualified_for_portable_projects(self) -> None:
        content = '''(symbol "R"
  (property
    "Footprint"
    ":R0603"
  )
)'''

        normalized = _qualify_symbol_footprint_references(content, "JLC-MCP")

        self.assertIn('"JLC-MCP:R0603"', normalized)
        self.assertNotIn('":R0603"', normalized)

    def test_selected_part_lcsc_id_skips_search_path(self) -> None:
        model = {
            "components": [
                {
                    "ref": "U1",
                    "role": "mcu",
                    "value": "ESP32-C3FH4",
                    "selected_part": {
                        "lcsc_id": "C2858491",
                        "display_name": "ESP32-C3FH4",
                    },
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("{}", encoding="utf-8")

            install_result = {
                "ok": True,
                "lcsc_id": "C2858491",
                "title": "ESP32-C3FH4",
                "package": "QFN-32",
                "symbol_ref": "ESP32-C3FH4",
                "pin_count": 32,
            }

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id", return_value=install_result) as install_mock:
                with patch("kicad_suite.adapters.jlc_installer.jlc_api.search") as search_mock:
                    result = resolve_missing_symbols(project_path, model, timeout=5, model_path=model_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["failed"], 0)
        install_mock.assert_called_once_with(
            "C2858491",
            project_path,
            retries=2,
            delay=30.0,
            initial_delay_range=(3.0, 8.0),
        )
        search_mock.assert_not_called()
        self.assertEqual(model["components"][0]["selected_part"]["symbol_ref"], "ESP32-C3FH4")
        self.assertEqual(model["components"][0]["selected_part"]["kicad_footprint_hint"], "QFN-32")

    def test_explicit_footprint_hint_is_preserved_over_library_default(self) -> None:
        model = {
            "components": [
                {
                    "ref": "U9",
                    "role": "load_switch",
                    "value": "TPS22918 MIC_3V3 load switch",
                    "selected_part": {
                        "lcsc_id": "C131941",
                        "display_name": "TPS22918DBVR",
                        "kicad_footprint_hint": "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
                    },
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("{}", encoding="utf-8")

            install_result = {
                "ok": True,
                "lcsc_id": "C131941",
                "title": "TPS22918DBVR",
                "package": "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR",
                "symbol_ref": "TPS22918DBVR",
                "pin_count": 6,
            }

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id", return_value=install_result):
                result = resolve_missing_symbols(project_path, model, timeout=5, model_path=model_path)

        self.assertTrue(result["ok"])
        self.assertEqual(model["components"][0]["selected_part"]["kicad_footprint_hint"], "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL")
        self.assertEqual(model["components"][0]["selected_part"]["symbol_ref"], "TPS22918DBVR")

    def test_component_without_lcsc_id_needs_selection(self) -> None:
        model = {
            "components": [
                {
                    "ref": "R1",
                    "role": "resistor",
                    "value": "10k",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("{}", encoding="utf-8")

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id") as install_mock:
                with patch("kicad_suite.adapters.jlc_installer.jlc_api.search") as search_mock:
                    result = resolve_missing_symbols(project_path, model, timeout=5, model_path=model_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["needs_selection"], 1)
        self.assertEqual(result["details"][0]["reason"], "missing_selected_part_lcsc_id")
        install_mock.assert_not_called()
        search_mock.assert_not_called()

    def test_duplicate_selected_lcsc_ids_install_once_per_run(self) -> None:
        model = {
            "components": [
                {
                    "ref": "R1",
                    "role": "resistor",
                    "value": "10k",
                    "selected_part": {"lcsc_id": "C15401", "display_name": "0603WAJ0103T5E"},
                },
                {
                    "ref": "R2",
                    "role": "resistor",
                    "value": "10k",
                    "selected_part": {"lcsc_id": "C15401", "display_name": "0603WAJ0103T5E"},
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("{}", encoding="utf-8")

            install_result = {
                "ok": True,
                "lcsc_id": "C15401",
                "title": "0603WAJ0103T5E",
                "package": "R0603",
                "symbol_ref": "0603WAJ0103T5E",
                "pin_count": 2,
            }

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id", return_value=install_result) as install_mock:
                result = resolve_missing_symbols(project_path, model, timeout=5, model_path=model_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolved"], 2)
        install_mock.assert_called_once()
        self.assertEqual(model["components"][0]["selected_part"]["symbol_ref"], "0603WAJ0103T5E")
        self.assertEqual(model["components"][1]["selected_part"]["symbol_ref"], "0603WAJ0103T5E")

    def test_explicit_non_lcsc_component_is_skipped(self) -> None:
        model = {
            "components": [
                {
                    "ref": "TP1",
                    "role": "test_point",
                    "value": "TP",
                    "part_source": "internal",
                    "bom_exclude": True,
                    "selected_part": {"part_id": "tp-1p", "kicad_footprint_hint": "TP-SMD_1P"},
                },
                {
                    "ref": "J1",
                    "role": "usb_c_connector",
                    "value": "USB-C",
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("{}", encoding="utf-8")

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id") as install_mock:
                with patch("kicad_suite.adapters.jlc_installer.jlc_api.search") as search_mock:
                    result = resolve_missing_symbols(project_path, model, timeout=5, model_path=model_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["needs_selection"], 1)
        self.assertEqual(result["details"][0]["ref"], "TP1")
        self.assertEqual(result["details"][0]["reason"], "bom_exclude")
        self.assertEqual(result["details"][1]["ref"], "J1")
        self.assertEqual(result["details"][1]["reason"], "missing_selected_part_lcsc_id")
        install_mock.assert_not_called()
        search_mock.assert_not_called()

    def test_dnp_text_without_explicit_assembly_still_needs_selection(self) -> None:
        model = {
            "components": [
                {
                    "ref": "C1",
                    "role": "rf_shunt_tune",
                    "value": "DNP",
                    "package": "C0402",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("{}", encoding="utf-8")

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id") as install_mock:
                with patch("kicad_suite.adapters.jlc_installer.jlc_api.search") as search_mock:
                    result = resolve_missing_symbols(project_path, model, timeout=5, model_path=model_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["needs_selection"], 1)
        self.assertEqual(result["details"][0]["reason"], "missing_selected_part_lcsc_id")
        install_mock.assert_not_called()
        search_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

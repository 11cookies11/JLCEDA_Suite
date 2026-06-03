"""Tests for JLC installer resolution flow."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.jlc_installer import resolve_missing_symbols


class TestResolveMissingSymbols(unittest.TestCase):
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

            with patch("kicad_suite.jlc_installer.install_by_lcsc_id", return_value=install_result) as install_mock:
                with patch("kicad_suite.jlc_installer.jlc_api.search") as search_mock:
                    result = resolve_missing_symbols(project_path, model, timeout=5, delay=0, model_path=model_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["failed"], 0)
        install_mock.assert_called_once_with("C2858491", project_path)
        search_mock.assert_not_called()
        self.assertEqual(model["components"][0]["selected_part"]["symbol_ref"], "ESP32-C3FH4")
        self.assertEqual(model["components"][0]["selected_part"]["kicad_footprint_hint"], "QFN-32")


if __name__ == "__main__":
    unittest.main()

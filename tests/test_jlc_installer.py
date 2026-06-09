"""Tests for JLC installer resolution flow."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters import jlc_api, jlc_installer
from kicad_suite.adapters.jlc_installer import resolve_missing_symbols


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

            with patch("kicad_suite.adapters.jlc_installer.install_by_lcsc_id", return_value=install_result) as install_mock:
                with patch("kicad_suite.adapters.jlc_installer.jlc_api.search") as search_mock:
                    result = resolve_missing_symbols(project_path, model, timeout=5, delay=0, model_path=model_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["failed"], 0)
        install_mock.assert_called_once_with("C2858491", project_path)
        search_mock.assert_not_called()
        self.assertEqual(model["components"][0]["selected_part"]["symbol_ref"], "ESP32-C3FH4")
        self.assertEqual(model["components"][0]["selected_part"]["kicad_footprint_hint"], "QFN-32")

    def test_cached_install_does_not_touch_api_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            cache_key = f"{project_path.resolve()}:C1234"
            previous_cache = dict(jlc_installer._installed_lcsc_cache)
            previous_empty_streak = jlc_api._empty_streak
            try:
                jlc_installer._installed_lcsc_cache[cache_key] = "QFN-32"
                jlc_api._empty_streak = 7

                with patch("kicad_suite.adapters.jlc_installer.jlc_api.get_component") as get_component_mock:
                    result = jlc_installer.install_by_lcsc_id("C1234", project_path)

                self.assertTrue(result["ok"])
                self.assertTrue(result["cached"])
                self.assertEqual(result["package"], "QFN-32")
                get_component_mock.assert_not_called()
                self.assertEqual(jlc_api._empty_streak, 7)
            finally:
                jlc_installer._installed_lcsc_cache.clear()
                jlc_installer._installed_lcsc_cache.update(previous_cache)
                jlc_api._empty_streak = previous_empty_streak

    def test_escalated_get_component_uses_three_failed_attempts(self) -> None:
        previous_empty_streak = jlc_api._empty_streak
        previous_last_call_time = jlc_api._last_call_time
        try:
            jlc_api._empty_streak = 3
            api = Mock()
            api.get_cad_data_of_component.return_value = {}

            with patch("kicad_suite.adapters.jlc_api._get_api", return_value=api):
                with patch("kicad_suite.adapters.jlc_api._rate_limit"):
                    with patch("kicad_suite.adapters.jlc_api._time.sleep"):
                        result = jlc_api.get_component("C9999", retries=5, delay=0)

            self.assertIsNone(result)
            self.assertEqual(api.get_cad_data_of_component.call_count, 3)
        finally:
            jlc_api._empty_streak = previous_empty_streak
            jlc_api._last_call_time = previous_last_call_time


if __name__ == "__main__":
    unittest.main()

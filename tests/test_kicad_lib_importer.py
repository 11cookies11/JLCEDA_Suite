"""Tests for KiCad Library Importer module."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.kicad_lib_importer import (
    ImportResult,
    _yaml_dumps,
    _yaml_value,
    _build_lock_data,
    _build_risk_report,
    _parse_lock_file,
    import_parts,
)
from kicad_suite.part_selector import SelectedPart


def _make_selected(**overrides: object) -> SelectedPart:
    defaults: dict[str, object] = dict(
        requirement_id="power_ldo",
        lcsc_id="C2040",
        mpn="AMS1117-3.3",
        manufacturer="AMS",
        package="SOT-223",
        description="3.3V LDO, 1A",
        price=0.12,
        stock=5000,
        basic_or_extended="Basic",
        has_easyeda_symbol=True,
        has_easyeda_footprint=True,
        has_3d_model=True,
        source="jlcpcb_parts",
        confidence=0.85,
        composite_score=85.0,
        reasons=["MPN exact match: AMS1117-3.3", "Package exact match: SOT-223", "JLCPCB Basic Part"],
        risks=[],
        needs_review=False,
        value="3.3V 1A",
        note="",
    )
    defaults.update(overrides)
    return SelectedPart(**defaults)  # type: ignore[arg-type]


class TestYamlValue(unittest.TestCase):
    """YAML scalar serialisation."""

    def test_none(self):
        self.assertEqual(_yaml_value(None), "null")

    def test_bool_true(self):
        self.assertEqual(_yaml_value(True), "true")

    def test_bool_false(self):
        self.assertEqual(_yaml_value(False), "false")

    def test_int(self):
        self.assertEqual(_yaml_value(42), "42")

    def test_float_whole(self):
        self.assertEqual(_yaml_value(3.0), "3")

    def test_float_fractional(self):
        self.assertEqual(_yaml_value(3.14), "3.14")

    def test_simple_string(self):
        self.assertEqual(_yaml_value("hello"), "hello")

    def test_string_with_colon(self):
        result = _yaml_value("hello: world")
        self.assertIn('"', result)
        self.assertIn("hello: world", result)

    def test_empty_string(self):
        self.assertEqual(_yaml_value(""), '""')


class TestYamlDumps(unittest.TestCase):
    """YAML structure serialisation."""

    def test_simple_dict(self):
        result = _yaml_dumps({"name": "test", "value": 42})
        self.assertIn("name: test", result)
        self.assertIn("value: 42", result)

    def test_nested_dict(self):
        result = _yaml_dumps({"outer": {"inner": "val"}})
        self.assertIn("outer:", result)
        self.assertIn("inner: val", result)

    def test_list_of_dicts(self):
        result = _yaml_dumps({"parts": [{"id": "1"}, {"id": "2"}]})
        self.assertIn("id: 1", result)
        self.assertIn("id: 2", result)

    def test_empty_dict(self):
        result = _yaml_dumps({"empty": {}})
        self.assertIn("empty:", result)

    def test_empty_list(self):
        result = _yaml_dumps({"empty": []})
        self.assertIn("empty: []", result)


class TestLockData(unittest.TestCase):
    """Lock file builder tests."""

    def test_build_lock_data_structure(self):
        p1 = _make_selected(lcsc_id="C1001", mpn="LDO-1")
        p2 = _make_selected(lcsc_id="C1002", mpn="CAP-1", needs_review=True)
        data = _build_lock_data([p1, p2], [], {}, project_name="test-project")
        self.assertEqual(data["schema_version"], "part-lock.v1")
        self.assertEqual(data["project"], "test-project")
        self.assertIn("generated_at", data)
        self.assertEqual(len(data["parts"]), 2)
        statuses = [p["status"] for p in data["parts"]]  # type: ignore[union-attr]
        self.assertIn("locked", statuses)
        self.assertIn("review", statuses)
        # Check rich fields exist
        for part in data["parts"]:  # type: ignore[union-attr]
            self.assertIn("ref", part)
            self.assertIn("role", part)
            self.assertIn("risk", part)
            self.assertIn("kicad_symbol", part)
            self.assertIn("kicad_footprint", part)

    def test_build_lock_data_skips_duplicates(self):
        p1 = _make_selected(lcsc_id="C1001", mpn="LDO-1")
        data = _build_lock_data([p1], [], {"C1001": {"lcsc_id": "C1001", "mpn": "OLD"}})
        self.assertEqual(len(data["parts"]), 1)

    def test_build_lock_data_combines_imported_and_skipped(self):
        p1 = _make_selected(lcsc_id="C1001", mpn="LDO-1")
        p2 = _make_selected(lcsc_id="", mpn="NO-ID")
        data = _build_lock_data([p1], [p2], {})
        self.assertEqual(len(data["parts"]), 1)  # empty lcsc_id skipped


class TestRiskReport(unittest.TestCase):
    """Risk report generation tests."""

    def test_risk_report_contains_part_info(self):
        p1 = _make_selected()
        report = _build_risk_report([p1])
        self.assertIn("EasyEDA Import Risk Report", report)
        self.assertIn("AMS1117-3.3", report)
        self.assertIn("C2040", report)

    def test_risk_report_has_risk_sections(self):
        p1 = _make_selected(package="0603")
        p2 = _make_selected(requirement_id="mod1", lcsc_id="C9999", mpn="ESP32MOD", package="SMD Module")
        p3 = _make_selected(requirement_id="usb1", lcsc_id="C7777", mpn="USB-C", package="USB-C 16P")
        report = _build_risk_report([p1, p2, p3])
        self.assertIn("Low Risk", report)
        self.assertIn("Medium Risk", report)
        self.assertIn("High Risk", report)

    def test_risk_report_high_risk_usb(self):
        p1 = _make_selected(requirement_id="usb1", lcsc_id="C8888", mpn="USB-C-16P", package="USB-C 16P")
        report = _build_risk_report([p1])
        self.assertIn("High Risk", report)

    def test_risk_report_summary_counts(self):
        p1 = _make_selected(package="0603")
        p2 = _make_selected(requirement_id="other", lcsc_id="C9999", mpn="OTHER", package="0603")
        report = _build_risk_report([p1, p2])
        self.assertIn("Total Parts", report)
        self.assertIn("Low Risk", report)


class TestLockFileParser(unittest.TestCase):
    """Lock file parsing tests."""

    def test_parse_written_lock_file(self):
        p1 = _make_selected(lcsc_id="C1001", mpn="TEST-1")
        data = _build_lock_data([p1], [], {})
        yaml_content = _yaml_dumps(data) + "\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "part.lock.yaml"
            lock_path.write_text(yaml_content, encoding="utf-8")
            parsed = _parse_lock_file(lock_path)
            self.assertIn("C1001", parsed)
            self.assertEqual(parsed["C1001"]["mpn"], "TEST-1")

    def test_parse_missing_file(self):
        parsed = _parse_lock_file(Path("/nonexistent/path.yaml"))
        self.assertEqual(parsed, {})

    def test_parse_multiple_parts(self):
        p1 = _make_selected(lcsc_id="C1001", mpn="TEST-1")
        p2 = _make_selected(lcsc_id="C1002", mpn="TEST-2", requirement_id="req2")
        data = _build_lock_data([p1, p2], [], {})
        yaml_content = _yaml_dumps(data) + "\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "part.lock.yaml"
            lock_path.write_text(yaml_content, encoding="utf-8")
            parsed = _parse_lock_file(lock_path)
            self.assertIn("C1001", parsed)
            self.assertIn("C1002", parsed)


class TestImportParts(unittest.TestCase):
    """Import parts integration tests."""

    def test_import_parts_no_tool(self):
        """When easyeda2kicad is not found, returns error gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = import_parts(
                [_make_selected()],
                tmpdir,
                easyeda2kicad_bin="/nonexistent/path/easyeda2kicad",
            )
            self.assertEqual(result.imported_count, 0)
            self.assertTrue(len(result.errors) > 0 or len(result.failed_lcsc_ids) > 0)

    def test_import_parts_empty_selections(self):
        """Empty selections produce clean result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = import_parts([], tmpdir)
            self.assertEqual(result.imported_count, 0)
            self.assertEqual(result.skipped_count, 0)

    def test_import_parts_creates_expected_dirs(self):
        """Even when import fails, library directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = import_parts(
                [_make_selected()],
                tmpdir,
                easyeda2kicad_bin="/nonexistent/path/tool",
            )
            self.assertTrue(Path(result.footprint_lib_dir).exists())
            self.assertTrue(Path(result.model_dir).exists())

    def test_import_parts_creates_report(self):
        """Risk report and lock file are written even on failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = import_parts(
                [_make_selected()],
                tmpdir,
                easyeda2kicad_bin="/nonexistent/path/tool",
            )
            output = Path(tmpdir)
            # Report and lock file paths are set even if import failed
            self.assertTrue(result.risk_report_file)
            self.assertTrue(result.lock_file)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_artifacts as va  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class ValidateArtifactsTests(unittest.TestCase):
    def test_valid_summary_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            (project_dir / "project.kicad_pro").write_text("{}", encoding="utf-8")
            (project_dir / "project.kicad_sch").write_text("{}", encoding="utf-8")
            _write_json(
                project_dir / "kicad-erc.summary.json",
                {
                    "schema_version": "kicad-erc-result.v1",
                    "enabled": True,
                    "attempted": True,
                    "success": True,
                    "finding_count": 0,
                    "summary_file": str(project_dir / "kicad-erc.summary.json"),
                    "output_file": str(project_dir / "kicad-erc.json"),
                },
            )
            _write_json(project_dir / "kicad-erc.json", {"findings": []})
            plan = {
                "schema_version": "kicad-execution-plan.v1",
                "symbols": [
                    {"ref": "U1", "pins": [{"number": "1", "net": "VCC"}, {"number": "2", "net": "GND"}]},
                    {"ref": "R1", "pins": [{"number": "1", "net": "NET_A"}, {"number": "2", "net": "NET_B"}]},
                ],
                "nets": [{"name": "VCC"}, {"name": "GND"}, {"name": "NET_A"}, {"name": "NET_B"}],
                "diagnostics": {"warnings": [], "unsupported": []},
            }
            _write_json(project_dir / "kicad-execution-plan.json", plan)
            summary = {
                "schema_version": "kicad-project-write-result.v1",
                "files": {
                    "project": "project/project.kicad_pro",
                    "schematic": "project/project.kicad_sch",
                    "execution_plan": "project/kicad-execution-plan.json",
                    "kicad_erc_summary": "project/kicad-erc.summary.json",
                    "kicad_erc_report": "project/kicad-erc.json",
                },
                "counts": {"symbols": 2, "nets": 4},
                "erc": {
                    "schema_version": "kicad-erc-result.v1",
                    "enabled": True,
                    "attempted": True,
                    "success": True,
                    "finding_count": 0,
                    "summary_file": "project/kicad-erc.summary.json",
                    "output_file": "project/kicad-erc.json",
                },
            }
            summary_path = root / "run-summary.json"
            _write_json(summary_path, summary)

            report = va.validate_artifacts(summary_path)

            self.assertTrue(report.ok)
            self.assertFalse(report.errors)
            self.assertTrue(report.stats.get("erc_enabled"))
            self.assertTrue(report.stats.get("erc_success"))

    def test_detects_stale_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            (project_dir / "project.kicad_pro").write_text("D:/GitRepository/AI/JLCEDA_Suite", encoding="utf-8")
            summary = {
                "files": {"project": "project/project.kicad_pro"},
            }
            summary_path = root / "summary.json"
            _write_json(summary_path, summary)

            report = va.validate_artifacts(summary_path)

            self.assertFalse(report.ok)
            self.assertTrue(any("stale path" in item for item in report.errors))

    def test_detects_count_mismatch_and_pin_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            _write_json(project_dir / "project.kicad_pro", {})
            _write_json(project_dir / "project.kicad_sch", {})
            plan = {
                "schema_version": "kicad-execution-plan.v1",
                "symbols": [
                    {"ref": "U1", "pins": [{"number": "1", "net": "A"}, {"number": "1", "net": "B"}]},
                ],
                "nets": [{"name": "A"}],
                "diagnostics": {"warnings": [], "unsupported": []},
            }
            _write_json(project_dir / "kicad-execution-plan.json", plan)
            summary = {
                "files": {
                    "project": "project/project.kicad_pro",
                    "schematic": "project/project.kicad_sch",
                    "execution_plan": "project/kicad-execution-plan.json",
                },
                "counts": {"symbols": 2, "nets": 3},
            }
            summary_path = root / "summary.json"
            _write_json(summary_path, summary)

            report = va.validate_artifacts(summary_path)

            self.assertFalse(report.ok)
            self.assertTrue(any("symbol count mismatch" in item for item in report.errors))
            self.assertTrue(any("net count mismatch" in item for item in report.errors))
            self.assertEqual(report.stats.get("shared_node_labels"), 1)
            self.assertTrue(any("shared-node labels" in item for item in report.checks))

    def test_detects_failed_erc_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            _write_json(project_dir / "project.kicad_pro", {})
            _write_json(project_dir / "project.kicad_sch", {})
            _write_json(
                project_dir / "kicad-erc.summary.json",
                {
                    "schema_version": "kicad-erc-result.v1",
                    "enabled": True,
                    "attempted": True,
                    "success": False,
                    "return_code": 1,
                    "finding_count": 3,
                    "summary_file": str(project_dir / "kicad-erc.summary.json"),
                    "output_file": str(project_dir / "kicad-erc.json"),
                },
            )
            _write_json(project_dir / "kicad-erc.json", {"findings": [{"kind": "error"}]})
            plan = {
                "schema_version": "kicad-execution-plan.v1",
                "symbols": [],
                "nets": [],
                "diagnostics": {"warnings": [], "unsupported": []},
            }
            _write_json(project_dir / "kicad-execution-plan.json", plan)
            summary = {
                "files": {
                    "project": "project/project.kicad_pro",
                    "schematic": "project/project.kicad_sch",
                    "execution_plan": "project/kicad-execution-plan.json",
                    "kicad_erc_summary": "project/kicad-erc.summary.json",
                    "kicad_erc_report": "project/kicad-erc.json",
                },
                "counts": {"symbols": 0, "nets": 0},
                "erc": {
                    "schema_version": "kicad-erc-result.v1",
                    "enabled": True,
                    "attempted": True,
                    "success": False,
                    "return_code": 1,
                    "finding_count": 3,
                    "summary_file": "project/kicad-erc.summary.json",
                    "output_file": "project/kicad-erc.json",
                },
            }
            summary_path = root / "summary.json"
            _write_json(summary_path, summary)

            report = va.validate_artifacts(summary_path)

            self.assertFalse(report.ok)
            self.assertTrue(any("ERC failed" in item for item in report.errors))

    def test_strict_mode_fails_on_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = {}
            summary_path = root / "summary.json"
            _write_json(summary_path, summary)

            report = va.validate_artifacts(summary_path, strict=True)

            self.assertFalse(report.ok)
            self.assertTrue(any("strict mode" in item for item in report.errors))


if __name__ == "__main__":
    unittest.main()

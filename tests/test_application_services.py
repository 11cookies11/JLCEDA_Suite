"""Tests for application-service boundaries."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.application_services.erc_classification_service import ErcClassificationService
from kicad_suite.application_services.footprint_resolution_service import FootprintResolutionService
from kicad_suite.application_services.design_intent_service import check_design_intent
from kicad_suite.application_services.placement_planner import build_placement_plan, write_placement_plan
from kicad_suite.application_services.part_resolution_service import PartResolutionService
from kicad_suite.application_services.symbol_normalization_service import (
    SymbolNormalizationService,
    _qualify_library_footprint_references,
)
from kicad_suite.cli import main as cli_main
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
        result = PartResolutionService().resolve_symbols(tmp_path, {}, timeout=1)

    assert result["ok"] is True
    resolver.assert_called_once_with(tmp_path, {}, timeout=1, model_path=None)


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


def test_symbol_normalization_qualifies_library_local_footprints() -> None:
    symbol_library = '''(kicad_symbol_lib
  (symbol "R"
    (property
      "Footprint"
      ":R0603"
    )
  )
)'''

    normalized = _qualify_library_footprint_references(symbol_library, "JLC-MCP")

    assert '"JLC-MCP:R0603"' in normalized
    assert '":R0603"' not in normalized


def test_footprint_resolution_service_normalizes_3d_model_paths(tmp_path) -> None:
    project = tmp_path
    fp_dir = project / "libraries" / "footprints" / "JLC-MCP.pretty"
    model_dir = project / "libraries" / "3dmodels" / "JLC-MCP.3dshapes"
    fp_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)

    model_file = model_dir / "demo-model.wrl"
    model_file.write_text("dummy", encoding="utf-8")

    footprint = fp_dir / "C0402.kicad_mod"
    footprint.write_text(
        """
(footprint "C0402"
  (model "/demo-model.wrl"
    (offset (xyz 0 0 0))
    (scale (xyz 1 1 1))
    (rotate (xyz 0 0 0))
  )
)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    pcb = project / "demo.kicad_pcb"
    pcb.write_text(
        """
(kicad_pcb
  (footprint "C0402"
    (model "/demo-model.wrl"
      (offset (xyz 0 0 0))
      (scale (xyz 1 1 1))
      (rotate (xyz 0 0 0))
    )
  )
)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    fp_table = project / "fp-lib-table"
    fp_table.write_text(
        """
(fp_lib_table
  (version 7)
  (lib (name "JLC-MCP")(type "KiCad")(uri "libraries/footprints/JLC-MCP.pretty")(options "")(descr ""))
)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = FootprintResolutionService().normalize_3d_model_paths(project)

    expected = "${KIPRJMOD}/libraries/3dmodels/JLC-MCP.3dshapes/demo-model.wrl"
    assert result["success"] is True
    assert result["updated_references"] == 2
    assert expected in footprint.read_text(encoding="utf-8")
    assert expected in pcb.read_text(encoding="utf-8")

    validation = FootprintResolutionService().validate_gui_assets(project, normalize=False)
    assert validation["success"] is True
    assert validation["missing_models"] == []
    assert validation["non_project_model_refs"] == []
    assert isinstance(validation["search_roots"], list)


def test_footprint_resolution_service_uses_configured_3d_model_roots(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    footprints_dir = project / "libraries" / "footprints" / "Demo.pretty"
    footprints_dir.mkdir(parents=True)
    fp_table = project / "fp-lib-table"
    fp_table.write_text(
        """
(fp_lib_table
  (version 7)
  (lib (name "Demo")(type "KiCad")(uri "libraries/footprints/Demo.pretty")(options "")(descr ""))
)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    pcb = project / "demo.kicad_pcb"
    pcb.write_text(
        """
(kicad_pcb
  (footprint "Demo"
    (model "/external-model.wrl"
      (offset (xyz 0 0 0))
      (scale (xyz 1 1 1))
      (rotate (xyz 0 0 0))
    )
  )
)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    external_root = tmp_path / "shared-3d"
    external_root.mkdir()
    (external_root / "external-model.wrl").write_text("dummy", encoding="utf-8")
    monkeypatch.setenv("KICAD_AGENT_3DMODEL_DIRS", str(external_root))

    result = FootprintResolutionService().normalize_3d_model_paths(project)

    expected = "${KIPRJMOD}/libraries/3dmodels/external-model.wrl"
    assert result["success"] is True
    assert expected in pcb.read_text(encoding="utf-8")
    assert (project / "libraries" / "3dmodels" / "external-model.wrl").exists()
    assert str(external_root) in result["search_roots"]


def test_design_intent_service_flags_incomplete_intent(tmp_path) -> None:
    model = {
        "schema_version": "circuit-model.v1",
        "request_id": "demo",
        "project_id": "demo",
        "topology": "demo_topology",
        "components": [
            {"ref": "U1", "role": "main_controller_bare_soc", "value": "ESP32-S3"},
            {"ref": "U2", "role": "single_cell_lipo_charger", "value": "MCP73831"},
        ],
        "nets": [],
        "sheets": [],
        "design_decisions": [],
        "risks": [],
        "constraints": [],
    }

    result = check_design_intent(model, strict=False)

    assert result["success"] is True
    assert result["status"] == "warning"
    assert "design_decisions" in result["missing_baseline_sections"]
    assert any(item["domain"] == "power" for item in result["domain_coverage"])
    assert any(item["domain"] == "mcu" for item in result["domain_coverage"])


def test_agent_assets_validate_command_reports_success(tmp_path, capsys) -> None:
    project = tmp_path
    fp_dir = project / "libraries" / "footprints" / "JLC-MCP.pretty"
    fp_dir.mkdir(parents=True)
    model_dir = project / "libraries" / "3dmodels" / "JLC-MCP.3dshapes"
    model_dir.mkdir(parents=True)

    (model_dir / "demo-model.wrl").write_text("dummy", encoding="utf-8")
    (fp_dir / "Demo.kicad_mod").write_text(
        """
(footprint "Demo"
  (model "${KIPRJMOD}/libraries/3dmodels/JLC-MCP.3dshapes/demo-model.wrl"
    (offset (xyz 0 0 0))
    (scale (xyz 1 1 1))
    (rotate (xyz 0 0 0))
  )
)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (project / "fp-lib-table").write_text(
        """
(fp_lib_table
  (version 7)
  (lib (name "JLC-MCP")(type "KiCad")(uri "libraries/footprints/JLC-MCP.pretty")(options "")(descr ""))
  (lib (name "Demo")(type "KiCad")(uri "libraries/footprints/Demo.pretty")(options "")(descr ""))
)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    code = cli_main(["agent", "assets", "validate", "--project", str(project)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["stage"] == "assets_validate"
    assert payload["result"]["success"] is True


def test_sanitize_generated_schematics_normalizes_passive_symbol_pins(tmp_path) -> None:
    schematic = tmp_path / "demo.kicad_sch"
    schematic.write_text(
        """
(kicad_sch
  (lib_symbols
    (symbol "JLC-MCP:R0603"
      (property "Reference" "R1" (at 0 0 0))
      (property "Value" "10k" (at 0 0 0))
      (symbol "R0603_0_1"
        (pin input line
          (at 0 0 0)
          (length 2.54)
          (name "1")
          (number "1")
        )
      )
    )
  )
)
""".strip(),
        encoding="utf-8",
    )

    result = SymbolNormalizationService().sanitize_generated_schematics(tmp_path)

    assert result["count"] == 1
    patched = schematic.read_text(encoding="utf-8")
    assert "(pin passive line" in patched
    assert "(pin input line" not in patched


def test_placement_planner_builds_plan_for_regions(tmp_path) -> None:
    model = {
        "project_id": "demo-board",
        "topology": "demo_topology",
        "components": [
            {"ref": "U1", "role": "mcu", "value": "MCU"},
            {"ref": "C1", "role": "decoupling", "value": "100nF"},
            {"ref": "J1", "role": "connector", "value": "USB-C"},
        ],
        "constraints": [
            {"name": "board_size", "type": "pcb", "scope": "global", "rules": ["max_width: 80mm", "max_height: 60mm"]},
        ],
        "pcb_layout": {
            "regions": {
                "mcu": {"x": 10, "y": 12, "components": ["U1", "C1"]},
                "edge": {"x": 50, "y": 10, "components": ["J1"]},
            }
        },
    }

    plan = build_placement_plan(model)
    assert plan["schema_version"] == "placement-plan.v1"
    assert plan["summary"]["region_count"] == 2
    assert plan["summary"]["placed_count"] == 3
    assert plan["board"]["width_mm"] == 80
    assert plan["board"]["height_mm"] == 60

    result = write_placement_plan(tmp_path, model)
    assert (tmp_path / "build" / "placement-plan.json").exists()
    assert (tmp_path / "build" / "placement-plan.md").exists()
    assert result["plan"]["summary"]["placed_count"] == 3

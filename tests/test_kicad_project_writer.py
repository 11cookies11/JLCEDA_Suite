from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.kicad_project_writer import (
    _sheet_file_stem,
    automatic_power_flags_for_net_names,
    render_connectivity,
    render_child_schematic,
    render_project,
    render_root_schematic,
    render_symbol_instance,
    symbol_block_with_default_footprint,
    write_project,
)
from kicad_suite.adapters.kicad_project_writer import _remove_stale_child_schematics
from kicad_suite.orchestration.pipeline_postprocess import pin_project_libraries
from kicad_suite.adapters.board_generator import (
    _load_source_model,
    _source_netlist_symbol_pins,
    generate_board_from_plan,
)
from kicad_suite.adapters.kicad_symbol_library import parse_symbol_pin_map
from kicad_suite.domain.core.netlist_builder import build_netlist
from kicad_suite.domain.core.ir_to_kicad import ir_to_kicad
from kicad_suite.domain.core.kicad_layout_engine import configured_schematic_position, configured_topology_position
from kicad_suite.domain.core.kicad_layout_engine import apply_sheet_aware_schematic_layout
from kicad_suite.adapters.pcb_generator import (
    _BOARD_SCRIPT,
    _convert_pad_block,
    _extract_pad_blocks,
    _validate_generated_board_nets,
    generate_pcb,
)


class TestKicadProjectWriter(unittest.TestCase):
    def test_render_project_includes_default_erc_settings(self) -> None:
        project = json.loads(render_project())

        erc = project["erc"]
        self.assertEqual(erc["meta"]["version"], 0)
        self.assertEqual(len(erc["pin_map"]), 12)
        self.assertEqual(erc["rule_severities"]["unconnected_wire_endpoint"], "ignore")
        self.assertEqual(erc["rule_severities"]["lib_symbol_issues"], "warning")
        self.assertEqual(erc["rule_severities"]["single_global_label"], "ignore")

    def test_sheet_file_stem_strips_duplicate_numeric_prefix(self) -> None:
        self.assertEqual(_sheet_file_stem(1, "01_usb_and_charging"), "01_usb_and_charging")
        self.assertEqual(_sheet_file_stem(2, "02_02_system_power"), "02_system_power")
        self.assertEqual(_sheet_file_stem(3, "audio_front_end"), "03_audio_front_end")

    def test_remove_stale_child_schematics_keeps_expected_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            keep = ["root.kicad_sch", "01_usb_and_charging.kicad_sch"]
            (directory / "root.kicad_sch").write_text("root", encoding="utf-8")
            (directory / "01_usb_and_charging.kicad_sch").write_text("new", encoding="utf-8")
            (directory / "01_01_usb_and_charging.kicad_sch").write_text("old", encoding="utf-8")
            (directory / "unrelated.txt").write_text("x", encoding="utf-8")

            _remove_stale_child_schematics(directory, keep)

            self.assertTrue((directory / "root.kicad_sch").exists())
            self.assertTrue((directory / "01_usb_and_charging.kicad_sch").exists())
            self.assertFalse((directory / "01_01_usb_and_charging.kicad_sch").exists())
            self.assertTrue((directory / "unrelated.txt").exists())

    def test_write_project_always_emits_one_standard_schematic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            output_dir = project_dir / "output" / "demo"
            project_dir.mkdir(parents=True)
            # A former EasyEDA-only marker must not alter the standard export.
            (project_dir / ".kicad-flat-schematic").write_text("obsolete", encoding="utf-8")
            plan = {
                "request_id": "demo",
                "target": {
                    "project_name": "demo",
                    "output_dir": str(output_dir),
                    "schematic_file": str(output_dir / "demo.kicad_sch"),
                    "project_file": str(output_dir / "demo.kicad_pro"),
                },
                "sheets": [{"name": "power", "components": ["R1"]}],
                "symbols": [{
                    "ref": "R1",
                    "lib_id": "Device:R",
                    "value": "10K",
                    "footprint": "JLC-MCP:R0603",
                    "at": {"x": 10.0, "y": 10.0, "rotation": 0.0},
                    "pins": [],
                }],
                "nets": [],
            }

            result = write_project(plan, project_path=project_dir)
            schematic = output_dir / "demo.kicad_sch"
            self.assertTrue(result["single_page"])
            self.assertEqual(result["section_count"], 1)
            self.assertTrue(schematic.exists())
            self.assertEqual([path.name for path in output_dir.glob("*.kicad_sch")], ["demo.kicad_sch"])
            self.assertIn("JLC-MCP:R0603", schematic.read_text(encoding="utf-8"))

    def test_default_footprint_replaces_multiline_library_property(self) -> None:
        block = '''(symbol "JLC-MCP:Example"
  (property
    "Footprint"
    ":R0603"
  )
)'''

        rendered = symbol_block_with_default_footprint(block, "JLC-MCP:R0603")

        self.assertIn('"JLC-MCP:R0603"', rendered)
        self.assertNotIn('":R0603"', rendered)

    def test_automatic_power_flags_are_not_bom_or_pcb_parts(self) -> None:
        flags = automatic_power_flags_for_net_names({"GND"}, {"GND": "ground"})
        rendered = render_symbol_instance(flags[0], "demo")

        self.assertIn("(in_bom no)", rendered)
        self.assertIn("(on_board no)", rendered)

    def test_footprint_property_is_preserved_for_kicad_importers(self) -> None:
        rendered = render_symbol_instance(
            {
                "ref": "R1",
                "lib_id": "Device:R",
                "value": "10K",
                "footprint": "JLC-MCP:R0603",
                "at": {"x": 10.0, "y": 10.0, "rotation": 0.0},
                "pins": [],
            },
            "demo",
        )

        footprint_start = rendered.index('(property "Footprint"')
        footprint_block = rendered[footprint_start:footprint_start + 220]
        self.assertNotIn("(hide yes)", footprint_block)
        self.assertIn("(size 0.01 0.01)", footprint_block)

    def test_hierarchical_render_includes_sheet_ports_and_child_ports(self) -> None:
        plan = {
            "target": {"project_name": "demo"},
            "nets": [
                {"name": "SYS_3V3", "kind": "power", "members": ["U1.1", "U2.1"]},
            ],
            "symbols": [],
        }
        page = {
            "name": "power",
            "file": "01_power.kicad_sch",
            "path": "/sheet-uuid",
            "uuid": "sheet-uuid",
            "x": 25.4,
            "y": 25.4,
            "w": 48.26,
            "h": 30.48,
            "ports": ["SYS_3V3", "UNPOPULATED_PORT"],
            "pins": ["SYS_3V3", "UNPOPULATED_PORT"],
            "symbols": [
                {
                    "ref": "U1",
                    "lib_id": "power:PWR_FLAG",
                    "value": "PWR_FLAG",
                    "at": {"x": 50.8, "y": 50.8, "rotation": 0.0},
                    "pins": [{"number": "1", "net": "SYS_3V3"}],
                }
            ],
        }

        root = render_root_schematic(plan, [page])
        child = render_child_schematic(plan, page, page["symbols"], [page], {"SYS_3V3"})

        self.assertIn('(pin "SYS_3V3"', root)
        self.assertIn('(hierarchical_label "SYS_3V3"', child)
        self.assertGreaterEqual(child.count('(hierarchical_label "SYS_3V3"'), 1)
        self.assertIn('(hierarchical_label "UNPOPULATED_PORT"', child)
        self.assertNotIn('(global_label "SYS_3V3"', child)

    def test_render_connectivity_keeps_collided_horizontal_labels_orthogonal(self) -> None:
        plan = {
            "nets": [
                {"name": "NET_A", "kind": "signal"},
                {"name": "NET_B", "kind": "signal"},
            ],
        }
        symbols = [
            {
                "ref": "U1",
                "lib_id": "power:PWR_FLAG",
                "value": "PWR_FLAG",
                "at": {"x": 50.8, "y": 50.8, "rotation": 0.0},
                "pins": [{"number": "1", "net": "NET_A"}],
            },
            {
                "ref": "U2",
                "lib_id": "power:PWR_FLAG",
                "value": "PWR_FLAG",
                "at": {"x": 50.8, "y": 50.8, "rotation": 0.0},
                "pins": [{"number": "1", "net": "NET_B"}],
            },
        ]

        schematic = render_connectivity(plan, symbols)

        self.assertIn('(label "NET_A"', schematic)
        self.assertIn('(label "NET_B"', schematic)
        self.assertNotIn('(xy 50.8 50.8) (xy 46.99 53.34)', schematic)

    def test_ai_memory_badge_profile_exposes_schematic_positions(self) -> None:
        pos = configured_topology_position("ai_memory_badge_v1", "U1")
        self.assertIsNotNone(pos)
        self.assertEqual((pos.x, pos.y, pos.rotation), (55.0, 35.0, 0.0))

        schematic_pos = configured_schematic_position("ai_memory_badge_v1", "TP14")
        self.assertIsNotNone(schematic_pos)
        self.assertEqual((schematic_pos.x, schematic_pos.y, schematic_pos.rotation), (101.6, 127.0, 0.0))

    def test_ai_memory_badge_sheet_layout_separates_symbol_lanes(self) -> None:
        def symbol(ref: str, role: str) -> SimpleNamespace:
            return SimpleNamespace(
                ref=ref,
                role=role,
                lib_id="",
                at=SimpleNamespace(x=0.0, y=0.0, rotation=0.0),
            )

        symbols = [
            symbol("J1", "usb_connector"),
            symbol("U1", "main_controller_wroom_module"),
            symbol("R1", "pullup_resistor"),
            symbol("TP1", "test_point"),
        ]
        applied = apply_sheet_aware_schematic_layout(
            symbols,
            {item.ref: "demo" for item in symbols},
            "ai_memory_badge_v1",
        )
        positions = {item.ref: (item.at.x, item.at.y) for item in symbols}

        self.assertTrue(applied)
        self.assertEqual(positions["J1"][0], 38.1)
        self.assertEqual(positions["U1"][0], 106.68)
        self.assertEqual(positions["R1"][0], 38.1)
        self.assertGreater(positions["TP1"][1], positions["R1"][1])

    def test_ai_memory_badge_overlap_resolution_uses_source_sheet_assignment(self) -> None:
        ir = {
            "topology": "ai_memory_badge_v1",
            "project_name": "demo",
            "components": [
                {
                    "ref": "Q1",
                    "role": "vibration_motor_driver",
                    "value": "switch",
                    "assigned_sheet": "08_user_interface",
                    "selected_part": {"symbol_ref": "power:PWR_FLAG"},
                },
                {
                    "ref": "R31",
                    "role": "rec_button_pullup",
                    "value": "10K",
                    "assigned_sheet": "08_user_interface",
                    "selected_part": {"symbol_ref": "power:PWR_FLAG"},
                },
            ],
            "nets": [],
        }
        with patch("kicad_suite.domain.core.ir_to_kicad._resolve_symbol_overlaps_for_group") as resolve:
            resolve.return_value = 0
            ir_to_kicad(ir)

        groups = [call.args[0] for call in resolve.call_args_list]
        self.assertTrue(any({symbol.ref for symbol in group} == {"Q1", "R31"} for group in groups))

    def test_pin_project_libraries_restores_default_erc_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            project_file = project_dir / "demo.kicad_pro"
            project_file.write_text(json.dumps({"libraries": {}}), encoding="utf-8")

            result = pin_project_libraries(project_dir)
            project = json.loads(project_file.read_text(encoding="utf-8"))

        self.assertTrue(result["success"])
        self.assertEqual(project["erc"]["rule_severities"]["unconnected_wire_endpoint"], "ignore")
        self.assertEqual(len(project["erc"]["pin_map"]), 12)

    def test_extract_pad_blocks_preserves_multiline_kicad_10_pads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fp_file = Path(tmpdir) / "demo.kicad_mod"
            fp_file.write_text(
                "\n".join(
                    [
                        '(footprint "demo"',
                        '  (pad "1" smd rect',
                        '    (at 0 0)',
                        '    (size 1 1)',
                        '    (layers "F.Cu" "F.Paste" "F.Mask")',
                        '  )',
                        ')',
                    ]
                ),
                encoding="utf-8",
            )

            blocks = _extract_pad_blocks(fp_file)
            converted = _convert_pad_block(blocks[0])

        self.assertEqual(len(blocks), 1)
        self.assertGreater(len(blocks[0]), 1)
        self.assertTrue(any("(uuid " in line for line in converted))
        self.assertTrue(any('(layers "F.Cu" "F.Paste" "F.Mask")' in line for line in converted))

    def test_generate_pcb_reports_missing_footprint_without_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            plan = {
                "target": {
                    "output_dir": str(output_dir),
                    "project_name": "demo",
                },
                "symbols": [
                    {
                        "ref": "U1",
                        "footprint": "LQFP-48",
                        "value": "MCU",
                        "at": {"x": 10.0, "y": 20.0, "rotation": 0.0},
                    }
                ],
                "nets": [],
            }

            with patch("kicad_suite.adapters.pcb_generator._kicad_python", return_value="fake-kicad-python"):
                with patch("kicad_suite.adapters.pcb_generator.subprocess.run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = json.dumps(
                        {
                            "board": str(output_dir / "demo.kicad_pcb"),
                            "footprints": 0,
                            "nets": 0,
                            "skipped": ["U1: no footprint"],
                        }
                    )
                    run.return_value.stderr = ""

                    result = generate_pcb(plan, project_path=tmpdir)

        self.assertTrue(result["ok"])
        self.assertEqual(result["component_count"], 1)
        self.assertEqual(result["placements"], [])
        self.assertTrue(any("U1: no footprint" in warning for warning in result["warnings"]))

    def test_generate_board_rejects_missing_pad_nets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "output" / "demo"
            project_dir.mkdir(parents=True, exist_ok=True)
            board_file = project_dir / "demo.kicad_pcb"
            plan_file = Path(tmpdir) / "plan.json"
            plan = {
                "target": {
                    "output_dir": str(project_dir),
                    "project_name": "demo",
                },
                "symbols": [
                    {
                        "ref": "U1",
                        "footprint": "JLC-MCP:QFN-56_L7.0-W7.0-P0.40-TL-EP4.0",
                        "value": "ESP32-S3",
                        "pins": [
                            {"number": "17", "net": "I2S_BCLK"},
                            {"number": "49", "net": "UART0_TX"},
                        ],
                    }
                ],
            }
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            board_file.write_text(
                """
(kicad_pcb
  (version 20260206)
  (generator "pcbnew")
  (footprint "JLC-MCP:QFN-56_L7.0-W7.0-P0.40-TL-EP4.0"
    (layer "F.Cu")
    (property "Reference" "U1" (at 0 0 0))
    (pad "17" smd rect
      (at 0 0)
      (size 1 1)
      (layers "F.Cu")
    )
    (pad "49" smd rect
      (at 1 0)
      (size 1 1)
      (layers "F.Cu")
      (net "UART0_TX")
    )
  )
)
""".strip(),
                encoding="utf-8",
            )

            def _run_side_effect(*args, **kwargs):
                class _Proc:
                    returncode = 0
                    stdout = json.dumps({"board": str(board_file), "footprints": 1, "nets": 1, "skipped": []})
                    stderr = ""

                return _Proc()

            with patch("kicad_suite.adapters.board_generator._resolve_kicad_python", return_value="fake-kicad-python"):
                with patch("kicad_suite.adapters.board_generator.subprocess.run", side_effect=_run_side_effect):
                    result = generate_board_from_plan(str(plan_file), project_dir, tmpdir)

        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertTrue(any("U1 pad 17" in warning for warning in result["warnings"]))
        self.assertTrue(result["verification_errors"])

    def test_generate_pcb_rejects_board_with_missing_pad_nets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            board_file = Path(tmpdir) / "demo.kicad_pcb"
            board_file.write_text(
                """
(kicad_pcb
  (version 20260206)
  (generator "pcbnew")
  (footprint "R0603"
    (layer "F.Cu")
    (property "Reference" "R3" (at 0 0 0))
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))
    (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu") (net "GND"))
  )
)
""".strip(),
                encoding="utf-8",
            )
            issues = _validate_generated_board_nets(
                {"symbols": [{"ref": "R3", "pins": [{"number": "1", "net": "CHG_PROG"}, {"number": "2", "net": "GND"}]}]},
                board_file,
            )

        self.assertEqual(len(issues), 1)
        self.assertIn("R3 pad 1 expected net CHG_PROG", issues[0])

    def test_source_netlist_symbol_pins_resolve_semantic_and_numeric_pins(self) -> None:
        project_dir = Path("examples/ai-memory-badge-v1")
        source_model = _load_source_model(project_dir)
        source_netlist = build_netlist(source_model)

        u1_lib_id = "JLC-MCP:ESP32-S3-WROOM-1"
        u6_lib_id = "JLC-MCP:USBLC6-2SC6"
        with patch.dict(
            os.environ,
            {
                "KICAD_SOURCE_PROJECT_DIR": str(project_dir),
                "KICAD_OUTPUT_DIR": str(project_dir / "output" / "ai_memory_badge_v1"),
            },
            clear=False,
        ):
            u1_pins = _source_netlist_symbol_pins(
                source_netlist,
                "U1",
                u1_lib_id,
                parse_symbol_pin_map(u1_lib_id),
            )
            u6_pins = _source_netlist_symbol_pins(
                source_netlist,
                "U6",
                u6_lib_id,
                parse_symbol_pin_map(u6_lib_id),
            )

        u1_pin_nets = {pin["number"]: pin["net"] for pin in u1_pins}
        self.assertEqual(u1_pin_nets["3"], "ESP_EN")
        self.assertEqual(u1_pin_nets["13"], "USB_D_N")
        self.assertEqual(u1_pin_nets["14"], "USB_D_P")
        self.assertEqual(u1_pin_nets["34"], "NFC_GPO")
        self.assertEqual([pin["number"] for pin in u6_pins], ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(u6_pins[1]["net"], "GND")

    def test_generate_pcb_preflights_semantic_pins_to_physical_pads(self) -> None:
        project_dir = Path("examples/ai-memory-badge-v1")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            plan = {
                "target": {
                    "output_dir": str(output_dir),
                    "project_name": "demo",
                },
                "symbols": [
                    {
                        "ref": "U1",
                        "lib_id": "JLC-MCP:ESP32-S3-WROOM-1",
                        "footprint": "JLC-MCP:WIRELM-SMD_ESP32-S3-WROOM-1",
                        "value": "ESP32-S3-WROOM-1-N8R8 module",
                        "pins": [{"number": "GPIO20", "net": "USB_D_P"}],
                    }
                ],
            }
            captured: dict[str, object] = {}

            def _run_side_effect(args, **kwargs):
                plan_file = Path(args[2])
                payload = json.loads(plan_file.read_text(encoding="utf-8"))
                captured["pins"] = payload["symbols"][0]["pins"]

                class _Proc:
                    returncode = 0
                    stdout = json.dumps({"board": str(output_dir / "demo.kicad_pcb"), "footprints": 1, "nets": 1})
                    stderr = ""

                return _Proc()

            with patch("kicad_suite.adapters.pcb_generator._kicad_python", return_value="fake-kicad-python"):
                with patch("kicad_suite.adapters.pcb_generator.subprocess.run", side_effect=_run_side_effect):
                    result = generate_pcb(plan, project_path=project_dir)

        self.assertTrue(result["ok"])
        pin_nets = {pin["number"]: pin["net"] for pin in captured["pins"] if pin.get("net")}
        self.assertEqual(pin_nets["3"], "ESP_EN")
        self.assertEqual(pin_nets["13"], "USB_D_N")
        self.assertEqual(pin_nets["14"], "USB_D_P")
        self.assertEqual(pin_nets["1"], "GND")

    def test_board_script_does_not_depend_on_repo_src_imports(self) -> None:
        self.assertNotIn("src.kicad_suite", _BOARD_SCRIPT)
        self.assertNotIn("from src ", _BOARD_SCRIPT)
        self.assertNotIn("from src.", _BOARD_SCRIPT)


if __name__ == "__main__":
    unittest.main()

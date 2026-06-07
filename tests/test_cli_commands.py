"""Tests for the unified CLI entrypoint."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite import cli


class TestCliParser(unittest.TestCase):
    def test_parser_exposes_expected_subcommands(self):
        parser = cli.build_parser()
        subparsers = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
        self.assertIn("pipeline", subparsers)
        self.assertIn("validate-artifacts", subparsers)
        self.assertIn("erc", subparsers)
        self.assertIn("ngspice-doctor", subparsers)
        self.assertIn("simulation-plan", subparsers)
        self.assertIn("model-api", subparsers)
        self.assertIn("agent", subparsers)

    def test_main_without_args_prints_help(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main([])
        self.assertEqual(code, 0)
        self.assertIn("Unified command-line entrypoint", buffer.getvalue())


class TestCliDispatch(unittest.TestCase):
    def test_pipeline_command_delegates_to_run_pipeline(self):
        with patch("kicad_suite.cli.run_pipeline", return_value={"ok": True}) as run_pipeline:
            code = cli.main(["pipeline", "model.json", "out"])
        self.assertEqual(code, 0)
        run_pipeline.assert_called_once_with("model.json", "out")

    def test_validate_artifacts_forwards_flags(self):
        with patch("kicad_suite.cli.validate_artifacts_main", return_value=0) as validate:
            code = cli.main(["validate-artifacts", "--summary", "summary.json", "--strict", "--require-erc", "--json"])
        self.assertEqual(code, 0)
        validate.assert_called_once()
        forwarded = validate.call_args.args[0]
        self.assertEqual(forwarded, ["--summary", "summary.json", "--strict", "--require-erc", "--json"])

    def test_ngspice_doctor_prints_environment_report(self):
        report = {"found": False, "recommendations": ["install ngspice"]}
        with patch("kicad_suite.cli.diagnose_ngspice_environment", return_value=report) as diagnose:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["ngspice-doctor"])
        self.assertEqual(code, 0)
        diagnose.assert_called_once()
        self.assertIn("install ngspice", buffer.getvalue())

    def test_simulation_plan_command_delegates(self):
        model = {"request_id": "r1", "project_id": "p1", "topology": "demo", "components": [], "nets": []}
        with patch("kicad_suite.cli.load_circuit_model", return_value=model) as load_model:
            with patch(
                "kicad_suite.cli.build_simulation_plan",
                return_value={"schema_version": "simulation-plan.v1"},
            ) as build_plan:
                with patch(
                    "kicad_suite.cli.simulation_plan_to_dict",
                    return_value={"schema_version": "simulation-plan.v1"},
                ) as to_dict:
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main(["simulation-plan", "model.json"])
        self.assertEqual(code, 0)
        load_model.assert_called_once()
        build_plan.assert_called_once()
        to_dict.assert_called_once()

    def test_model_api_command_injects_cli_options(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            request_path = tmp_path / "request.json"
            model_path = tmp_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            config_path = tmp_path / "external-tools.local.json"
            request_path.write_text(
                json.dumps(
                    {
                        "request_id": "cli-model-api-1",
                        "operation": "export_report",
                        "payload": {},
                    }
                ),
                encoding="utf-8",
            )
            config_path.write_text("{}", encoding="utf-8")

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cli.main(
                        [
                            "model-api",
                            str(request_path),
                            "--model",
                            str(model_path),
                            "--config",
                            str(config_path),
                            "--dry-run",
                            "--no-commit",
                            "--no-diff",
                            "--no-snapshot",
                            "--no-strict",
                        ]
                    )

        self.assertEqual(code, 0)
        sent_request = service.handle_dict.call_args.args[0]
        self.assertEqual(sent_request["payload"]["config"], str(config_path))
        self.assertTrue(sent_request["options"]["dry_run"])
        self.assertFalse(sent_request["options"]["commit"])
        self.assertFalse(sent_request["options"]["return_diff"])
        self.assertFalse(sent_request["options"]["return_snapshot"])
        self.assertFalse(sent_request["options"]["strict"])

    def test_model_api_dry_run_does_not_update_project_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            request_path = tmp_path / "request.json"
            model_path = tmp_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            request_path.write_text(
                json.dumps(
                    {
                        "request_id": "cli-model-api-dry-run",
                        "operation": "add_component",
                        "payload": {"ref": "U1"},
                    }
                ),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                with patch("kicad_suite.cli.ProjectState") as state_cls:
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main(
                            [
                                "model-api",
                                str(request_path),
                                "--model",
                                str(model_path),
                                "--dry-run",
                            ]
                        )

        self.assertEqual(code, 0)
        state_cls.assert_not_called()

    def test_agent_manifest_prints_agent_entry_schema(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(["agent", "manifest"])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["schema_version"], "kas-agent-entry.v1")
        self.assertIn("run", payload["commands"])
        self.assertIn("build-ir", payload["commands"])
        self.assertIn("doctor", payload["commands"])
        self.assertIn("pins", payload["commands"])
        self.assertIn("self-test", payload["commands"])
        self.assertIn("build-kicad-plan", payload["commands"])
        self.assertIn("patch", payload["commands"])

    def test_agent_run_builds_model_api_request_from_project(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source" / "circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps(
                    {
                        "schema_version": "circuit-model.v1",
                        "request_id": "demo",
                        "project_id": "agent-demo",
                        "topology": "agent_board",
                        "components": [],
                        "nets": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cli.main(
                        [
                            "agent",
                            "run",
                            "add_net",
                            "--project",
                            str(project_path),
                            "--payload-json",
                            '{"name":"+3V3"}',
                            "--dry-run",
                        ]
                    )

        self.assertEqual(code, 0)
        sent_request = service.handle_dict.call_args.args[0]
        self.assertEqual(sent_request["schema_version"], "dsl-api-request.v1")
        self.assertEqual(sent_request["project_id"], "agent-demo")
        self.assertEqual(sent_request["topology"], "agent_board")
        self.assertEqual(sent_request["operation"], "add_net")
        self.assertEqual(sent_request["payload"], {"name": "+3V3"})
        self.assertTrue(sent_request["options"]["dry_run"])

    def test_agent_create_builds_create_hardware_project_request(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir) / "new-board"
            source_model = Path(tmp_dir) / "source.json"
            source_model.write_text(
                json.dumps(
                    {
                        "schema_version": "circuit-model.v1",
                        "request_id": "src",
                        "project_id": "src",
                        "topology": "src",
                        "components": [],
                        "nets": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.return_value
                service.handle_dict.return_value = {"success": True}
                with patch("kicad_suite.cli.ProjectState"):
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main(
                            [
                                "agent",
                                "create",
                                str(project_path),
                                "--project-id",
                                "new-board",
                                "--source-model",
                                str(source_model),
                                "--overwrite",
                                "--export-ir",
                            ]
                        )

        self.assertEqual(code, 0)
        sent_request = service.handle_dict.call_args.args[0]
        self.assertEqual(sent_request["operation"], "create_hardware_project")
        self.assertEqual(sent_request["payload"]["project_id"], "new-board")
        self.assertEqual(sent_request["payload"]["source_model"], str(source_model.resolve()))
        self.assertTrue(sent_request["payload"]["overwrite"])
        self.assertTrue(sent_request["payload"]["export_ir"])

    def test_agent_export_kicad_uses_project_defaults(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir) / "agent-board"
            project_path.mkdir()
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps(
                    {
                        "schema_version": "circuit-model.v1",
                        "request_id": "demo",
                        "project_id": "agent-board",
                        "topology": "agent_board",
                        "components": [],
                        "nets": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                with patch("kicad_suite.cli.ProjectState"):
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main(["agent", "export-kicad", "--project", str(project_path)])

        self.assertEqual(code, 0)
        sent_request = service.handle_dict.call_args.args[0]
        self.assertEqual(sent_request["operation"], "export_kicad_project")
        self.assertEqual(sent_request["payload"]["project_name"], "agent_board")
        self.assertEqual(Path(sent_request["payload"]["output_dir"]), project_path / "output")

    def test_agent_build_ir_writes_structured_ir_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps(
                    {
                        "schema_version": "circuit-model.v1",
                        "request_id": "demo",
                        "project_id": "agent-demo",
                        "topology": "agent_board",
                        "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
                        "nets": [],
                    }
                ),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "build-ir", "--project", str(project_path)])

            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["stage"], "build_ir")
            self.assertTrue((project_path / "build" / "ir.v1.json").exists())

    def test_agent_validate_ir_writes_validation_report(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps(
                    {
                        "schema_version": "circuit-model.v1",
                        "request_id": "demo",
                        "project_id": "agent-demo",
                        "topology": "agent_board",
                        "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
                        "nets": [],
                    }
                ),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "validate-ir", "--project", str(project_path)])

            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["stage"], "ir_validation")
            self.assertTrue((project_path / "build" / "ir-validation.json").exists())

    def test_agent_report_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps(
                    {
                        "schema_version": "circuit-model.v1",
                        "request_id": "demo",
                        "project_id": "agent-demo",
                        "topology": "agent_board",
                        "components": [],
                        "nets": [],
                    }
                ),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "report", "--project", str(project_path), "--markdown"])

            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["stage"], "report")
            self.assertTrue((project_path / "build" / "report.json").exists())
            self.assertTrue((project_path / "build" / "report.md").exists())

    def test_agent_doctor_returns_structured_checks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "doctor", "--project", tmp_dir])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["stage"], "doctor")
        self.assertTrue(any(item["name"] == "python" for item in payload["checks"]))

    def test_agent_diagnose_returns_structured_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "diag-demo",
                    "topology": "diag_board",
                    "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
                    "nets": [{"name": "VCC", "members": ["U1.1"]}],
                    "sheets": [],
                    "risks": [],
                }),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "diagnose", "--project", str(project_path)])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["stage"], "diagnose")
        self.assertIn("must_fix", payload["diagnostics"])
        self.assertIn("suggested_actions", payload["diagnostics"])

    # -- new agent commands ---------------------------------------------------

    def test_agent_pins_free_lists_free_gpio_pins(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "pin-demo",
                    "topology": "pin_board",
                    "components": [{"ref": "U1", "role": "mcu", "value": "ESP32-S3"}],
                    "nets": [],
                }),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "pins", "free", "--project", str(project_path), "--ref", "U1"])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["stage"], "pins_free")
        self.assertEqual(payload["mcu_ref"], "U1")
        self.assertIsInstance(payload["pins"], list)

    def test_agent_pins_assign_builds_connect_pin_request(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "pin-assign-demo",
                    "topology": "pin_board",
                    "components": [],
                    "nets": [],
                }),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                with patch("kicad_suite.cli.ProjectState"):
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main([
                            "agent", "pins", "assign",
                            "--project", str(project_path),
                            "--ref", "U1",
                            "--pin", "GPIO17",
                            "--net", "LCD_BL",
                            "--role", "backlight",
                        ])

        self.assertEqual(code, 0)
        sent = service.handle_dict.call_args.args[0]
        self.assertEqual(sent["operation"], "connect_pin_to_net")
        self.assertEqual(sent["payload"]["ref"], "U1")
        self.assertEqual(sent["payload"]["pin"], "GPIO17")
        self.assertEqual(sent["payload"]["net"], "LCD_BL")
        self.assertEqual(sent["payload"]["role"], "backlight")

    def test_agent_pins_check_reports_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "pin-check-demo",
                    "topology": "pin_board",
                    "components": [{"ref": "U1", "role": "mcu", "value": "ESP32-S3"}],
                    "nets": [],
                }),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "pins", "check", "--project", str(project_path)])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["stage"], "pins_check")
        self.assertIsInstance(payload["conflicts"], list)

    def test_agent_build_kicad_plan_compiles_execution_plan(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "plan-demo",
                    "topology": "plan_board",
                    "components": [],
                    "nets": [],
                }),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                with patch("kicad_suite.cli.ProjectState"):
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main(["agent", "build-kicad-plan", "--project", str(project_path)])

        self.assertEqual(code, 0)
        sent = service.handle_dict.call_args.args[0]
        self.assertEqual(sent["operation"], "compile_kicad_execution_plan")
        self.assertIn("output_dir", sent["payload"])

    def test_agent_patch_applies_model_patch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "patch-demo",
                    "topology": "patch_board",
                    "components": [],
                    "nets": [],
                }),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.ModelApiService") as service_cls:
                service = service_cls.from_repository.return_value
                service.handle_dict.return_value = {"success": True}
                with patch("kicad_suite.cli.ProjectState"):
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main([
                            "agent", "patch",
                            "--project", str(project_path),
                            "--payload-json", '{"components":[{"ref":"U1","role":"mcu"}]}',
                        ])

        self.assertEqual(code, 0)
        sent = service.handle_dict.call_args.args[0]
        self.assertEqual(sent["operation"], "patch_model")
        self.assertIn("patch", sent["payload"])
        self.assertIn("components", sent["payload"]["patch"])

    def test_agent_workflow_run_delegates_to_service(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "workflow-demo",
                    "topology": "workflow_board",
                    "components": [],
                    "nets": [],
                }),
                encoding="utf-8",
            )

            with patch("kicad_suite.cli.AgentWorkflowService") as workflow_cls:
                workflow_cls.return_value.run.return_value = {
                    "ok": True,
                    "stage": "workflow",
                    "status": "completed",
                }
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cli.main([
                        "agent", "workflow", "run",
                        "--project", str(project_path),
                        "--template", "lcsc_selection_v1",
                        "--timeout", "5",
                    ])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "completed")
        workflow_cls.return_value.run.assert_called_once()
        call_kwargs = workflow_cls.return_value.run.call_args.kwargs
        self.assertEqual(call_kwargs["template"], "lcsc_selection_v1")
        self.assertEqual(call_kwargs["timeout"], 5)

    def test_agent_workflow_propose_delegates_to_service(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            proposal = project_path / "proposal.json"
            proposal.write_text("{}", encoding="utf-8")

            with patch("kicad_suite.cli.AgentWorkflowService") as workflow_cls:
                workflow_cls.return_value.propose_workflow.return_value = {
                    "ok": True,
                    "stage": "workflow_propose",
                    "status": "waiting_for_agent_execution",
                }
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cli.main([
                        "agent", "workflow", "propose",
                        "--project", str(project_path),
                        "--file", str(proposal),
                    ])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "waiting_for_agent_execution")
        workflow_cls.return_value.propose_workflow.assert_called_once()

    def test_agent_workflow_choose_route_delegates_to_service(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)

            with patch("kicad_suite.cli.AgentWorkflowService") as workflow_cls:
                workflow_cls.return_value.choose_route.return_value = {
                    "ok": True,
                    "stage": "workflow_choose_route",
                    "status": "route_chosen",
                }
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = cli.main([
                        "agent", "workflow", "choose-route",
                        "--project", str(project_path),
                        "--workflow", "lcsc_selection_v1",
                        "--reason", "agent_confirmed",
                    ])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "route_chosen")
        workflow_cls.return_value.choose_route.assert_called_once()
        kwargs = workflow_cls.return_value.choose_route.call_args.kwargs
        self.assertEqual(kwargs["workflow_id"], "lcsc_selection_v1")
        self.assertEqual(kwargs["reason"], "agent_confirmed")

    def test_diagnostic_parser_extracts_error_codes(self):
        from kicad_suite.cli import _parse_diagnostic

        d = _parse_diagnostic("IR.nets: duplicate net name 'VCC'", "error")
        self.assertEqual(d["code"], "DUPLICATE_NET_NAME")
        self.assertEqual(d["location"], "VCC")
        self.assertIn("suggestion", d)

        d = _parse_diagnostic("IR.nets['+3V3'] has no members (floating)", "warning")
        self.assertEqual(d["code"], "FLOATING_NET")
        self.assertIn("suggestion", d)

        d = _parse_diagnostic("IR.components: duplicate ref 'U1'", "error")
        self.assertEqual(d["code"], "DUPLICATE_COMPONENT_REF")
        self.assertEqual(d["location"], "U1")

        d = _parse_diagnostic("IR schema_version must be 'ir.v1', got 'circuit-model.v1'", "error")
        self.assertEqual(d["code"], "SCHEMA_VERSION_MISMATCH")
        self.assertEqual(d["location"], "ir.v1")
        self.assertIn("suggestion", d)

        d = _parse_diagnostic("some completely unknown error text here", "error")
        self.assertEqual(d["code"], "UNKNOWN_VALUE")

    def test_agent_build_ir_validates_output_is_written(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "ir-demo",
                    "topology": "ir_board",
                    "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
                    "nets": [{"name": "VCC", "members": ["U1.1"]}],
                }),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "build-ir", "--project", str(project_path)])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["summary"]["components"], 0)
        self.assertEqual(payload["summary"]["nets"], 1)

    def test_agent_validate_ir_with_duplicate_net_produces_specific_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir)
            model_path = project_path / "source/circuit-model.source.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps({
                    "schema_version": "circuit-model.v1",
                    "request_id": "demo",
                    "project_id": "dup-demo",
                    "topology": "dup_board",
                    "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
                    "nets": [
                        {"name": "VCC", "members": ["U1.1"]},
                        {"name": "VCC", "members": ["U1.2"]},
                    ],
                }),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["agent", "validate-ir", "--project", str(project_path)])

        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["ok"])
        self.assertGreater(len(payload["diagnostics"]), 0)
        codes = [d["code"] for d in payload["diagnostics"]]
        self.assertIn("DUPLICATE_NET_NAME", codes)

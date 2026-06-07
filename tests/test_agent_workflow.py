"""Tests for agent-assisted workflow orchestration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.orchestration.agent_tasks import agent_tasks_path, read_agent_tasks
from kicad_suite.orchestration.agent_workflow import AgentWorkflowService
from kicad_suite.orchestration.workflow_stack import WorkflowStackStore, workflow_stack_path


class FakePartResolutionService:
    def __init__(self, result: dict):
        self.result = result
        self.calls: list[dict] = []

    def resolve_symbols(self, project_path, model, *, timeout=120, model_path=None):
        self.calls.append({
            "project_path": project_path,
            "model": model,
            "timeout": timeout,
            "model_path": model_path,
        })
        return self.result


def _write_source_model(project: Path, components: list[dict]) -> Path:
    model_path = project / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        json.dumps({
            "schema_version": "circuit-model.v1",
            "request_id": "workflow-demo",
            "project_id": "workflow-demo",
            "topology": "workflow_demo",
            "components": components,
            "nets": [],
        }),
        encoding="utf-8",
    )
    return model_path


def test_lcsc_workflow_emits_agent_tasks_for_missing_selection(tmp_path: Path) -> None:
    model_path = _write_source_model(
        tmp_path,
        [
            {
                "ref": "R1",
                "role": "pullup_resistor",
                "value": "10k",
                "package": "0603",
                "search_hints": ["10k resistor 0603"],
            }
        ],
    )
    fake = FakePartResolutionService({
        "ok": False,
        "resolved": 0,
        "downloaded": 0,
        "needs_selection": 1,
        "failed": 0,
        "details": [
            {
                "ref": "R1",
                "role": "pullup_resistor",
                "value": "10k",
                "reason": "missing_selected_part_lcsc_id",
            }
        ],
    })

    result = AgentWorkflowService(part_resolution_service=fake).run(
        tmp_path,
        template="lcsc_selection_v1",
        model_path=model_path,
        timeout=7,
    )

    assert result["ok"] is False
    assert result["status"] == "waiting_for_agent"
    assert result["task_count"] == 1
    assert result["workflow"]["status"] == "waiting_for_agent"
    assert result["workflow"]["active_workflow"] == "lcsc_selection_v1"
    assert result["workflow"]["depth"] == 1
    assert workflow_stack_path(tmp_path).exists()
    assert fake.calls[0]["timeout"] == 7
    tasks = read_agent_tasks(tmp_path)
    assert tasks["task_count"] == 1
    task = tasks["tasks"][0]
    assert task["type"] == "agent_decision"
    assert task["decision_schema"] == "select_lcsc_part_v1"
    assert task["component"]["ref"] == "R1"
    assert task["component"]["package"] == "0603"
    assert "10k" in task["suggested_query"]


def test_lcsc_workflow_completed_clears_stale_tasks(tmp_path: Path) -> None:
    model_path = _write_source_model(
        tmp_path,
        [
            {
                "ref": "R1",
                "role": "pullup_resistor",
                "value": "10k",
                "package": "0603",
                "selected_part": {"lcsc_id": "C22843"},
            }
        ],
    )
    task_path = agent_tasks_path(tmp_path)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text('{"tasks":[{"task_id":"stale"}]}', encoding="utf-8")
    fake = FakePartResolutionService({
        "ok": True,
        "resolved": 1,
        "downloaded": 1,
        "needs_selection": 0,
        "failed": 0,
        "details": [{"ref": "R1", "source": "selected_part_lcsc_id"}],
    })

    result = AgentWorkflowService(part_resolution_service=fake).run(
        tmp_path,
        template="lcsc_selection_v1",
        model_path=model_path,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert not task_path.exists()
    assert not workflow_stack_path(tmp_path).exists()


def test_workflow_status_summarizes_pending_tasks(tmp_path: Path) -> None:
    task_path = agent_tasks_path(tmp_path)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        json.dumps({
            "schema_version": "agent_tasks.v1",
            "workflow_id": "lcsc_selection_v1",
            "status": "waiting_for_agent",
            "reason": "needs_selection",
            "tasks": [
                {
                    "task_id": "select_lcsc:R1",
                    "type": "agent_decision",
                    "decision_schema": "select_lcsc_part_v1",
                    "component": {"ref": "R1", "value": "10k", "package": "0603"},
                }
            ],
        }),
        encoding="utf-8",
    )

    result = AgentWorkflowService().status(tmp_path)

    assert result["ok"] is True
    assert result["workflow"]["status"] == "waiting_for_agent"
    assert result["workflow"]["pending_task_count"] == 1
    assert result["workflow"]["current_task"]["task_id"] == "select_lcsc:R1"
    assert result["workflow"]["current_task"]["status"] == "pending"
    assert result["workflow"]["task_summary"][0]["summary"] == "R1 10k 0603"


def test_workflow_stack_can_push_child_workflow(tmp_path: Path) -> None:
    service = AgentWorkflowService()

    result = service.push_workflow(tmp_path, workflow_id="lcsc_selection_v1", reason="needs_selection")

    assert result["ok"] is True
    assert result["action"] == "push_workflow"
    assert result["workflow"]["depth"] == 1
    assert result["workflow"]["active_workflow"] == "lcsc_selection_v1"
    payload = WorkflowStackStore(tmp_path).load()
    assert payload["stack"][0]["reason"] == "needs_selection"


def test_workflow_stack_can_pop_completed_workflow(tmp_path: Path) -> None:
    service = AgentWorkflowService()
    service.push_workflow(tmp_path, workflow_id="lcsc_selection_v1", reason="needs_selection")

    result = service.pop_workflow(tmp_path, reason="workflow_completed")

    assert result["ok"] is True
    assert result["action"] == "pop_workflow"
    assert result["workflow_id"] == "lcsc_selection_v1"
    assert result["workflow"]["depth"] == 0
    assert not workflow_stack_path(tmp_path).exists()


def test_workflow_stack_module_exposes_navigation_api(tmp_path: Path) -> None:
    store = WorkflowStackStore(tmp_path)

    assert store.is_empty()
    payload = store.replace_root("lcsc_selection_v1", reason="manual_start")

    assert payload["active_workflow"] == "lcsc_selection_v1"
    assert not store.is_empty()
    assert store.depth() == 1
    assert store.peek()["workflow_id"] == "lcsc_selection_v1"

    status = store.to_agent_status(
        tasks_file=str(agent_tasks_path(tmp_path)),
        pending_task_count=0,
        current_task={},
        task_summary=[],
        reason="",
    )

    assert status["active_workflow"] == "lcsc_selection_v1"
    assert status["stack"]["depth"] == 1


def test_full_build_pushes_lcsc_selection_for_missing_parts(tmp_path: Path) -> None:
    model_path = _write_source_model(
        tmp_path,
        [
            {
                "ref": "R1",
                "role": "pullup_resistor",
                "value": "10k",
                "package": "0603",
            }
        ],
    )
    fake = FakePartResolutionService({
        "ok": False,
        "resolved": 0,
        "downloaded": 0,
        "needs_selection": 1,
        "failed": 0,
        "details": [
            {
                "ref": "R1",
                "role": "pullup_resistor",
                "value": "10k",
                "reason": "missing_selected_part_lcsc_id",
            }
        ],
    })

    result = AgentWorkflowService(part_resolution_service=fake).run(
        tmp_path,
        template="full_build_v1",
        model_path=model_path,
    )

    assert result["status"] == "waiting_for_agent"
    assert result["workflow_id"] == "lcsc_selection_v1"
    assert result["workflow"]["active_workflow"] == "lcsc_selection_v1"
    assert result["workflow"]["depth"] == 2
    stack = result["workflow"]["stack"]
    assert stack[0]["workflow_id"] == "full_build_v1"
    assert stack[0]["status"] == "paused"
    assert stack[0]["blocked_by"] == "lcsc_selection_v1"


def test_repair_after_diagnose_emits_repair_and_review_tasks(tmp_path: Path) -> None:
    _write_source_model(tmp_path, [])
    diagnostics = {
        "ok": False,
        "counts": {"must_fix": 1, "review_required": 1, "library_noise": 0},
        "diagnostics": {
            "must_fix": [
                {
                    "source": "erc",
                    "code": "POWER_INPUT_NOT_DRIVEN",
                    "severity": "error",
                    "message": "Power input pin is not driven.",
                }
            ],
            "review_required": [
                {
                    "source": "ir_validation",
                    "code": "FLOATING_NET",
                    "severity": "warning",
                    "message": "Net is floating.",
                }
            ],
            "library_noise": [],
        },
    }

    with patch("kicad_suite.orchestration.agent_workflow.build_agent_diagnostics", return_value=diagnostics):
        result = AgentWorkflowService().run(
            tmp_path,
            template="repair_after_diagnose_v1",
            model_path=tmp_path / "source" / "circuit-model.source.json",
        )

    assert result["status"] == "waiting_for_agent"
    assert result["task_count"] == 2
    tasks = read_agent_tasks(tmp_path)["tasks"]
    assert tasks[0]["type"] == "agent_repair"
    assert tasks[0]["decision_schema"] == "repair_diagnostic_v1"
    assert tasks[1]["type"] == "agent_review"
    assert tasks[1]["decision_schema"] == "review_diagnostic_v1"


def test_workflow_status_lists_main_and_problem_templates(tmp_path: Path) -> None:
    result = AgentWorkflowService().status(tmp_path)
    template_ids = {item["workflow_id"] for item in result["templates"]}

    assert {"full_build_v1", "lcsc_selection_v1", "repair_after_diagnose_v1"} <= template_ids

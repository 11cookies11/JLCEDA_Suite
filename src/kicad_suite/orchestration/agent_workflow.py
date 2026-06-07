"""Agent-assisted workflow orchestration.

This module coordinates existing atomic services. It does not make part
selection decisions and does not write generated files as source truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..application_services.agent_diagnostics import build_agent_diagnostics
from ..application_services.part_resolution_service import PartResolutionService
from ..domain.core.simulation_planner import load_circuit_model
from .agent_tasks import (
    agent_tasks_path,
    clear_agent_tasks,
    current_task,
    read_agent_tasks,
    summarize_tasks,
    write_agent_tasks,
)
from .workflow_stack import WorkflowStackStore
from .workflow_templates import get_template, list_templates


DEFAULT_WORKFLOW_ID = "lcsc_selection_v1"


class AgentWorkflowService:
    """Run idempotent agent-assisted workflows."""

    def __init__(self, *, part_resolution_service: PartResolutionService | None = None) -> None:
        self.part_resolution_service = part_resolution_service or PartResolutionService()

    def run(
        self,
        project_path: str | Path,
        *,
        template: str = DEFAULT_WORKFLOW_ID,
        model_path: str | Path | None = None,
        timeout: int = 120,
    ) -> dict[str, Any]:
        project = Path(project_path)
        stack = WorkflowStackStore(project)
        stack.ensure(template)
        while True:
            active = stack.active()
            workflow_id = str(active.get("workflow_id", "")) if active else template
            workflow_template = get_template(workflow_id)
            if workflow_template is None:
                stack.update_active(status="failed", reason="unknown_template")
                return self._with_stack({
                    "ok": False,
                    "stage": "workflow",
                    "status": "failed",
                    "reason": "unknown_template",
                    "workflow_id": workflow_id,
                    "available_templates": [item["workflow_id"] for item in list_templates()],
                }, stack)
            if workflow_template.workflow_id == "full_build_v1":
                result = self._run_full_build(project, model_path=model_path)
            elif workflow_template.workflow_id == "lcsc_selection_v1":
                result = self._run_lcsc_selection(project, model_path=model_path, timeout=timeout)
            elif workflow_template.workflow_id == "repair_after_diagnose_v1":
                result = self._run_repair_after_diagnose(project, model_path=model_path)
            else:
                stack.update_active(status="failed", reason="unsupported_template")
                return self._with_stack({
                    "ok": False,
                    "stage": "workflow",
                    "status": "failed",
                    "reason": "unsupported_template",
                    "workflow_id": workflow_template.workflow_id,
                }, stack)
            status = str(result.get("status", ""))
            if status == "pushed_workflow":
                continue
            if status == "completed":
                self.pop_workflow(project, reason="workflow_completed")
                if not stack.active():
                    return self._with_stack(result, stack)
                continue
            stack.update_active(
                status=status or "failed",
                reason=str(result.get("reason", "")),
                tasks_file=str(result.get("tasks_file", "")),
            )
            return self._with_stack(result, stack)

    def status(self, project_path: str | Path) -> dict[str, Any]:
        project = Path(project_path)
        tasks = read_agent_tasks(project)
        task_list = tasks.get("tasks", [])
        if not isinstance(task_list, list):
            task_list = []
        stack_store = WorkflowStackStore(project)
        workflow = stack_store.to_agent_status(
            tasks_file=tasks.get("path", str(agent_tasks_path(project))),
            pending_task_count=int(tasks.get("task_count", 0) or 0),
            current_task=current_task(task_list),
            task_summary=summarize_tasks(task_list),
            reason=str(tasks.get("reason", "")),
        )
        if not workflow.get("active_workflow") and tasks.get("workflow_id"):
            workflow["active_workflow"] = tasks.get("workflow_id", "")
        return {
            "ok": True,
            "stage": "workflow_status",
            "workflow": workflow,
            "templates": list_templates(),
        }

    def push_workflow(
        self,
        project_path: str | Path,
        *,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        template = get_template(workflow_id)
        if template is None:
            return {
                "ok": False,
                "stage": "workflow_push",
                "status": "failed",
                "reason": "unknown_template",
                "workflow_id": workflow_id,
            }
        stack = WorkflowStackStore(project_path)
        payload = stack.push(workflow_id, reason=reason)
        return {
            "ok": True,
            "stage": "workflow_action",
            "action": "push_workflow",
            "status": payload.get("status", "running"),
            "workflow_id": workflow_id,
            "workflow": stack.summary(),
        }

    def pop_workflow(
        self,
        project_path: str | Path,
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        stack = WorkflowStackStore(project_path)
        before = stack.summary()
        active = before.get("active_workflow", "")
        payload = stack.pop()
        after = stack.summary()
        return {
            "ok": True,
            "stage": "workflow_action",
            "action": "pop_workflow",
            "reason": reason,
            "workflow_id": active,
            "status": payload.get("status", "idle"),
            "workflow": after,
        }

    def push(
        self,
        project_path: str | Path,
        *,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Backward-compatible wrapper for internal push_workflow action."""
        return self.push_workflow(project_path, workflow_id=workflow_id, reason=reason)

    def _run_lcsc_selection(
        self,
        project_path: Path,
        *,
        model_path: str | Path | None,
        timeout: int,
    ) -> dict[str, Any]:
        workflow_id = "lcsc_selection_v1"
        model_file = Path(model_path) if model_path is not None else project_path / "source" / "circuit-model.source.json"
        try:
            model = load_circuit_model(model_file)
        except FileNotFoundError:
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "failed",
                "reason": "model_not_found",
                "model": str(model_file),
            }
        result = self.part_resolution_service.resolve_symbols(
            project_path,
            model,
            timeout=timeout,
            model_path=model_file,
        )
        tasks = _build_lcsc_selection_tasks(model, result)
        if tasks:
            tasks_file = write_agent_tasks(
                project_path,
                workflow_id=workflow_id,
                tasks=tasks,
                reason="needs_selection",
            )
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "waiting_for_agent",
                "reason": "needs_selection",
                "tasks_file": str(tasks_file),
                "task_count": len(tasks),
                "rerun_after_agent": True,
                "next_action": "read tasks_file, set selected_part.lcsc_id through Model API, then rerun this workflow",
                "resolution": _resolution_summary(result),
            }
        clear_agent_tasks(project_path)
        return {
            "ok": bool(result.get("ok", False)),
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "completed" if result.get("ok", False) else "failed",
            "reason": "" if result.get("ok", False) else "resolution_failed",
            "tasks_file": str(agent_tasks_path(project_path)),
            "task_count": 0,
            "resolution": _resolution_summary(result),
        }

    def _run_full_build(
        self,
        project_path: Path,
        *,
        model_path: str | Path | None,
    ) -> dict[str, Any]:
        workflow_id = "full_build_v1"
        model_file = Path(model_path) if model_path is not None else project_path / "source" / "circuit-model.source.json"
        try:
            model = load_circuit_model(model_file)
        except FileNotFoundError:
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "failed",
                "reason": "model_not_found",
                "model": str(model_file),
            }

        missing = _components_missing_lcsc(model)
        if missing:
            self.push_workflow(project_path, workflow_id="lcsc_selection_v1", reason="needs_selection")
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "pushed_workflow",
                "reason": "needs_selection",
                "pushed_workflow": "lcsc_selection_v1",
                "missing_lcsc_count": len(missing),
            }

        diagnostics = build_agent_diagnostics(project_path, model_file)
        counts = diagnostics.get("counts", {}) if isinstance(diagnostics, dict) else {}
        must_fix = int(counts.get("must_fix", 0) or 0)
        review_required = int(counts.get("review_required", 0) or 0)
        if must_fix or review_required:
            reason = "diagnose_must_fix" if must_fix else "diagnose_review_required"
            self.push_workflow(project_path, workflow_id="repair_after_diagnose_v1", reason=reason)
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "pushed_workflow",
                "reason": reason,
                "pushed_workflow": "repair_after_diagnose_v1",
                "diagnostics": {
                    "must_fix": must_fix,
                    "review_required": review_required,
                },
            }

        clear_agent_tasks(project_path)
        return {
            "ok": True,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "completed",
            "reason": "",
            "diagnostics": {
                "must_fix": must_fix,
                "review_required": review_required,
            },
        }

    def _run_repair_after_diagnose(
        self,
        project_path: Path,
        *,
        model_path: str | Path | None,
    ) -> dict[str, Any]:
        workflow_id = "repair_after_diagnose_v1"
        model_file = Path(model_path) if model_path is not None else project_path / "source" / "circuit-model.source.json"
        diagnostics = build_agent_diagnostics(project_path, model_file)
        tasks = _build_diagnostic_tasks(diagnostics)
        if tasks:
            tasks_file = write_agent_tasks(
                project_path,
                workflow_id=workflow_id,
                tasks=tasks,
                reason="diagnose_requires_agent",
            )
            counts = diagnostics.get("counts", {}) if isinstance(diagnostics, dict) else {}
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "waiting_for_agent",
                "reason": "diagnose_requires_agent",
                "tasks_file": str(tasks_file),
                "task_count": len(tasks),
                "rerun_after_agent": True,
                "next_action": "resolve current diagnostic task through Model API, then rerun this workflow",
                "diagnostics": counts,
            }
        clear_agent_tasks(project_path)
        return {
            "ok": True,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "completed",
            "reason": "",
            "diagnostics": diagnostics.get("counts", {}) if isinstance(diagnostics, dict) else {},
        }

    @staticmethod
    def _with_stack(result: dict[str, Any], stack: WorkflowStackStore) -> dict[str, Any]:
        return {**result, "workflow": stack.summary()}


def _resolution_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(result.get("ok", False)),
        "resolved": int(result.get("resolved", 0) or 0),
        "downloaded": int(result.get("downloaded", 0) or 0),
        "needs_selection": int(result.get("needs_selection", 0) or 0),
        "failed": int(result.get("failed", 0) or 0),
    }


def _build_lcsc_selection_tasks(model: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    components_by_ref = _components_by_ref(model)
    tasks: list[dict[str, Any]] = []
    for item in result.get("details", []):
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason", ""))
        if reason not in {"missing_selected_part_lcsc_id", "timeout"}:
            continue
        ref = str(item.get("ref", "")).strip()
        component = components_by_ref.get(ref, {})
        tasks.append(_lcsc_selection_task(ref, component, reason))
    return tasks


def _components_missing_lcsc(model: dict[str, Any]) -> list[dict[str, Any]]:
    components = model.get("components", [])
    if not isinstance(components, list):
        return []
    missing: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        selected = component.get("selected_part", {}) if isinstance(component.get("selected_part"), dict) else {}
        if not str(selected.get("lcsc_id", "")).strip():
            missing.append(component)
    return missing


def _build_diagnostic_tasks(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    buckets = diagnostics.get("diagnostics", {}) if isinstance(diagnostics, dict) else {}
    tasks: list[dict[str, Any]] = []
    for bucket_name, task_type, schema in (
        ("must_fix", "agent_repair", "repair_diagnostic_v1"),
        ("review_required", "agent_review", "review_diagnostic_v1"),
    ):
        items = buckets.get(bucket_name, []) if isinstance(buckets, dict) else []
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", "DIAGNOSTIC"))
            source = str(item.get("source", "diagnose"))
            tasks.append({
                "task_id": f"{task_type}:{source}:{code}:{index}",
                "type": task_type,
                "decision_schema": schema,
                "reason": bucket_name,
                "diagnostic": item,
                "allowed_actions": [
                    "apply_model_operation",
                    "needs_human_review",
                    "mark_library_noise",
                    "skip_with_reason",
                ],
                "allowed_operations": [
                    "connect_member",
                    "disconnect_member",
                    "set_net_kind",
                    "update_component",
                    "set_selected_part",
                    "patch_model",
                ],
                "write_operation": "agent run or agent patch",
            })
    return tasks


def _components_by_ref(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components = model.get("components", [])
    if not isinstance(components, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", "")).strip()
        if ref:
            result[ref] = component
    return result


def _lcsc_selection_task(ref: str, component: dict[str, Any], reason: str) -> dict[str, Any]:
    selected = component.get("selected_part", {}) if isinstance(component.get("selected_part"), dict) else {}
    search_hints = component.get("search_hints", [])
    if not isinstance(search_hints, list):
        search_hints = []
    value = str(component.get("value", "") or "")
    package = str(component.get("package", "") or selected.get("package", "") or "")
    role = str(component.get("role", "") or "")
    query_terms = [term for term in (value, role, package) if term]
    return {
        "task_id": f"select_lcsc:{ref or 'unknown'}",
        "type": "agent_decision",
        "decision_schema": "select_lcsc_part_v1",
        "reason": reason,
        "component": {
            "ref": ref,
            "role": role,
            "value": value,
            "package": package,
            "selected_part": {
                key: selected.get(key)
                for key in ("display_name", "mpn", "manufacturer", "package")
                if selected.get(key) not in (None, "")
            },
            "search_hints": [str(item) for item in search_hints if str(item).strip()],
        },
        "suggested_query": " ".join(query_terms).strip(),
        "allowed_actions": ["select", "needs_human_review", "skip"],
        "write_operation": "set_selected_part",
    }

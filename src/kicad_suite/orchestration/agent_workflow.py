"""Agent-assisted workflow orchestration.

This module coordinates workflow templates and task emission. It does not
make part selection decisions or perform symbol downloading as a workflow
dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..application_services.agent_diagnostics import build_agent_diagnostics
from ..application_services.part_resolution_service import PartResolutionService
from ..domain.core.ir_compiler import build_ir
from ..domain.core.ir_validator import validate_ir
from ..domain.core.simulation_planner import load_circuit_model
from .proposed_workflow import (
    load_proposed_workflow_file,
    proposed_workflow_summary,
    save_proposed_workflow,
    validate_proposed_workflow,
)
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
ROUTE_PENDING_WORKFLOW_ID = "__route_pending__"


class AgentWorkflowService:
    """Run idempotent agent-assisted workflows."""

    def __init__(self, *, part_resolution_service: object | None = None) -> None:
        # Kept for backward compatibility with older tests and callers.
        self.part_resolution_service = part_resolution_service

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
                if workflow_id == ROUTE_PENDING_WORKFLOW_ID:
                    return self._with_stack({
                        "ok": False,
                        "stage": "workflow",
                        "status": "waiting_for_agent",
                        "reason": "route_decision_required",
                        "workflow_id": workflow_id,
                        "tasks_file": str(agent_tasks_path(project)),
                        "rerun_after_agent": True,
                    }, stack)
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
                result = self._run_full_build(project, model_path=model_path, timeout=timeout)
            elif workflow_template.workflow_id == "lcsc_selection_v1":
                result = self._run_lcsc_selection(project, model_path=model_path, timeout=timeout)
            elif workflow_template.workflow_id == "repair_after_diagnose_v1":
                result = self._run_repair_after_diagnose(project, model_path=model_path)
            elif workflow_template.workflow_id == "ir_repair_v1":
                result = self._run_ir_repair(project, model_path=model_path)
            elif workflow_template.workflow_id == "export_repair_v1":
                result = self._run_export_repair(project, model_path=model_path)
            elif workflow_template.workflow_id == "unknown_task_v1":
                result = self._run_unknown_task(project)
            else:
                self.push_workflow(project, workflow_id="unknown_task_v1", reason="unsupported_template")
                result = {
                    "ok": False,
                    "stage": "workflow",
                    "status": "pushed_workflow",
                    "reason": "unsupported_template",
                    "workflow_id": workflow_template.workflow_id,
                    "pushed_workflow": "unknown_task_v1",
                }
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
        workflow["proposed_workflow"] = proposed_workflow_summary(project)
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

    def propose_workflow(
        self,
        project_path: str | Path,
        *,
        proposal_file: str | Path,
    ) -> dict[str, Any]:
        project = Path(project_path)
        plan = load_proposed_workflow_file(proposal_file)
        validation = validate_proposed_workflow(plan)
        path = save_proposed_workflow(project, plan, validation)
        if not validation.get("ok"):
            return {
                "ok": False,
                "stage": "workflow_propose",
                "status": "failed",
                "reason": "invalid_proposed_workflow",
                "proposal_file": str(path),
                "validation": validation,
            }
        workflow_id = f"agent_proposed:{validation.get('workflow_id')}"
        stack = WorkflowStackStore(project)
        payload = stack.replace_active(
            workflow_id,
            reason=str(plan.get("reason", "agent_proposed_workflow")),
            status="waiting_for_agent_execution",
            proposed_workflow_file=str(path),
        )
        return {
            "ok": True,
            "stage": "workflow_propose",
            "status": "waiting_for_agent_execution",
            "workflow_id": workflow_id,
            "proposal_file": str(path),
            "validation": validation,
            "workflow": WorkflowStackStore(project).summary(),
            "stack": payload,
        }

    def choose_route(
        self,
        project_path: str | Path,
        *,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        project = Path(project_path)
        template = get_template(workflow_id)
        if template is None:
            return {
                "ok": False,
                "stage": "workflow_choose_route",
                "status": "failed",
                "reason": "unknown_template",
                "workflow_id": workflow_id,
            }
        stack = WorkflowStackStore(project)
        active = stack.active()
        if not active or str(active.get("workflow_id", "")) != ROUTE_PENDING_WORKFLOW_ID:
            return {
                "ok": False,
                "stage": "workflow_choose_route",
                "status": "failed",
                "reason": "no_route_pending",
                "workflow_id": workflow_id,
                "workflow": stack.summary(),
            }
        clear_agent_tasks(project)
        payload = stack.replace_active(
            workflow_id,
            reason=reason or str(active.get("reason", "route_chosen")),
            status="running",
            chosen_from=ROUTE_PENDING_WORKFLOW_ID,
        )
        return {
            "ok": True,
            "stage": "workflow_choose_route",
            "status": "route_chosen",
            "workflow_id": workflow_id,
            "workflow": stack.summary(),
            "stack": payload,
        }

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
        missing = _components_missing_lcsc(model)
        tasks = [_lcsc_selection_task(item) for item in missing]
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
                "next_action": "read tasks_file, choose LCSC IDs through Model API, then rerun this workflow",
                "selection": {
                    "missing_selected_part_lcsc_id": len(missing),
                },
            }
        clear_agent_tasks(project_path)
        return {
            "ok": True,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "completed",
            "reason": "",
            "tasks_file": str(agent_tasks_path(project_path)),
            "task_count": 0,
            "selection": {
                "missing_selected_part_lcsc_id": 0,
            },
        }

    def _run_full_build(
        self,
        project_path: Path,
        *,
        model_path: str | Path | None,
        timeout: int = 120,
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
            return self._emit_route_task(
                project_path,
                workflow_id=workflow_id,
                task_id="route:needs_selection",
                reason="needs_selection",
                summary=f"{len(missing)} components are missing selected_part.lcsc_id.",
                recommended_workflow="lcsc_selection_v1",
                alternatives=["lcsc_selection_v1", "unknown_task_v1"],
                context={
                    "missing_lcsc_count": len(missing),
                    "sample_refs": [str(item.get("ref", "")) for item in missing[:10] if isinstance(item, dict)],
                    "source": "full_build_v1.parts_milestone",
                },
            )

        # Library resolution milestone — download symbols/footprints for selected parts
        library_result = PartResolutionService().resolve_symbols(
            project_path,
            model,
            timeout=timeout,
            model_path=model_file,
        )
        needs_sel = int(library_result.get("needs_selection", 0) or 0)
        failed_dl = int(library_result.get("failed", 0) or 0)

        # Components still missing LCSC → route back to selection workflow
        if needs_sel:
            return self._emit_route_task(
                project_path,
                workflow_id=workflow_id,
                task_id="route:needs_selection",
                reason="needs_selection",
                summary=f"{needs_sel} components still need LCSC selection after library resolution.",
                recommended_workflow="lcsc_selection_v1",
                alternatives=["lcsc_selection_v1", "unknown_task_v1"],
                context={
                    "needs_selection": needs_sel,
                    "source": "full_build_v1.library_milestone",
                },
            )

        # Download failures → per-component tasks for agent to fix
        if failed_dl:
            tasks = _build_library_failure_tasks(library_result)
            tasks_file = write_agent_tasks(
                project_path,
                workflow_id=workflow_id,
                tasks=tasks,
                reason="library_resolution_failed",
            )
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "waiting_for_agent",
                "reason": "library_resolution_failed",
                "tasks_file": str(tasks_file),
                "task_count": len(tasks),
                "rerun_after_agent": True,
                "next_action": "fix failed selected_part data (retry download or choose alternative LCSC), then rerun this workflow",
                "library": {
                    "resolved": library_result.get("resolved", 0),
                    "downloaded": library_result.get("downloaded", 0),
                    "failed": failed_dl,
                },
            }

        # IR build milestone
        try:
            ir = build_ir(model)
        except (ValueError, KeyError, TypeError) as exc:
            return self._emit_route_task(
                project_path,
                workflow_id=workflow_id,
                task_id="route:ir_build_failed",
                reason="ir_build_failed",
                summary=f"IR build failed: {exc}",
                recommended_workflow="ir_repair_v1",
                alternatives=["ir_repair_v1", "unknown_task_v1"],
                context={
                    "error": str(exc),
                    "source": "full_build_v1.ir_build_milestone",
                },
            )

        # IR validation milestone
        ir_report = validate_ir(ir)
        if ir_report.errors:
            return self._emit_route_task(
                project_path,
                workflow_id=workflow_id,
                task_id="route:ir_validation_failed",
                reason="ir_validation_failed",
                summary=f"IR validation found {len(ir_report.errors)} errors and {len(ir_report.warnings)} warnings.",
                recommended_workflow="ir_repair_v1",
                alternatives=["ir_repair_v1", "unknown_task_v1"],
                context={
                    "ir_errors": len(ir_report.errors),
                    "ir_warnings": len(ir_report.warnings),
                    "source": "full_build_v1.ir_milestone",
                },
            )

        # KiCad export milestone
        export_result = self._export_kicad_for_workflow(project_path, model, model_file)
        if not export_result.get("ok"):
            return self._emit_route_task(
                project_path,
                workflow_id=workflow_id,
                task_id="route:export_failed",
                reason="export_failed",
                summary=str(export_result.get("error", "KiCad export failed.")),
                recommended_workflow="export_repair_v1",
                alternatives=["export_repair_v1", "unknown_task_v1"],
                context={
                    "error": export_result.get("error", "KiCad export failed."),
                    "source": "full_build_v1.export_milestone",
                },
            )

        # Post-export diagnose milestone
        diagnostics = build_agent_diagnostics(project_path, model_file)
        counts = diagnostics.get("counts", {}) if isinstance(diagnostics, dict) else {}
        must_fix = int(counts.get("must_fix", 0) or 0)
        review_required = int(counts.get("review_required", 0) or 0)
        if must_fix or review_required:
            reason = "diagnose_must_fix" if must_fix else "diagnose_review_required"
            return self._emit_route_task(
                project_path,
                workflow_id=workflow_id,
                task_id=f"route:{reason}",
                reason=reason,
                summary=f"diagnose reports {must_fix} must_fix and {review_required} review_required findings.",
                recommended_workflow="repair_after_diagnose_v1",
                alternatives=["repair_after_diagnose_v1", "unknown_task_v1"],
                context={
                    "must_fix": must_fix,
                    "review_required": review_required,
                    "source": "full_build_v1.diagnose_milestone",
                },
            )

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
            "export": export_result.get("export", {}),
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

    def _run_ir_repair(
        self,
        project_path: Path,
        *,
        model_path: str | Path | None,
    ) -> dict[str, Any]:
        workflow_id = "ir_repair_v1"
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
        try:
            ir = build_ir(model)
        except (ValueError, KeyError, TypeError) as exc:
            tasks_file = write_agent_tasks(
                project_path,
                workflow_id=workflow_id,
                tasks=[{
                    "task_id": "repair:ir_build:BUILD_FAILED:1",
                    "type": "agent_repair",
                    "decision_schema": "repair_diagnostic_v1",
                    "reason": "must_fix",
                    "diagnostic": {
                        "source": "ir_build",
                        "code": "IR_BUILD_FAILED",
                        "severity": "error",
                        "message": str(exc),
                    },
                    "allowed_actions": [
                        "apply_model_operation",
                        "needs_human_review",
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
                }],
                reason="ir_build_failed",
            )
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "waiting_for_agent",
                "reason": "ir_build_failed",
                "tasks_file": str(tasks_file),
                "task_count": 1,
                "rerun_after_agent": True,
                "next_action": "fix the circuit model so it can compile to IR, then rerun this workflow",
            }
        report = validate_ir(ir)
        tasks = _build_ir_diagnostic_tasks(report)
        if tasks:
            tasks_file = write_agent_tasks(
                project_path,
                workflow_id=workflow_id,
                tasks=tasks,
                reason="ir_validation_failed",
            )
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "waiting_for_agent",
                "reason": "ir_validation_failed",
                "tasks_file": str(tasks_file),
                "task_count": len(tasks),
                "rerun_after_agent": True,
                "next_action": "resolve IR validation errors through Model API, then rerun this workflow",
                "ir_validation": {
                    "errors": len(report.errors),
                    "warnings": len(report.warnings),
                },
            }
        clear_agent_tasks(project_path)
        return {
            "ok": True,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "completed",
            "reason": "",
            "ir_validation": {
                "errors": 0,
                "warnings": 0,
            },
        }

    @staticmethod
    def _export_kicad_for_workflow(
        project_path: Path,
        model: dict[str, Any],
        model_file: Path,
    ) -> dict[str, Any]:
        """Run KiCad export through ModelApiService and return a summary.

        This keeps the full export logic (plan, write, postprocess, ERC, report)
        inside the Model API layer; the workflow only orchestrates the result.
        """
        from ..model_api import CircuitModelRepository, ModelApiService  # noqa: PLC0415
        try:
            service = ModelApiService.from_repository(CircuitModelRepository(model_file))
            project_id = str(model.get("project_id", "") or project_path.name)
            topology = str(model.get("topology", "") or project_id.replace("-", "_"))
            request = {
                "schema_version": "dsl-api-request.v1",
                "request_id": f"agent-workflow-export-{topology}",
                "project_id": project_id,
                "topology": topology,
                "operation": "export_kicad_project",
                "payload": {
                    "output_dir": str(project_path / "output"),
                    "project_name": topology,
                },
            }
            result = service.handle_dict(request)
            if result.get("success"):
                return {"ok": True, "export": result.get("result", {})}
            errors = result.get("errors", [])
            message = str(errors[0].get("message", "Export failed.")) if errors else "Export failed."
            return {"ok": False, "error": message}
        except ImportError as exc:
            return {"ok": False, "error": f"Model API not available: {exc}"}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}

    def _run_export_repair(
        self,
        project_path: Path,
        *,
        model_path: str | Path | None,
    ) -> dict[str, Any]:
        workflow_id = "export_repair_v1"
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
        export_result = self._export_kicad_for_workflow(project_path, model, model_file)
        if not export_result.get("ok"):
            tasks_file = write_agent_tasks(
                project_path,
                workflow_id=workflow_id,
                tasks=[{
                    "task_id": "repair:export_kicad:EXPORT_FAILED:1",
                    "type": "agent_repair",
                    "decision_schema": "repair_diagnostic_v1",
                    "reason": "must_fix",
                    "diagnostic": {
                        "source": "export_kicad",
                        "code": "EXPORT_FAILED",
                        "severity": "error",
                        "message": str(export_result.get("error", "KiCad export failed.")),
                    },
                    "allowed_actions": [
                        "apply_model_operation",
                        "needs_human_review",
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
                }],
                reason="export_failed",
            )
            return {
                "ok": False,
                "stage": "workflow",
                "workflow_id": workflow_id,
                "status": "waiting_for_agent",
                "reason": "export_failed",
                "tasks_file": str(tasks_file),
                "task_count": 1,
                "rerun_after_agent": True,
                "next_action": "fix circuit model issues and rerun this workflow",
            }
        clear_agent_tasks(project_path)
        return {
            "ok": True,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "completed",
            "reason": "",
            "export": export_result.get("export", {}),
        }

    def _run_unknown_task(self, project_path: Path) -> dict[str, Any]:
        workflow_id = "unknown_task_v1"
        stack = WorkflowStackStore(project_path).summary()
        tasks_file = write_agent_tasks(
            project_path,
            workflow_id=workflow_id,
            tasks=[
                {
                    "task_id": "review:unknown_task:1",
                    "type": "agent_review",
                    "decision_schema": "classify_unknown_task_v1",
                    "reason": "unknown_condition",
                    "summary": "Classify the current unknown workflow condition.",
                    "context": {
                        "workflow_stack": stack,
                    },
                    "allowed_actions": [
                        "choose_workflow_template",
                        "needs_human_review",
                        "mark_blocked",
                        "skip_with_reason",
                    ],
                    "available_templates": [item["workflow_id"] for item in list_templates()],
                }
            ],
            reason="unknown_condition",
        )
        return {
            "ok": False,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "waiting_for_agent",
            "reason": "unknown_condition",
            "tasks_file": str(tasks_file),
            "task_count": 1,
            "rerun_after_agent": True,
            "next_action": "classify current unknown task and choose a specific workflow or request human review",
        }

    def _emit_route_task(
        self,
        project_path: Path,
        *,
        workflow_id: str,
        task_id: str,
        reason: str,
        summary: str,
        recommended_workflow: str,
        alternatives: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tasks_file = write_agent_tasks(
            project_path,
            workflow_id=workflow_id,
            tasks=[
                {
                    "task_id": task_id,
                    "type": "agent_review",
                    "decision_schema": "choose_workflow_route_v1",
                    "reason": reason,
                    "summary": summary,
                    "recommended_workflow": recommended_workflow,
                    "alternatives": alternatives,
                    "context": context,
                    "allowed_actions": [
                        "confirm_route",
                        "choose_alternative",
                        "propose_workflow",
                        "needs_human_review",
                        "mark_blocked",
                    ],
                }
            ],
            reason="route_decision_required",
        )
        WorkflowStackStore(project_path).push_placeholder(
            reason=reason,
            task_id=task_id,
            tasks_file=str(tasks_file),
            recommended_workflow=recommended_workflow,
        )
        return {
            "ok": False,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "waiting_for_agent",
            "reason": "route_decision_required",
            "tasks_file": str(tasks_file),
            "task_count": 1,
            "route": {
                "reason": reason,
                "recommended_workflow": recommended_workflow,
                "alternatives": alternatives,
            },
            "rerun_after_agent": True,
            "next_action": "choose a workflow route, propose a workflow, or request human review",
        }

    @staticmethod
    def _with_stack(result: dict[str, Any], stack: WorkflowStackStore) -> dict[str, Any]:
        return {**result, "workflow": stack.summary()}


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


def _build_ir_diagnostic_tasks(report: Any) -> list[dict[str, Any]]:
    """Convert an IR validation report (errors/warnings) into agent repair tasks."""
    tasks: list[dict[str, Any]] = []
    errors = getattr(report, "errors", []) if hasattr(report, "errors") else []
    warnings = getattr(report, "warnings", []) if hasattr(report, "warnings") else []
    if not isinstance(errors, list):
        errors = []
    if not isinstance(warnings, list):
        warnings = []
    for index, error in enumerate(errors, start=1):
        message = str(error)
        code = _classify_ir_message(message)
        tasks.append({
            "task_id": f"agent_repair:ir_validation:{code}:{index}",
            "type": "agent_repair",
            "decision_schema": "repair_diagnostic_v1",
            "reason": "must_fix",
            "diagnostic": {
                "source": "ir_validation",
                "code": code,
                "severity": "error",
                "message": message,
            },
            "allowed_actions": [
                "apply_model_operation",
                "needs_human_review",
                "skip_with_reason",
            ],
            "allowed_operations": [
                "connect_member",
                "disconnect_member",
                "set_net_kind",
                "update_component",
                "set_selected_part",
                "patch_model",
                "add_component",
                "remove_component",
                "add_net",
                "remove_net",
                "merge_nets",
            ],
            "write_operation": "agent run or agent patch",
        })
    for index, warning in enumerate(warnings, start=len(errors) + 1):
        message = str(warning)
        code = _classify_ir_message(message)
        tasks.append({
            "task_id": f"agent_review:ir_validation:{code}:{index}",
            "type": "agent_review",
            "decision_schema": "review_diagnostic_v1",
            "reason": "review_required",
            "diagnostic": {
                "source": "ir_validation",
                "code": code,
                "severity": "warning",
                "message": message,
            },
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


def _build_library_failure_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one agent task per failed library download with specific ref, LCSC, and reason."""
    tasks: list[dict[str, Any]] = []
    for item in result.get("details", []):
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason", ""))
        if reason not in {"failed", "timeout", "not_found", "network_error"}:
            continue
        ref = str(item.get("ref", "")).strip()
        lcsc_id = str(item.get("lcsc_id", "")).strip()
        message = str(item.get("message", f"Download failed for {ref} ({lcsc_id})"))
        tasks.append({
            "task_id": f"repair:library:{reason}:{ref or 'unknown'}",
            "type": "agent_repair",
            "decision_schema": "repair_diagnostic_v1",
            "reason": "must_fix",
            "diagnostic": {
                "source": "library_resolution",
                "code": reason.upper(),
                "severity": "error",
                "message": message,
                "ref": ref,
                "lcsc_id": lcsc_id,
            },
            "allowed_actions": [
                "apply_model_operation",
                "retry_download",
                "search_alternative_lcsc",
                "needs_human_review",
                "skip_with_reason",
            ],
            "allowed_operations": [
                "set_selected_part",
                "update_component",
                "patch_model",
            ],
            "write_operation": "agent run set_selected_part or agent jlc search",
            "suggested_action": "retry_download" if reason == "timeout" else "search_alternative_lcsc",
        })
    return tasks


def _classify_ir_message(message: str) -> str:
    """Classify an IR validation message into a stable error code."""
    lower = message.lower()
    if "duplicate" in lower:
        return "DUPLICATE_ENTRY"
    if "missing" in lower or "not found" in lower:
        return "MISSING_REFERENCE"
    if "must be" in lower:
        return "INVALID_FIELD_TYPE"
    if "circular" in lower:
        return "CIRCULAR_REFERENCE"
    if "floating" in lower:
        return "FLOATING_NET"
    if "schema_version" in lower:
        return "SCHEMA_VERSION_MISMATCH"
    if "unknown" in lower:
        return "UNKNOWN_VALUE"
    if "forbidden" in lower or "leaked" in lower or "leakage" in lower:
        return "KICAD_FIELD_LEAKAGE"
    return "VALIDATION_FINDING"


def _lcsc_selection_task(component: dict[str, Any]) -> dict[str, Any]:
    ref = str(component.get("ref", "")).strip()
    reason = "missing_selected_part_lcsc_id"
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

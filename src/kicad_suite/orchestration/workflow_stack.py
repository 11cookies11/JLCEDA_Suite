"""Lightweight workflow stack state for agent-assisted orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STACK_SCHEMA_VERSION = "agent_workflow_stack.v1"
STACK_FILENAME = "agent-workflow-stack.json"


def workflow_stack_path(project_path: str | Path) -> Path:
    return Path(project_path) / "build" / STACK_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_entry(workflow_id: str, *, reason: str = "") -> dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "status": "running",
        "reason": reason,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


class WorkflowStackStore:
    """Persist a stack of active workflows.

    The stack stores workflow-level nesting only. Individual workflow handlers
    remain idempotent and recompute progress from project files on each run.
    """

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)
        self.path = workflow_stack_path(self.project_path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_payload()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        stack = payload.get("stack", [])
        if not isinstance(stack, list):
            stack = []
        payload["stack"] = [item for item in stack if isinstance(item, dict)]
        payload.setdefault("schema_version", STACK_SCHEMA_VERSION)
        payload.setdefault("status", "idle" if not payload["stack"] else "running")
        payload["active_workflow"] = self._active_workflow(payload["stack"])
        return payload

    def ensure(self, workflow_id: str) -> dict[str, Any]:
        payload = self.load()
        if payload["stack"]:
            return payload
        payload = self._payload([_new_entry(workflow_id)])
        self.save(payload)
        return payload

    def save(self, payload: dict[str, Any]) -> Path:
        stack = payload.get("stack", [])
        if not isinstance(stack, list):
            stack = []
        payload = self._payload(stack, status=str(payload.get("status", "")) or None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.path

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def is_empty(self) -> bool:
        return not bool(self.load().get("stack", []))

    def depth(self) -> int:
        return len(self.load().get("stack", []))

    def active(self) -> dict[str, Any] | None:
        stack = self.load().get("stack", [])
        return stack[-1] if stack else None

    def peek(self) -> dict[str, Any] | None:
        return self.active()

    def replace_root(self, workflow_id: str, *, reason: str = "") -> dict[str, Any]:
        payload = self._payload([_new_entry(workflow_id, reason=reason)])
        self.save(payload)
        return self.load()

    def replace_active(self, workflow_id: str, *, reason: str = "", status: str = "running", **extra: Any) -> dict[str, Any]:
        payload = self.load()
        stack = payload.get("stack", [])
        entry = _new_entry(workflow_id, reason=reason)
        entry["status"] = status
        entry.update({key: value for key, value in extra.items() if value not in (None, "")})
        if stack:
            stack[-1] = entry
        else:
            stack = [entry]
        payload["stack"] = stack
        payload["status"] = status
        self.save(payload)
        return self.load()

    def push_placeholder(self, *, reason: str, task_id: str, parent_status: str = "paused", **extra: Any) -> dict[str, Any]:
        payload = self.load()
        stack = payload.get("stack", [])
        placeholder_id = "__route_pending__"
        if stack:
            parent = dict(stack[-1])
            parent["status"] = parent_status
            parent["blocked_by"] = placeholder_id
            parent["updated_at"] = _now_iso()
            stack[-1] = parent
        entry = _new_entry(placeholder_id, reason=reason)
        entry.update({
            "status": "waiting_for_agent",
            "task_id": task_id,
        })
        entry.update({key: value for key, value in extra.items() if value not in (None, "")})
        stack.append(entry)
        payload["stack"] = stack
        payload["status"] = "waiting_for_agent"
        self.save(payload)
        return self.load()

    def update_active(self, **updates: Any) -> dict[str, Any]:
        payload = self.load()
        stack = payload.get("stack", [])
        if not stack:
            return payload
        active = dict(stack[-1])
        active.update({key: value for key, value in updates.items() if value not in (None, "")})
        active["updated_at"] = _now_iso()
        stack[-1] = active
        payload["stack"] = stack
        payload["status"] = str(active.get("status", "running"))
        self.save(payload)
        return self.load()

    def push(self, workflow_id: str, *, reason: str = "", parent_status: str = "paused") -> dict[str, Any]:
        payload = self.load()
        stack = payload.get("stack", [])
        if stack:
            parent = dict(stack[-1])
            parent["status"] = parent_status
            parent["blocked_by"] = workflow_id
            parent["updated_at"] = _now_iso()
            stack[-1] = parent
        stack.append(_new_entry(workflow_id, reason=reason))
        payload["stack"] = stack
        payload["status"] = "running"
        self.save(payload)
        return self.load()

    def pop(self) -> dict[str, Any]:
        payload = self.load()
        stack = payload.get("stack", [])
        if stack:
            stack.pop()
        if not stack:
            self.clear()
            return self._empty_payload()
        active = dict(stack[-1])
        active.pop("blocked_by", None)
        active["status"] = "running"
        active["updated_at"] = _now_iso()
        stack[-1] = active
        payload["stack"] = stack
        payload["status"] = "running"
        self.save(payload)
        return self.load()

    def summary(self) -> dict[str, Any]:
        payload = self.load()
        stack = payload.get("stack", [])
        return {
            "status": payload.get("status", "idle"),
            "active_workflow": payload.get("active_workflow", ""),
            "stack_file": str(self.path),
            "depth": len(stack),
            "stack": stack,
        }

    def to_agent_status(
        self,
        *,
        tasks_file: str,
        pending_task_count: int,
        current_task: dict[str, Any] | None = None,
        task_summary: list[dict[str, Any]] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        stack = self.summary()
        status = str(stack.get("status", "idle"))
        if not stack.get("depth") and pending_task_count:
            status = "waiting_for_agent"
        return {
            "status": status,
            "active_workflow": stack.get("active_workflow", ""),
            "tasks_file": tasks_file,
            "pending_task_count": pending_task_count,
            "current_task": current_task or {},
            "task_summary": task_summary or [],
            "reason": reason,
            "stack": stack,
            "next_action": (
                "resolve current_task, then rerun workflow"
                if pending_task_count
                else "run a workflow template"
            ),
        }

    def _payload(self, stack: list[Any], *, status: str | None = None) -> dict[str, Any]:
        clean_stack = [item for item in stack if isinstance(item, dict)]
        active = self._active_workflow(clean_stack)
        return {
            "schema_version": STACK_SCHEMA_VERSION,
            "status": status or ("idle" if not clean_stack else str(clean_stack[-1].get("status", "running"))),
            "active_workflow": active,
            "updated_at": _now_iso(),
            "stack": clean_stack,
        }

    def _empty_payload(self) -> dict[str, Any]:
        return self._payload([])

    @staticmethod
    def _active_workflow(stack: list[dict[str, Any]]) -> str:
        if not stack:
            return ""
        return str(stack[-1].get("workflow_id", ""))

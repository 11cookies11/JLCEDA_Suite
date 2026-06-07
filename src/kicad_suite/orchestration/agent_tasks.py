"""Read and write agent workflow task files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASKS_SCHEMA_VERSION = "agent_tasks.v1"
TASKS_FILENAME = "agent-tasks.json"


def agent_tasks_path(project_path: str | Path) -> Path:
    return Path(project_path) / "build" / TASKS_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_agent_tasks(
    project_path: str | Path,
    *,
    workflow_id: str,
    tasks: list[dict[str, Any]],
    reason: str = "",
) -> Path:
    path = agent_tasks_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": TASKS_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "status": "waiting_for_agent" if tasks else "completed",
        "reason": reason,
        "created_at": _now_iso(),
        "task_count": len(tasks),
        "tasks": tasks,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_agent_tasks(project_path: str | Path) -> dict[str, Any]:
    path = agent_tasks_path(project_path)
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "schema_version": TASKS_SCHEMA_VERSION,
            "workflow_id": "",
            "status": "idle",
            "task_count": 0,
            "tasks": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    return {
        "exists": True,
        "path": str(path),
        "schema_version": str(payload.get("schema_version", "")),
        "workflow_id": str(payload.get("workflow_id", "")),
        "status": str(payload.get("status", "waiting_for_agent")),
        "reason": str(payload.get("reason", "")),
        "task_count": len(tasks),
        "tasks": tasks,
    }


def task_status(task: dict[str, Any]) -> str:
    status = str(task.get("status", "")).strip()
    return status or "pending"


def summarize_task(task: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(task, dict):
        return {}
    component = task.get("component", {})
    diagnostic = task.get("diagnostic", {})
    summary = str(task.get("summary", "")).strip()
    if not summary and isinstance(component, dict):
        ref = str(component.get("ref", "")).strip()
        value = str(component.get("value", "")).strip()
        package = str(component.get("package", "")).strip()
        role = str(component.get("role", "")).strip()
        summary = " ".join(item for item in (ref, value, package, role) if item)
    if not summary and isinstance(diagnostic, dict):
        code = str(diagnostic.get("code", "")).strip()
        message = str(diagnostic.get("message", "")).strip()
        summary = ": ".join(item for item in (code, message) if item)
    return {
        "task_id": str(task.get("task_id", "")),
        "type": str(task.get("type", "")),
        "status": task_status(task),
        "decision_schema": str(task.get("decision_schema", "")),
        "summary": summary,
    }


def summarize_tasks(tasks: list[Any], *, limit: int = 20) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        summary = summarize_task(task)
        if summary:
            summaries.append(summary)
        if len(summaries) >= limit:
            break
    return summaries


def current_task(tasks: list[Any]) -> dict[str, Any]:
    for task in tasks:
        if isinstance(task, dict) and task_status(task) == "pending":
            return summarize_task(task)
    for task in tasks:
        if isinstance(task, dict):
            return summarize_task(task)
    return {}


def clear_agent_tasks(project_path: str | Path) -> None:
    path = agent_tasks_path(project_path)
    if path.exists():
        path.unlink()

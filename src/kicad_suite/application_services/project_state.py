"""Project state management: lifecycle tracking for circuit-model projects."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -- state constants --
STATUS_INIT = "INIT"
STATUS_DIRTY = "DIRTY"
STATUS_VALID = "VALID"
STATUS_INVALID = "INVALID"
STATUS_BUILT = "BUILT"
STATUS_STALE = "STALE"
STATUS_BUILD_FAILED = "BUILD_FAILED"

_STATE_ORDER = {
    STATUS_INIT: 0,
    STATUS_DIRTY: 1,
    STATUS_VALID: 2,
    STATUS_INVALID: 2,
    STATUS_BUILT: 3,
    STATUS_BUILD_FAILED: 3,
    STATUS_STALE: 4,
}

# operations that modify the model (trigger mark_dirty)
_MUTATING_OPERATIONS = frozenset({
    "add_component", "update_component", "remove_component",
    "add_net", "update_net", "remove_net",
    "connect_member", "disconnect_member", "connect_members", "disconnect_members",
    "rename_net", "merge_nets", "split_net",
    "set_selected_part", "add_candidate_part", "remove_candidate_part",
    "select_part", "update_selected_part", "replace_selected_part",
    "lock_selected_part", "unlock_selected_part",
    "set_pinmap", "update_pinmap", "remove_pinmap",
    "connect_pin_to_net", "disconnect_pin_from_net",
    "add_risk", "update_risk", "remove_risk",
    "add_design_decision", "update_design_decision", "remove_design_decision",
    "add_sheet", "update_sheet", "remove_sheet",
    "add_calculation", "update_calculation", "remove_calculation",
    "add_constraint", "update_constraint", "remove_constraint",
    "add_power_rail", "update_power_rail", "remove_power_rail",
    "set_component_ref", "set_component_role", "set_component_value",
    "set_component_notes", "set_component_availability",
    "set_net_kind", "set_net_notes", "set_net_aliases", "set_net_domain",
    "mark_component_resolved", "mark_component_needs_review", "mark_component_blocked",
    "mark_net_global", "mark_net_power", "mark_net_high_speed", "mark_net_debug",
    "mark_net_differential_pair", "mark_risk_resolved", "mark_risk_blocked",
    "mark_risk_open", "mark_risk_in_progress", "mark_risk_deferred",
    "mark_decision_proposed", "mark_decision_accepted", "mark_decision_rejected",
    "mark_decision_needs_review", "mark_decision_finalized",
    "assign_component_to_sheet", "assign_net_to_sheet",
    "set_schema_version", "set_request_id", "set_project_id", "set_topology",
    "update_metadata", "set_rail_voltage", "set_rail_current_limit",
    "set_rail_sequence_order", "set_rail_enable_condition",
    "set_rail_source", "set_rail_sink", "set_rail_parent", "set_rail_children",
    "set_risk_category", "set_risk_severity", "set_risk_owner", "set_risk_due_reason",
    "set_constraint_type", "set_constraint_scope", "set_constraint_priority",
    "set_constraint_status", "set_calculation_formula", "set_calculation_inputs",
    "set_calculation_result", "set_calculation_unit",
    "set_sheet_name", "set_sheet_inputs", "set_sheet_outputs",
    "set_sheet_components", "set_sheet_nets", "set_sheet_constraints", "set_sheet_notes",
    "link_risk_to_component", "link_risk_to_net", "link_risk_to_decision", "link_risk_to_sheet",
    "link_decision_to_component", "link_decision_to_net", "link_decision_to_risk",
    "link_decision_to_sheet", "link_calculation_to_component", "link_calculation_to_net",
    "apply_batch", "apply_operation",
    "load_model", "reset_model", "patch_model", "merge_model",
    "set_pin_name", "set_pin_role", "set_pin_direction", "set_pin_no_connect",
    "add_pin_alias", "resolve_pin_alias",
})

# operations that run validation
_VALIDATE_OPERATIONS = frozenset({
    "validate_model", "validate_schema", "validate_references",
    "validate_connectivity", "validate_pinmap", "validate_power_tree",
    "validate_power_budget", "validate_sequence", "validate_sheet_boundary",
    "validate_sheet_inputs_outputs", "validate_part_availability",
    "validate_risk_consistency", "validate_intent", "validate_readiness",
})

# operations that produce committed project build output.
_BUILD_OPERATIONS = frozenset({
    "export_kicad_project",
})


class ProjectState:
    """Track a circuit-model project's lifecycle state.

    State machine::

        INIT → DIRTY → VALID/INVALID → BUILT/STALE/BUILD_FAILED

    The state file ``project.state.json`` is a cache — it can be deleted and
    regenerated via :meth:`recompute`.
    """

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path).resolve()
        self.model_path = self.project_path / "source" / "circuit-model.source.json"
        self.state_path = self.project_path / "project.state.json"
        self.logs_dir = self.project_path / "logs"
        self.log_path = self.logs_dir / "operations.jsonl"
        self.state: dict[str, Any] = {}

    # -- file I/O ----------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """Load ``project.state.json``, falling back to recompute if missing."""
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.refresh_from_model()
        else:
            self.state = self._empty_state()
            self.recompute()
        return self.state

    def save(self) -> None:
        """Persist current state to ``project.state.json``."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def recompute(self) -> dict[str, Any]:
        """Rebuild state from ``source/circuit-model.source.json`` on disk (idempotent)."""
        model = self._read_model()
        if model is None:
            self.state = self._empty_state()
        else:
            self._sync_model_metadata(model)
        self.save()
        return self.state

    def refresh_from_model(self) -> bool:
        """Refresh cached model-derived fields when the source model changed.

        Returns True when the in-memory state was updated.
        """
        model = self._read_model()
        if model is None:
            return False
        current_hash = self._hash_dict(model)
        current_summary = self._build_summary(model)
        dsl = self.state.setdefault("dsl", {})
        changed = (
            dsl.get("hash") != current_hash
            or self.state.get("summary") != current_summary
            or self.state.get("project", {}).get("id") != str(model.get("project_id", ""))
            or self.state.get("project", {}).get("name") != str(model.get("topology", ""))
        )
        if not changed:
            return False
        self._sync_model_metadata(model)
        self.save()
        return True

    # -- status queries ----------------------------------------------------

    def get_status(self) -> str:
        """Return the current project status string."""
        return str(self.state.get("status", STATUS_INIT))

    def get_summary(self) -> dict[str, Any]:
        """Return structured project summary."""
        return dict(self.state.get("summary", {}))

    def get_explain(self) -> str:
        """Return a natural-language description of the project."""
        status = self.get_status()
        s = self.state.get("summary", {})
        lines = [
            f"Project: {self.state.get('project', {}).get('name', 'unknown')}",
            f"Status:  {status}",
            f"Components: {s.get('component_count', 0)}",
            f"Nets:       {s.get('net_count', 0)}",
            f"Risks:      {s.get('risk_count', 0)}",
        ]
        dsl = self.state.get("dsl", {})
        if dsl.get("hash"):
            lines.append(f"DSL hash:  {dsl['hash']}")
        diag = self.state.get("diagnostics", {})
        if diag.get("errors"):
            lines.append(f"Errors:    {diag['errors']}")
        if diag.get("warnings"):
            lines.append(f"Warnings:  {diag['warnings']}")

        hints = {
            STATUS_INIT: "Project created. Add components to get started.",
            STATUS_DIRTY: "Model modified. Run validate to check consistency.",
            STATUS_VALID: "Validation passed. Run compile/build to generate KiCad output.",
            STATUS_INVALID: "Validation failed. Check diagnostics and fix errors.",
            STATUS_BUILT: "Build succeeded. KiCad project is up to date.",
            STATUS_BUILD_FAILED: "Build failed. Check diagnostics for error details.",
            STATUS_STALE: "Model changed since last build. Rebuild to update outputs.",
        }
        lines.append(f"\n{hints.get(status, '')}")
        return "\n".join(lines)

    def is_stale(self) -> bool:
        """Return True if the model hash differs from the build input hash."""
        model = self._read_model()
        if model is None:
            return False
        current_hash = self._hash_dict(model)
        build_hash = self.state.get("build", {}).get("input_dsl_hash", "")
        return bool(build_hash and current_hash != build_hash)

    # -- state transitions -------------------------------------------------

    def mark_dirty(self, reason: str = "") -> None:
        """Mark the project DIRTY (modified since last validation)."""
        self._ensure_loaded()
        model = self._read_model()
        if model is not None:
            self._sync_model_metadata(model)
        self.state["status"] = STATUS_DIRTY
        self.state.setdefault("diagnostics", {})
        self.state["diagnostics"].setdefault("items", [])
        if reason:
            self.state["diagnostics"]["items"].append({
                "timestamp": _utc_now(),
                "level": "info",
                "message": reason,
            })
        self._append_operation({"op": "mark_dirty", "reason": reason, "ok": True})
        self.save()

    def mark_valid(self, diagnostics: dict[str, Any] | None = None) -> None:
        """Mark the project VALID (validation passed)."""
        self._ensure_loaded()
        model = self._read_model()
        if model is not None:
            self._sync_model_metadata(model)
        self.state["status"] = STATUS_VALID
        self.state["dsl"]["valid"] = True
        if diagnostics:
            self.state["diagnostics"] = {
                "errors": len(diagnostics.get("errors", [])),
                "warnings": len(diagnostics.get("warnings", [])),
                "items": diagnostics.get("errors", []) + diagnostics.get("warnings", []),
            }
        self._append_operation({"op": "mark_valid", "ok": True})
        self.save()

    def mark_invalid(self, diagnostics: dict[str, Any] | None = None) -> None:
        """Mark the project INVALID (validation failed)."""
        self._ensure_loaded()
        model = self._read_model()
        if model is not None:
            self._sync_model_metadata(model)
        self.state["status"] = STATUS_INVALID
        self.state["dsl"]["valid"] = False
        if diagnostics:
            errors = diagnostics.get("errors", [])
            warnings = diagnostics.get("warnings", [])
            self.state["diagnostics"] = {
                "errors": len(errors),
                "warnings": len(warnings),
                "items": [
                    {"level": "error", "message": str(e)} for e in errors
                ] + [
                    {"level": "warning", "message": str(w)} for w in warnings
                ],
            }
        self._append_operation({"op": "mark_invalid", "ok": True})
        self.save()

    def mark_built(self, outputs: dict[str, Any] | None = None, *, op_data: dict[str, Any] | None = None) -> None:
        """Mark the project BUILT (KiCad generation succeeded).

        *op_data* — extra context written to the operation log (symbol counts, ERC, timing).
        """
        self._ensure_loaded()
        model = self._read_model()
        dsl_hash = self._hash_dict(model) if model else ""
        if model is not None:
            self._sync_model_metadata(model)
        self.state["status"] = STATUS_BUILT
        self.state["build"] = {
            "last_build_ok": True,
            "last_build_at": _utc_now(),
            "input_dsl_hash": dsl_hash,
            "outputs": outputs or {},
        }
        entry: dict[str, Any] = {"op": "mark_built", "ok": True, "hash": dsl_hash}
        if op_data:
            entry |= op_data
        self._append_operation(entry)
        self.save()

    def mark_build_failed(self, diagnostics: dict[str, Any] | None = None) -> None:
        """Mark the project BUILD_FAILED."""
        self._ensure_loaded()
        self.state["status"] = STATUS_BUILD_FAILED
        self.state["build"] = {
            "last_build_ok": False,
            "last_build_at": _utc_now(),
            "input_dsl_hash": self.state.get("build", {}).get("input_dsl_hash", ""),
            "outputs": {},
        }
        if diagnostics:
            errors = diagnostics.get("errors", [])
            self.state["diagnostics"] = {
                "errors": len(errors),
                "warnings": len(diagnostics.get("warnings", [])),
                "items": [{"level": "error", "message": str(e)} for e in errors],
            }
        self._append_operation({"op": "mark_build_failed", "ok": False})
        self.save()

    # -- operation history -------------------------------------------------

    def append_operation(self, op: dict[str, Any]) -> None:
        """Record a high-level project operation to the operation log."""
        self._append_operation(op)

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent operations from ``logs/operations.jsonl``."""
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").strip().splitlines()
        entries: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    # -- internal helpers --------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self.state:
            self.load()

    def _read_model(self) -> dict[str, Any] | None:
        if not self.model_path.exists():
            return None
        return json.loads(self.model_path.read_text(encoding="utf-8-sig"))

    def _hash_dict(self, data: dict[str, Any]) -> str:
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:8]

    def _build_summary(self, model: dict[str, Any]) -> dict[str, Any]:
        def _count(key: str) -> int:
            items = model.get(key, [])
            return len(items) if isinstance(items, list) else 0
        return {
            "component_count": _count("components"),
            "net_count": _count("nets"),
            "risk_count": _count("risks"),
            "sheet_count": _count("sheets"),
            "calculation_count": _count("calculations"),
            "decision_count": _count("design_decisions"),
            "constraint_count": _count("constraints"),
            "power_rail_count": _count("power_rails"),
        }

    def _sync_model_metadata(self, model: dict[str, Any]) -> None:
        dsl_hash = self._hash_dict(model)
        self.state.setdefault("dsl", {})["hash"] = dsl_hash
        self.state.setdefault("dsl", {})["path"] = f"source/{self.model_path.name}"
        self.state.setdefault("project", {})["id"] = str(model.get("project_id", ""))
        self.state.setdefault("project", {})["name"] = str(model.get("topology", ""))
        self.state["summary"] = self._build_summary(model)
        self.state["status"] = self._compute_status()

    def _compute_status(self) -> str:
        dsl = self.state.get("dsl", {})
        build = self.state.get("build", {})
        diag = self.state.get("diagnostics", {})

        if not dsl.get("hash"):
            return STATUS_INIT

        # STALE has high priority (per design doc).
        build_hash = build.get("input_dsl_hash", "")
        current_hash = dsl.get("hash", "")
        if build_hash and build_hash != current_hash:
            return STATUS_STALE

        if diag.get("errors", 0) > 0:
            return STATUS_INVALID

        if build.get("last_build_ok") and build_hash == current_hash:
            return STATUS_BUILT

        # BUILD_FAILED only when a build was actually attempted.
        if build.get("last_build_ok") is False and build.get("last_build_at") is not None:
            return STATUS_BUILD_FAILED

        if dsl.get("valid"):
            return STATUS_VALID

        return STATUS_DIRTY

    def _empty_state(self) -> dict[str, Any]:
        return {
            "project": {"id": "", "name": ""},
            "status": STATUS_INIT,
            "dsl": {"path": f"source/{self.model_path.name}", "hash": "", "valid": None},
            "build": {"last_build_ok": False, "last_build_at": None, "input_dsl_hash": "", "outputs": {}},
            "diagnostics": {"errors": 0, "warnings": 0, "items": []},
            "summary": {},
        }

    def _append_operation(self, op: dict[str, Any]) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        entry = {"time": _utc_now(), **op}
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")


# -- module-level helpers -------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_mutating_operation(operation: str) -> bool:
    """Return True if *operation* modifies the circuit model."""
    return operation in _MUTATING_OPERATIONS or operation.startswith("set_") or operation.startswith("mark_")


def is_validate_operation(operation: str) -> bool:
    """Return True if *operation* runs validation."""
    return operation in _VALIDATE_OPERATIONS or operation.startswith("validate_")


def is_build_operation(operation: str) -> bool:
    """Return True if *operation* produces build output."""
    return operation in _BUILD_OPERATIONS

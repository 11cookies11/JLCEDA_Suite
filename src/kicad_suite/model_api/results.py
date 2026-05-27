"""Result objects for the circuit-model DSL API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schema_versions import DSL_API_RESULT_SCHEMA_VERSION
from ..validation.common import ValidationReport


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    path: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.path:
            data["path"] = self.path
        if self.hint:
            data["hint"] = self.hint
        return data


@dataclass
class OperationResult:
    success: bool
    request_id: str
    project_id: str
    operation: str
    diagnostics: ValidationReport
    result: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[ApiError] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    diff: list[dict[str, Any]] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    schema_version: str = DSL_API_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "success": self.success,
            "request_id": self.request_id,
            "project_id": self.project_id,
            "operation": self.operation,
            "result": self.result,
            "diagnostics": _validation_report_to_dict(self.diagnostics),
            "warnings": self.warnings,
            "errors": [error.to_dict() for error in self.errors],
            "before": self.before,
            "after": self.after,
            "diff": self.diff,
            "changed_paths": self.changed_paths,
        }


def _validation_report_to_dict(report: ValidationReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "checks": list(report.checks),
        "stats": dict(report.stats),
    }

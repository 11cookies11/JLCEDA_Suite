"""Request objects for the circuit-model DSL API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schema_versions import DSL_API_REQUEST_SCHEMA_VERSION


@dataclass(frozen=True)
class RequestOptions:
    dry_run: bool = False
    validate_only: bool = False
    commit: bool = True
    strict: bool = True
    return_diff: bool = True
    return_snapshot: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RequestOptions":
        data = payload or {}
        return cls(
            dry_run=bool(data.get("dry_run", False)),
            validate_only=bool(data.get("validate_only", False)),
            commit=bool(data.get("commit", True)),
            strict=bool(data.get("strict", True)),
            return_diff=bool(data.get("return_diff", True)),
            return_snapshot=bool(data.get("return_snapshot", True)),
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "dry_run": self.dry_run,
            "validate_only": self.validate_only,
            "commit": self.commit,
            "strict": self.strict,
            "return_diff": self.return_diff,
            "return_snapshot": self.return_snapshot,
        }


@dataclass(frozen=True)
class OperationRequest:
    request_id: str
    project_id: str
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)
    topology: str = ""
    options: RequestOptions = field(default_factory=RequestOptions)
    schema_version: str = DSL_API_REQUEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "project_id": self.project_id,
            "operation": self.operation,
            "payload": self.payload,
            "options": self.options.to_dict(),
        }
        if self.topology:
            data["topology"] = self.topology
        return data


def operation_request_from_dict(payload: dict[str, Any]) -> OperationRequest:
    if not isinstance(payload, dict):
        raise ValueError("DSL API request must be a JSON object.")
    if payload.get("schema_version") != DSL_API_REQUEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported DSL API request schema_version: {payload.get('schema_version', '')}")
    operation_payload = payload.get("payload", {})
    if not isinstance(operation_payload, dict):
        raise ValueError("DSL API request payload must be an object.")
    options_payload = payload.get("options")
    if options_payload is not None and not isinstance(options_payload, dict):
        raise ValueError("DSL API request options must be an object.")
    return OperationRequest(
        request_id=str(payload.get("request_id", "")),
        project_id=str(payload.get("project_id", "")),
        topology=str(payload.get("topology", "")),
        operation=str(payload.get("operation", "")),
        payload=operation_payload,
        options=RequestOptions.from_dict(options_payload),
        schema_version=str(payload.get("schema_version", "")),
    )

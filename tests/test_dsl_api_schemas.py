"""Basic regression checks for DSL API schema files."""

from __future__ import annotations

import json
from pathlib import Path


def _load_schema(name: str) -> dict[str, object]:
    path = Path("schemas") / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_dsl_api_schema_files_exist_and_match_versions():
    request_schema = _load_schema("dsl-api-request.v1.json")
    result_schema = _load_schema("dsl-api-result.v1.json")
    entities_schema = _load_schema("dsl-api-entities.v1.json")

    assert request_schema["$id"] == "https://kicad-agent-suite.local/schema/dsl-api-request.v1.json"
    assert result_schema["$id"] == "https://kicad-agent-suite.local/schema/dsl-api-result.v1.json"
    assert entities_schema["$id"] == "https://kicad-agent-suite.local/schema/dsl-api-entities.v1.json"

    assert request_schema["properties"]["schema_version"]["const"] == "dsl-api-request.v1"
    assert result_schema["properties"]["schema_version"]["const"] == "dsl-api-result.v1"

    assert "OperationRequest" not in entities_schema.get("$defs", {})
    assert "ValidationReport" in entities_schema["$defs"]
    assert "ApiError" in entities_schema["$defs"]
    assert "ModelSnapshot" in entities_schema["$defs"]


def test_dsl_api_request_operation_enum_covers_core_model_api():
    request_schema = _load_schema("dsl-api-request.v1.json")
    operations = request_schema["properties"]["operation"]["enum"]

    assert "add_component" in operations
    assert "connect_member" in operations
    assert "validate_model" in operations
    assert "compile_kicad_execution_plan" in operations
    assert "run_erc" in operations

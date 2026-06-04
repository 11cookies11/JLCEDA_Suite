"""Field-level contract metadata for major pipeline schemas."""

from __future__ import annotations

from .schema_versions import (
    KICAD_ERC_RESULT_SCHEMA_VERSION,
    KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
    KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION,
    PART_LOCK_SCHEMA_VERSION,
    SIMULATION_PLAN_SCHEMA_VERSION,
    SIMULATION_PROFILE_SCHEMA_VERSION,
    SIMULATION_TASK_PLAN_SCHEMA_VERSION,
    TEXT_TO_KICAD_SUMMARY_SCHEMA_VERSION,
)


SUMMARY_STABLE_FIELDS = ("files", "counts", "erc", "diagnostics", "postprocess", "warnings")

SCHEMA_FIELD_CONTRACTS = {
    KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION: {
        "stable": SUMMARY_STABLE_FIELDS,
    },
    KICAD_EXECUTION_PLAN_SCHEMA_VERSION: {
        "stable": ("request_id", "target", "symbols", "nets", "diagnostics"),
    },
    KICAD_ERC_RESULT_SCHEMA_VERSION: {
        "stable": ("enabled", "attempted", "success", "finding_count", "summary_file", "output_file", "error", "warnings"),
    },
    TEXT_TO_KICAD_SUMMARY_SCHEMA_VERSION: {
        "stable": ("output_files", "counts", "diagnostics"),
    },
    PART_LOCK_SCHEMA_VERSION: {
        "stable": ("project", "generated_at", "parts"),
    },
    SIMULATION_PROFILE_SCHEMA_VERSION: {
        "stable": ("profile_id", "project_id", "project_name", "topology", "default_backend", "preferred_analyses", "thresholds", "notes"),
    },
    SIMULATION_PLAN_SCHEMA_VERSION: {
        "stable": ("request_id", "project_id", "project_name", "topology", "source_profile", "scenarios", "summary", "recommendations"),
    },
    SIMULATION_TASK_PLAN_SCHEMA_VERSION: {
        "stable": ("request_id", "project_id", "project_name", "topology", "source_plan", "tasks", "summary", "recommendations"),
    },
}

CANONICAL_FIELD_CONTRACT_SCHEMAS = tuple(SCHEMA_FIELD_CONTRACTS.keys())

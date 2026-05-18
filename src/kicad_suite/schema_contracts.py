"""Field-level contract metadata for major pipeline schemas."""

from __future__ import annotations

from .schema_versions import (
    KICAD_ERC_RESULT_SCHEMA_VERSION,
    KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
    KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION,
    PART_LOCK_SCHEMA_VERSION,
    SIMULATION_PLAN_SCHEMA_VERSION,
    SIMULATION_PROFILE_SCHEMA_VERSION,
    TEXT_TO_KICAD_SUMMARY_SCHEMA_VERSION,
)


SUMMARY_STABLE_FIELDS = ("files", "counts", "erc", "diagnostics", "postprocess", "warnings")
SUMMARY_COMPAT_FIELDS = (
    "output_files",
    "project_file",
    "schematic_file",
    "summary_file",
    "execution_plan",
    "kicad_erc_summary",
    "kicad_erc_report",
)

SCHEMA_FIELD_CONTRACTS = {
    KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION: {
        "stable": SUMMARY_STABLE_FIELDS,
        "compat": SUMMARY_COMPAT_FIELDS,
    },
    KICAD_EXECUTION_PLAN_SCHEMA_VERSION: {
        "stable": ("request_id", "target", "symbols", "nets", "diagnostics"),
        "compat": ("schema_version",),
    },
    KICAD_ERC_RESULT_SCHEMA_VERSION: {
        "stable": ("enabled", "attempted", "success", "finding_count", "summary_file", "output_file", "error", "warnings"),
        "compat": ("schema_version", "return_code", "executable", "stdout", "stderr", "command"),
    },
    TEXT_TO_KICAD_SUMMARY_SCHEMA_VERSION: {
        "stable": ("output_files", "counts", "diagnostics"),
        "compat": ("schema_version", "request_id", "topology"),
    },
    PART_LOCK_SCHEMA_VERSION: {
        "stable": ("project", "generated_at", "parts"),
        "compat": ("schema_version",),
    },
    SIMULATION_PROFILE_SCHEMA_VERSION: {
        "stable": ("profile_id", "project_id", "project_name", "topology", "default_backend", "preferred_analyses", "thresholds", "notes"),
        "compat": ("schema_version", "tags"),
    },
    SIMULATION_PLAN_SCHEMA_VERSION: {
        "stable": ("request_id", "project_id", "project_name", "topology", "source_profile", "scenarios", "summary", "recommendations"),
        "compat": ("schema_version",),
    },
}

CANONICAL_FIELD_CONTRACT_SCHEMAS = tuple(SCHEMA_FIELD_CONTRACTS.keys())

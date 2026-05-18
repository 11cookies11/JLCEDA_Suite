"""Tests for field-level schema contracts."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.schema_contracts import (
    CANONICAL_FIELD_CONTRACT_SCHEMAS,
    SCHEMA_FIELD_CONTRACTS,
    SUMMARY_COMPAT_FIELDS,
    SUMMARY_STABLE_FIELDS,
)


class TestSchemaContracts(unittest.TestCase):
    def test_summary_contract_fields_are_stable(self) -> None:
        self.assertEqual(SUMMARY_STABLE_FIELDS, ("files", "counts", "erc", "diagnostics", "postprocess", "warnings"))
        self.assertIn("output_files", SUMMARY_COMPAT_FIELDS)
        self.assertIn("project_file", SUMMARY_COMPAT_FIELDS)
        self.assertIn("schematic_file", SUMMARY_COMPAT_FIELDS)

    def test_contracts_cover_canonical_schemas(self) -> None:
        self.assertEqual(len(CANONICAL_FIELD_CONTRACT_SCHEMAS), len(set(CANONICAL_FIELD_CONTRACT_SCHEMAS)))
        self.assertEqual(set(CANONICAL_FIELD_CONTRACT_SCHEMAS), set(SCHEMA_FIELD_CONTRACTS))

    def test_simulation_contracts_are_present(self) -> None:
        self.assertIn("simulation-profile.v1", SCHEMA_FIELD_CONTRACTS)
        self.assertIn("simulation-plan.v1", SCHEMA_FIELD_CONTRACTS)
        self.assertIn("simulation-task-plan.v1", SCHEMA_FIELD_CONTRACTS)
        self.assertIn("preferred_analyses", SCHEMA_FIELD_CONTRACTS["simulation-profile.v1"]["stable"])
        self.assertIn("scenarios", SCHEMA_FIELD_CONTRACTS["simulation-plan.v1"]["stable"])
        self.assertIn("tasks", SCHEMA_FIELD_CONTRACTS["simulation-task-plan.v1"]["stable"])


if __name__ == "__main__":
    unittest.main()

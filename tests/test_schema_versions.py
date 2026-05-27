"""Tests for canonical schema version constants."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.schema_versions import CANONICAL_SCHEMA_VERSIONS


class TestSchemaVersions(unittest.TestCase):
    def test_canonical_versions_are_unique(self) -> None:
        self.assertEqual(len(CANONICAL_SCHEMA_VERSIONS), len(set(CANONICAL_SCHEMA_VERSIONS)))

    def test_canonical_versions_include_current_pipeline_contracts(self) -> None:
        expected = {
            "requirement-spec.v1",
            "circuit-model.v1",
            "netlist.v1",
            "spice-netlist.v1",
            "ngspice-execution.v1",
            "ngspice-feedback.v1",
            "kicad-execution-plan.v1",
            "kicad-project-write-result.v1",
            "kicad-erc-result.v1",
            "text-to-kicad-summary.v1",
            "part-lock.v1",
            "simulation-profile.v1",
            "simulation-plan.v1",
            "simulation-task-plan.v1",
            "dsl-api-request.v1",
            "dsl-api-result.v1",
            "dsl-api-entities.v1",
        }
        self.assertEqual(set(CANONICAL_SCHEMA_VERSIONS), expected)


if __name__ == "__main__":
    unittest.main()

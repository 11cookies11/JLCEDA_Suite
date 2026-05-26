"""Tests for the example scaffold generator."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.example_scaffold import scaffold_example


class TestExampleScaffold(unittest.TestCase):
    def test_scaffold_creates_expected_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = scaffold_example("demo-board", title="Demo Board", root_dir=root)
            project_dir = root / "demo-board"

            self.assertTrue((project_dir / "README.md").exists())
            self.assertTrue((project_dir / "docs" / "00_requirements.md").exists())
            self.assertTrue((project_dir / "hardware" / "README.md").exists())
            self.assertTrue((project_dir / "software" / "README.md").exists())
            self.assertTrue((project_dir / "agent" / "review_rules.md").exists())
            self.assertIn(project_dir / "README.md", created)

    def test_scaffold_refuses_to_overwrite_existing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold_example("demo-board", title="Demo Board", root_dir=root)
            with self.assertRaises(FileExistsError):
                scaffold_example("demo-board", title="Demo Board", root_dir=root)

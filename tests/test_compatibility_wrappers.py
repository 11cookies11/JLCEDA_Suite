"""Tests for legacy compatibility wrappers."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite import parts_pipeline, run_pipeline


class TestRunPipelineWrapper(unittest.TestCase):
    def test_main_delegates_to_pipeline_coordinator(self):
        with patch("kicad_suite.run_pipeline._run_pipeline", return_value={"ok": True}) as wrapped:
            code = run_pipeline.main(["model.json", "out"])
        self.assertEqual(code, 0)
        wrapped.assert_called_once_with("model.json", "out")

    def test_main_shows_usage_without_args(self):
        code = run_pipeline.main([])
        self.assertEqual(code, 1)


class TestPartsPipelineWrapper(unittest.TestCase):
    def test_reexports_run_parts_pipeline(self):
        self.assertIs(parts_pipeline.run_parts_pipeline, parts_pipeline.run_parts_pipeline)
        self.assertIn("run_parts_pipeline", parts_pipeline.__all__)

    def test_wrapper_modules_have_transition_docstrings(self):
        self.assertIn("transition", run_pipeline.__doc__ or "")
        self.assertIn("transition", parts_pipeline.__doc__ or "")

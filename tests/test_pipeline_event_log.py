"""Tests for the pipeline event log."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.pipeline_event_log import append_pipeline_event, pipeline_event_log_path


class TestPipelineEventLog(unittest.TestCase):
    def test_append_pipeline_event_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            log_path = pipeline_event_log_path(output_dir)

            append_pipeline_event(log_path, "stage-a", "started", {"request_id": "req-1"})
            append_pipeline_event(log_path, "stage-b", "finished", {"ok": True})

            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)

            first = json.loads(lines[0])
            second = json.loads(lines[1])

            self.assertIn("timestamp", first)
            self.assertEqual(first["stage"], "stage-a")
            self.assertEqual(first["message"], "started")
            self.assertEqual(first["data"]["request_id"], "req-1")
            self.assertEqual(second["stage"], "stage-b")
            self.assertEqual(second["data"]["ok"], True)

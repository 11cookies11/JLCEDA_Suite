"""Compatibility wrapper for the parts workflow.

This is a transition path only. Prefer :mod:`kicad_suite.parts.workflow`
for new code paths.
"""

from .parts.workflow import run_parts_pipeline

__all__ = ["run_parts_pipeline"]

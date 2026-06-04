#!/usr/bin/env python3
"""Run the smallest guardrail test set for core functionality.

Use this before refactoring or deleting legacy code. It is intentionally
lightweight and focuses on the public entrypoints that should never break:
CLI parsing, compatibility wrappers, model API basics, parts workflow basics,
and the top-level pipeline wiring.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parent.parent
    tests = [str(repo_root / "tests" / "test_smoke_guardrails.py")]
    cmd = [sys.executable, "-m", "pytest", "-q", *tests, *args]
    completed = subprocess.run(cmd, cwd=repo_root, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kicad_suite.artifact_validator import validate_artifacts  # noqa: E402


if __name__ == "__main__":
    from kicad_suite.artifact_validator import main  # noqa: E402

    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from kicad_suite.run_pipeline import run_pipeline


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: run_pipeline.py <model.json> <output-dir>', file=sys.stderr)
        sys.exit(2)
    print(json.dumps(run_pipeline(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))

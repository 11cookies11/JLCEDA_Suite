#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from kicad_suite.server_eda_target import run


if __name__ == '__main__':
    run()


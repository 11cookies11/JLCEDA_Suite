#!/usr/bin/env python3
from __future__ import annotations

import sys

from server_text_to_kicad import run as run_kicad


def run() -> None:
    run_kicad()


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('KiCad pipeline failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)

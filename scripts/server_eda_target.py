#!/usr/bin/env python3
from __future__ import annotations

import sys

from env_utils import env, normalize_text


def run() -> None:
    target = normalize_text(env('EDA_TARGET', 'kicad')) or 'kicad'
    if target == 'kicad':
        from server_text_to_kicad import run as run_kicad

        run_kicad()
        return
    if target in {'jlceda', 'easyeda'}:
        from server_text_to_schematic import run as run_jlceda

        run_jlceda()
        return
    raise ValueError(f'Unsupported EDA_TARGET: {target}. Use kicad or jlceda.')


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('EDA target pipeline failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)

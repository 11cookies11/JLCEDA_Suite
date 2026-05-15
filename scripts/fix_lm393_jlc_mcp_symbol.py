"""Repair a JLC MCP LM393 symbol with the standard SOP-8 pinout.

Usage:
  python scripts/fix_lm393_jlc_mcp_symbol.py --project-dir .where/project --id C5252905
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _arg_value(name: str, default: str = "") -> str:
    for idx, arg in enumerate(sys.argv):
        if arg == name and idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return default


def main() -> None:
    project_dir = _arg_value("--project-dir")
    lcsc_id = _arg_value("--id", "C5252905")
    if not project_dir:
        print(__doc__.strip())
        sys.exit(2)

    corrections = {
        "pins": [
            {"action": "add", "number": "1", "name": "OUTA", "type": "open_collector"},
            {"action": "add", "number": "2", "name": "INA-", "type": "input"},
            {"action": "add", "number": "3", "name": "INA+", "type": "input"},
            {"action": "add", "number": "4", "name": "GND", "type": "power_in"},
            {"action": "add", "number": "5", "name": "INB+", "type": "input"},
            {"action": "add", "number": "6", "name": "INB-", "type": "input"},
            {"action": "add", "number": "7", "name": "OUTB", "type": "open_collector"},
            {"action": "add", "number": "8", "name": "VCC", "type": "power_in"},
        ],
    }

    bridge = Path(__file__).resolve().parent / "jlc_mcp_bridge.mjs"
    command = [
        "node",
        str(bridge),
        "fix",
        "--id",
        lcsc_id,
        "--project-path",
        project_dir,
        "--corrections-json",
        json.dumps(corrections, separators=(",", ":")),
        "--force",
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()

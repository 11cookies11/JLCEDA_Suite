#!/usr/bin/env python3
"""Generate a first-pass KiCad PCB from a KiCad Agent execution plan.

This script must run under KiCad's Python because it imports ``pcbnew``.
It creates a board containing all resolvable footprints and assigns pad nets
from the plan so KiCad can show ratsnest connections immediately.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pcbnew


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _footprint_library_dir(project_dir: Path, lib_name: str) -> Path | None:
    if lib_name == "JLC-MCP":
        return project_dir / "libraries" / "footprints" / "JLC-MCP.pretty"
    if lib_name == "AIAgent":
        return _repo_root() / "resources" / "kicad" / "footprints" / "AIAgent.pretty"
    return None


def _pin_tokens(pin_number: str) -> set[str]:
    text = str(pin_number).strip()
    if not text:
        return set()
    tokens = set(re.findall(r"[A-Za-z]+\d+|\d+", text))
    tokens.add(text)
    return tokens


def _pad_net_map(symbol: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pin in symbol.get("pins", []):
        if not isinstance(pin, dict):
            continue
        net = str(pin.get("net", "")).strip()
        if not net:
            continue
        for token in _pin_tokens(str(pin.get("number", ""))):
            mapping[token] = net
    return mapping


def _net(board: Any, nets: dict[str, Any], net_name: str) -> Any:
    if net_name not in nets:
        item = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(item)
        nets[net_name] = item
    return nets[net_name]


def generate_board(plan_path: Path, output_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    project_dir = output_path.parent
    board = pcbnew.BOARD()
    nets: dict[str, Any] = {}
    loaded = 0
    skipped: list[str] = []

    for index, symbol in enumerate(plan.get("symbols", [])):
        if not isinstance(symbol, dict):
            continue
        ref = str(symbol.get("ref", "")).strip()
        footprint = str(symbol.get("footprint", "")).strip()
        if not ref or ":" not in footprint:
            skipped.append(f"{ref or '<unknown>'}: no footprint")
            continue
        lib_name, footprint_name = footprint.split(":", 1)
        lib_dir = _footprint_library_dir(project_dir, lib_name)
        if lib_dir is None or not lib_dir.exists():
            skipped.append(f"{ref}: footprint library not found: {footprint}")
            continue
        fp = pcbnew.FootprintLoad(str(lib_dir), footprint_name)
        if fp is None:
            skipped.append(f"{ref}: footprint not found: {footprint}")
            continue

        fp.SetReference(ref)
        fp.SetValue(str(symbol.get("value", "")))
        at = symbol.get("at", {}) if isinstance(symbol.get("at"), dict) else {}
        x_mm = float(at.get("x", 0.0)) + (index % 8) * 6.0
        y_mm = float(at.get("y", 0.0)) + (index // 8) * 6.0
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
        fp.SetOrientationDegrees(float(at.get("rotation", 0.0)))

        pad_map = _pad_net_map(symbol)
        for pad in fp.Pads():
            net_name = pad_map.get(str(pad.GetNumber()).strip())
            if net_name:
                pad.SetNet(_net(board, nets, net_name))
        board.Add(fp)
        loaded += 1

    board.BuildListOfNets()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)
    return {
        "board": str(output_path),
        "footprints": loaded,
        "nets": len(nets),
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("board", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate_board(args.plan, args.board), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI entry point for KiCad Library Importer.

Usage:
  python scripts/import_parts.py --selections selections.json --project-dir ./my-project
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.part_selector import SelectedPart
from kicad_suite.kicad_lib_importer import import_parts


def run() -> None:
    selections_file = ""
    project_dir = ""
    easyeda2kicad_bin = ""

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--selections" and i + 1 < len(sys.argv):
            selections_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--project-dir" and i + 1 < len(sys.argv):
            project_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--easyeda2kicad-bin" and i + 1 < len(sys.argv):
            easyeda2kicad_bin = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    if not selections_file or not project_dir:
        print("Usage: python scripts/import_parts.py --selections selections.json --project-dir ./project [--easyeda2kicad-bin /path/to/easyeda2kicad]")
        sys.exit(2)

    with open(selections_file, encoding="utf-8") as f:
        data = json.load(f)

    parts: list[SelectedPart] = []
    for item in data:
        if item.get("selected") is None:
            continue
        s = item["selected"]
        parts.append(SelectedPart(
            requirement_id=item["requirement_id"],
            lcsc_id=s.get("lcsc_id", ""),
            mpn=s.get("mpn", ""),
            manufacturer=s.get("manufacturer", ""),
            package=s.get("package", ""),
            description=s.get("description", ""),
            price=s.get("price"),
            stock=s.get("stock", 0),
            basic_or_extended=s.get("basic_or_extended", ""),
            has_easyeda_symbol=s.get("has_easyeda_symbol", False),
            has_easyeda_footprint=s.get("has_easyeda_footprint", False),
            has_3d_model=s.get("has_3d_model", False),
            source=s.get("source", ""),
            confidence=s.get("confidence", 0.0),
            composite_score=s.get("composite_score", 0.0),
            reasons=s.get("reasons", []),
            risks=[],
            needs_review=s.get("needs_review", False),
        ))

    if not parts:
        print("No selected parts found in input file.")
        sys.exit(0)

    result = import_parts(
        parts,
        project_dir,
        easyeda2kicad_bin=easyeda2kicad_bin,
    )

    output = {
        "imported_count": result.imported_count,
        "skipped_count": result.skipped_count,
        "failed_lcsc_ids": result.failed_lcsc_ids,
        "symbol_lib_file": result.symbol_lib_file,
        "footprint_lib_dir": result.footprint_lib_dir,
        "model_dir": result.model_dir,
        "lock_file": result.lock_file,
        "risk_report_file": result.risk_report_file,
        "warnings": result.warnings,
        "errors": result.errors,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()

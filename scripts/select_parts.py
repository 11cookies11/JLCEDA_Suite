"""CLI entry point for Part Selector — resolve + select in one pass.

Usage:
  python scripts/select_parts.py                         # runs built-in demo
  python scripts/select_parts.py --json requirements.json  # batch from file
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.lcsc_resolver import PartRequirement, resolve_many, McpHttpBackend
from kicad_suite.part_selector import select_parts

DEMO_REQUIREMENTS = [
    PartRequirement(
        id="power_ldo",
        function="3.3V LDO regulator",
        preferred_mpn=["AMS1117-3.3"],
        package_preferred=["SOT-223"],
        output_voltage=3.3,
        assembly="JLCPCB",
        price_max=0.50,
    ),
    PartRequirement(
        id="decoupling_cap",
        function="100nF decoupling capacitor",
        package_preferred=["0603"],
        assembly="JLCPCB",
    ),
    PartRequirement(
        id="main_mcu",
        function="STM32F103C8T6 microcontroller",
        preferred_mpn=["STM32F103C8T6"],
        package_preferred=["LQFP-48"],
        assembly="JLCPCB",
        price_max=3.00,
    ),
    PartRequirement(
        id="usb_esd",
        function="USB ESD protection diode",
        package_preferred=["SOT-23"],
        assembly="JLCPCB",
    ),
]


def run_demo() -> None:
    print("=" * 70)
    print("Part Selector — Demo")
    print("=" * 70)

    backend = McpHttpBackend()
    resolver_results = resolve_many(DEMO_REQUIREMENTS, backend=backend)
    selections = select_parts(DEMO_REQUIREMENTS, resolver_results)

    for sel in selections:
        print(f"\n{sel.summary}")
        if sel.selected:
            for reason in sel.selected.reasons:
                print(f"   + {reason}")
            if sel.selected.risks:
                for risk in sel.selected.risks:
                    print(f"   ! ({risk.level}) {risk.message}")
        print(f"   Total candidates scored: {len(sel.all_candidates)}")


def run_from_file(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    requirements = [PartRequirement(**item) for item in data["requirements"]]

    backend = McpHttpBackend()
    resolver_results = resolve_many(requirements, backend=backend)
    selections = select_parts(requirements, resolver_results)

    output = []
    for sel in selections:
        entry: dict = {
            "requirement_id": sel.requirement_id,
            "summary": sel.summary,
            "selected": None,
            "all_candidates": [],
        }
        if sel.selected:
            entry["selected"] = {
                "lcsc_id": sel.selected.lcsc_id,
                "mpn": sel.selected.mpn,
                "manufacturer": sel.selected.manufacturer,
                "package": sel.selected.package,
                "price": sel.selected.price,
                "stock": sel.selected.stock,
                "composite_score": sel.selected.composite_score,
                "needs_review": sel.selected.needs_review,
                "reasons": sel.selected.reasons,
                "risks": [{"category": r.category, "message": r.message, "level": r.level} for r in sel.selected.risks],
            }
        for c in sel.all_candidates:
            entry["all_candidates"].append({
                "mpn": c.mpn,
                "lcsc_id": c.lcsc_id,
                "package": c.package,
                "composite_score": c.composite_score,
                "needs_review": c.needs_review,
            })
        output.append(entry)

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--json":
        run_from_file(sys.argv[2])
    else:
        run_demo()

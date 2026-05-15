"""CLI entry point for LCSC Resolver — test or batch resolve parts.

Usage:
  python scripts/resolve_parts.py                         # runs built-in demo
  python scripts/resolve_parts.py --json requirements.json  # batch from file
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.lcsc_resolver import PartRequirement, resolve_many


DEMO_REQUIREMENTS = [
    PartRequirement(
        id="power_ldo",
        function="3.3V LDO regulator",
        preferred_mpn=["AMS1117-3.3"],
        package_preferred=["SOT-223"],
        current_min=500,
    ),
    PartRequirement(
        id="decoupling_cap",
        function="100nF decoupling capacitor",
        package_preferred=["0603"],
    ),
    PartRequirement(
        id="main_mcu",
        function="STM32F103C8T6 microcontroller",
        preferred_mpn=["STM32F103C8T6"],
        package_preferred=["LQFP-48"],
    ),
    PartRequirement(
        id="usb_esd",
        function="USB ESD protection diode",
        package_preferred=["SOT-23"],
    ),
]


def run_demo() -> None:
    print("=" * 70)
    print("LCSC Resolver — Demo")
    print("=" * 70)
    for result in resolve_many(DEMO_REQUIREMENTS):
        print(f"\n--- {result.id} ({result.query_context['category_inferred']}) ---")
        print(f"    queries: {len(result.query_context['queries'])}")
        for c in result.candidates:
            stock_str = str(c.stock) if c.stock else "-"
            basic_str = c.basic_or_extended or "-"
            print(f"  [{c.confidence:.2f}] {c.mpn[:45]:45s} {c.package[:22]:22s} stock={stock_str:>6s} {basic_str:>8s}  {c.source}")
        if not result.candidates:
            print("  (no results)")


def run_from_file(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    requirements = [PartRequirement(**item) for item in data["requirements"]]
    results = resolve_many(requirements)
    output = [{"id": r.id, "candidates": [c.__dict__ for c in r.candidates], "query_context": r.query_context} for r in results]
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--json":
        run_from_file(sys.argv[2])
    else:
        run_demo()

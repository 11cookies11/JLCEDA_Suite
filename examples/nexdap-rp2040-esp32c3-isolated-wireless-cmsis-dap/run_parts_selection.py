"""NexDAP parts selection — resolve + select with correct MCP bridge path."""
from __future__ import annotations

import json, sys, os
from pathlib import Path

# Add repo src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kicad_suite.lcsc_resolver import (
    PartRequirement,
    JlcMcpCliBackend,
    resolve_many,
)
from kicad_suite.part_selector import select_parts

# Fix the bridge script path (parents[3] = repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = REPO_ROOT / "scripts" / "jlc_mcp_bridge.mjs"

PROJECT_DIR = Path(__file__).resolve().parent
REQUIREMENTS_FILE = PROJECT_DIR / "part.requirements.resolver.json"


def main():
    # Load requirements
    with open(REQUIREMENTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    requirements = [PartRequirement(**item) for item in data["requirements"]]
    print(f"Loaded {len(requirements)} requirements")
    print(f"Bridge script: {BRIDGE_SCRIPT} (exists={BRIDGE_SCRIPT.exists()})")
    print()

    # Resolve
    backend = JlcMcpCliBackend(bridge_script=str(BRIDGE_SCRIPT), timeout=30.0)
    print(f"Backend configured: {backend.configured}")
    print("Resolving parts from LCSC...")
    resolver_results = resolve_many(requirements, backend=backend)
    print(f"Resolved {len(resolver_results)} requirement(s)")
    print()

    # Select
    print("Selecting best parts...")
    selections = select_parts(requirements, resolver_results)
    print(f"Selected {len(selections)} part(s)")
    print()

    # Build output
    output = []
    summary_lines = []
    for sel in selections:
        entry: dict = {
            "requirement_id": sel.requirement_id,
            "summary": sel.summary,
            "selected": None,
            "all_candidates": [],
        }
        if sel.selected:
            s = sel.selected
            entry["selected"] = {
                "lcsc_id": s.lcsc_id,
                "mpn": s.mpn,
                "manufacturer": s.manufacturer,
                "package": s.package,
                "description": s.description,
                "price": s.price,
                "stock": s.stock,
                "basic_or_extended": s.basic_or_extended,
                "has_easyeda_symbol": s.has_easyeda_symbol,
                "has_easyeda_footprint": s.has_easyeda_footprint,
                "has_3d_model": s.has_3d_model,
                "source": s.source,
                "confidence": s.confidence,
                "composite_score": s.composite_score,
                "needs_review": s.needs_review,
                "reasons": s.reasons,
                "risks": [{"category": r.category, "message": r.message, "level": r.level} for r in s.risks],
            }
            status = "NEEDS REVIEW" if s.needs_review else "OK"
            summary_lines.append(
                f"  [{status}] {sel.requirement_id:30s} -> {s.mpn:25s} {s.lcsc_id:14s} "
                f"score={s.composite_score} stock={s.stock} price={s.price}"
            )
        else:
            summary_lines.append(f"  [NO SELECTION] {sel.requirement_id}")
            entry["selected"] = None

        for c in sel.all_candidates:
            entry["all_candidates"].append({
                "mpn": c.mpn,
                "lcsc_id": c.lcsc_id,
                "package": c.package,
                "price": c.price,
                "stock": c.stock,
                "basic_or_extended": c.basic_or_extended,
                "composite_score": c.composite_score,
                "needs_review": c.needs_review,
            })
        output.append(entry)

    # Print summary
    print("=" * 120)
    print("SELECTION SUMMARY")
    print("=" * 120)
    for line in summary_lines:
        print(line)
    print()

    # Write results
    output_path = PROJECT_DIR / "part-selection-results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Results written to: {output_path}")

    # Print details for each selected part
    for entry in output:
        sel = entry["selected"]
        if not sel:
            print(f"\n--- {entry['requirement_id']}: NO PART SELECTED ---")
            continue
        print(f"\n--- {entry['requirement_id']}: {sel['mpn']} ({sel['lcsc_id']}) ---")
        print(f"  Package: {sel['package']}")
        print(f"  Manufacturer: {sel['manufacturer']}")
        print(f"  Description: {sel['description']}")
        print(f"  Price: {sel['price']}, Stock: {sel['stock']}, Type: {sel['basic_or_extended']}")
        print(f"  Score: {sel['composite_score']}/100, Confidence: {sel['confidence']}")
        print(f"  EasyEDA: sym={sel['has_easyeda_symbol']} fp={sel['has_easyeda_footprint']} 3d={sel['has_3d_model']}")
        print(f"  Needs review: {sel['needs_review']}")
        if sel['reasons']:
            for r in sel['reasons']:
                print(f"    + {r}")
        if sel['risks']:
            for r in sel['risks']:
                print(f"    ! [{r['level']}] {r['category']}: {r['message']}")


if __name__ == "__main__":
    main()

"""End-to-end demo: circuit-model.json → KiCad files + part.lock.yaml + risk report.

Uses the existing circuit model examples and runs the full pipeline
including the integrated Parts Pipeline.

Usage:
  python scripts/demo_e2e_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Enable parts pipeline
os.environ["KICAD_PARTS_PIPELINE"] = "true"

from kicad_suite.run_pipeline import run_pipeline
from kicad_suite.parts.workflow import run_parts_pipeline


def main():
    repo = Path(__file__).resolve().parents[1]

    # Use the ESP32-C3 example
    model_file = repo / "examples" / "esp32-c3-bare-minimal-devboard.circuit-model.json"
    if not model_file.exists():
        print(f"Model file not found: {model_file}")
        sys.exit(1)

    output_dir = repo / ".where" / "demo-e2e-output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  End-to-End Pipeline Demo")
    print(f"  Model: {model_file.name}")
    print(f"  Output: {output_dir}")
    print("=" * 70)

    # Step 1: Run the existing KiCad pipeline
    print("\n[1/3] Running KiCad pipeline (circuit-model → KiCad files)...")
    print(f"       Environment: KICAD_PARTS_PIPELINE=true")
    try:
        result = run_pipeline(str(model_file), str(output_dir))
        print(f"       Schematic: {result['files'].get('schematic', '(failed)')}")
        print(f"       Project:   {result['files'].get('project', '(failed)')}")
        if result['files'].get('part_lock'):
            print(f"       Part Lock: {result['files']['part_lock']}")
        if result['files'].get('part_risk_report'):
            print(f"       Risk Rpt:  {result['files']['part_risk_report']}")
    except Exception as exc:
        print(f"       Pipeline failed: {exc}")

    # Step 2: Run parts pipeline standalone (with richer output)
    print("\n[2/3] Running Parts Pipeline standalone...")
    model = json.loads(model_file.read_text(encoding="utf-8"))
    parts_result = run_parts_pipeline(
        model,
        output_dir,
        project_name=model.get("topology", "demo-project"),
        run_importer=False,  # easyeda2kicad may not be installed
    )

    if parts_result.get("warning"):
        print(f"       Warning: {parts_result['warning']}")
    elif parts_result.get("summary"):
        s = parts_result["summary"]
        print(f"       Components: {s['total_components']}")
        print(f"       Resolved:   {s['resolved_parts']}")
        print(f"       Low Risk:   {s['low_risk']}")
        print(f"       Med Risk:   {s['medium_risk']}")
        print(f"       High Risk:  {s['high_risk']}")
        print(f"       Review:     {s['needs_review']}")
    elif parts_result.get("error"):
        print(f"       Error: {parts_result['error']}")

    # Step 3: Show output files
    print("\n[3/3] Output files:")
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"       {f.relative_to(output_dir)} ({size}B)")

    # Print the part.lock.yaml if it exists
    lock_file = output_dir / "part.lock.yaml"
    if lock_file.exists():
        print("\n" + "=" * 70)
        print("  part.lock.yaml")
        print("=" * 70)
        print(lock_file.read_text(encoding="utf-8")[:2000])

    report_file = output_dir / "part-risk-report.md"
    if report_file.exists():
        print("\n" + "=" * 70)
        print("  part-risk-report.md")
        print("=" * 70)
        print(report_file.read_text(encoding="utf-8")[:2000])

    print("\nDone.")


if __name__ == "__main__":
    main()

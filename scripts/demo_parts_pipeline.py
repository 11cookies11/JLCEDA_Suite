"""End-to-end demo: Part Selector + part.lock.yaml + risk report.

Uses realistic mock LCSC results to demonstrate the full pipeline
without requiring the MCP backend or easyeda2kicad.

Usage:
  python scripts/demo_parts_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.lcsc_resolver import PartRequirement, ResolvedPart, ResolverResult
from kicad_suite.part_selector import select_parts
from kicad_suite.kicad_lib_importer import (
    import_parts,
    _build_lock_data,
    _build_risk_report,
    _yaml_dumps,
)

# ---------------------------------------------------------------------------
# Realistic mock LCSC search results simulating what the MCP backend returns
# ---------------------------------------------------------------------------


def _make_candidate(lcsc_id, mpn, manufacturer, package, stock, basic, description,
                    symbol=True, footprint=True, model3d=True, price=None, source="jlcpcb_parts", confidence=0.85):
    return ResolvedPart(
        lcsc_id=lcsc_id, mpn=mpn, manufacturer=manufacturer,
        package=package, description=description, stock=stock,
        basic_or_extended=basic, price=price,
        has_easyeda_symbol=symbol, has_easyeda_footprint=footprint,
        has_3d_model=model3d, source=source, confidence=confidence,
    )


# Simulated requirements and search results — like what LCSC Resolver returns
REQUIREMENTS = [
    PartRequirement(
        id="main_mcu",
        function="ESP32-C3-WROOM-02 module",
        preferred_mpn=["ESP32-C3-WROOM-02"],
        package_preferred=[],
        assembly="JLCPCB",
        price_max=3.00,
    ),
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
        id="boot_pullup",
        function="10k pull-up resistor",
        preferred_mpn=[],
        package_preferred=["0603"],
        assembly="JLCPCB",
    ),
    PartRequirement(
        id="decoupling_cap",
        function="100nF decoupling capacitor",
        preferred_mpn=[],
        package_preferred=["0603"],
        assembly="JLCPCB",
    ),
    PartRequirement(
        id="usb_connector",
        function="USB-C 16pin connector",
        preferred_mpn=["TYPE-C-16P"],
        package_preferred=[],
        assembly="JLCPCB",
    ),
    PartRequirement(
        id="crystal_40m",
        function="40MHz crystal oscillator",
        preferred_mpn=[],
        package_preferred=["3225"],
        assembly="JLCPCB",
        price_max=0.80,
    ),
]

# Mock resolver results — simulating what the MCP backend would return
RESOLVER_RESULTS = [
    ResolverResult(id="main_mcu", candidates=[
        _make_candidate("C100001", "ESP32-C3-WROOM-02", "Espressif", "SMD Module",
                        8500, "Basic", "ESP32-C3 WiFi/BLE module, 4MB flash",
                        price=2.50, confidence=0.93),
        _make_candidate("C100002", "ESP32-C3-WROOM-02-N4", "Espressif", "SMD Module",
                        6000, "Basic", "ESP32-C3 module, 4MB flash, PCB antenna",
                        price=2.45, confidence=0.90),
    ], query_context={}),
    ResolverResult(id="power_ldo", candidates=[
        _make_candidate("C2040", "AMS1117-3.3", "AMS", "SOT-223",
                        12000, "Basic", "3.3V 1A LDO regulator",
                        price=0.12, confidence=0.95),
        _make_candidate("C61861", "AMS1117-3.3", "AMS", "SOT-89",
                        8000, "Basic", "3.3V 1A LDO regulator",
                        price=0.10, confidence=0.82),
        _make_candidate("C427196", "ME6203A33M3G", "MicrOne", "SOT-23-3",
                        5000, "Basic", "3.3V 500mA LDO",
                        price=0.06, confidence=0.70),
    ], query_context={}),
    ResolverResult(id="boot_pullup", candidates=[
        _make_candidate("C25804", "RC0603JR-0710KL", "Yageo", "0603",
                        50000, "Basic", "10k 5% 0603 thick film resistor",
                        model3d=False, price=0.008, confidence=0.94),
        _make_candidate("C139776", "0603WAF1002T5E", "UniOhm", "0603",
                        45000, "Basic", "10k 1% 0603 thick film resistor",
                        model3d=False, price=0.006, confidence=0.90),
    ], query_context={}),
    ResolverResult(id="decoupling_cap", candidates=[
        _make_candidate("C1500", "CL10B104KB8NNNC", "Samsung", "0603",
                        80000, "Basic", "100nF 50V X7R 0603 MLCC",
                        model3d=False, price=0.015, confidence=0.92),
        _make_candidate("C1710", "CC0603KRX7R9BB104", "Yageo", "0603",
                        60000, "Basic", "100nF 50V X7R 0603 MLCC",
                        model3d=False, price=0.012, confidence=0.88),
    ], query_context={}),
    ResolverResult(id="usb_connector", candidates=[
        _make_candidate("C88888", "TYPE-C-16P-Female", "JRC", "USB-C 16P",
                        3000, "Extended", "USB-C 16pin female, SMD, 1.6mm PCB",
                        price=0.35, confidence=0.82),
        _make_candidate("C77777", "UJ31-CH-3-SMT-TR", "CUI Devices", "USB-C 16P",
                        2500, "Basic", "USB-C 3.1, 16pin, SMD, horizontal",
                        price=0.52, confidence=0.85),
    ], query_context={}),
    ResolverResult(id="crystal_40m", candidates=[
        _make_candidate("C90001", "X322540MMB4SI", "YXC", "3225",
                        15000, "Basic", "40MHz 10ppm 12pF 3225 SMD crystal",
                        model3d=False, price=0.25, confidence=0.91),
    ], query_context={}),
]


# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 70)
    print("  Part Selector + part.lock.yaml Demo")
    print("  项目: esp32-c3-minimal-devboard")
    print("=" * 70)

    # Step 1: Run Part Selector
    print("\n[1/3] Part Selector — 从候选器件中选择最优...\n")
    selections = select_parts(REQUIREMENTS, RESOLVER_RESULTS)

    for sel in selections:
        if sel.selected:
            risk = "REVIEW" if sel.selected.needs_review else "OK"
            print(f"  {sel.selected.requirement_id:20s} → "
                  f"{sel.selected.mpn:30s} "
                  f"{sel.selected.package:12s} "
                  f"score={sel.selected.composite_score:.0f}/100 "
                  f"[{risk}]")
            for reason in sel.selected.reasons:
                print(f"    + {reason}")
            if sel.selected.risks:
                for r in sel.selected.risks:
                    print(f"    ! ({r.level}) {r.message}")
        else:
            print(f"  {sel.requirement_id:20s} → (no acceptable part)")
    print()

    # Step 2: Generate part.lock.yaml
    print("[2/3] 生成 part.lock.yaml ...\n")
    selected_parts = [s.selected for s in selections if s.selected]

    # Enrich with realistic data
    for i, part in enumerate(selected_parts):
        if part.requirement_id == "boot_pullup":
            part.note = ""
        elif part.requirement_id == "usb_connector":
            part.note = "需要检查外壳焊盘和定位孔位置"
        elif part.requirement_id == "main_mcu":
            part.note = "模块边缘焊盘需要人工核对间距"

    lock_data = _build_lock_data(selected_parts, [], {}, project_name="esp32-c3-minimal-devboard")
    lock_yaml = _yaml_dumps(lock_data)
    print(lock_yaml)

    # Step 3: Generate risk report
    print("[3/3] 生成 part-risk-report.md ...\n")
    report = _build_risk_report(selected_parts)
    print(report)

    # Write output files
    output_dir = Path(tempfile.mkdtemp(prefix="demo_parts_"))
    (output_dir / "part.lock.yaml").write_text(lock_yaml + "\n", encoding="utf-8")
    (output_dir / "part-risk-report.md").write_text(report, encoding="utf-8")

    print("=" * 70)
    print(f"  输出文件已写入: {output_dir}")
    print(f"    {output_dir / 'part.lock.yaml'}")
    print(f"    {output_dir / 'part-risk-report.md'}")
    print("=" * 70)


if __name__ == "__main__":
    run()

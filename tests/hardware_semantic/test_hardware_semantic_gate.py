from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hardware_semantic_gate.py"


def write_project(tmp_path: Path, model: dict) -> Path:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    (source / "circuit-model.source.json").write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp_path


def run_gate(project: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--project", str(project), "--no-fail"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout
    return json.loads((project / "build" / "hardware-erc.v1.json").read_text(encoding="utf-8"))


def blocker_codes(report: dict) -> set[str]:
    return {item["code"] for item in report.get("blockers", [])}


def test_tps22918_requires_vin_and_vout(tmp_path: Path) -> None:
    project = write_project(tmp_path, {
        "schema_version": "circuit-model.v1",
        "project_id": "bad-load-switch",
        "topology": "bad_load_switch",
        "components": [
            {"ref": "U9", "role": "mic_power_switch", "value": "TPS22918DBVR"}
        ],
        "nets": [
            {"name": "GND", "kind": "ground", "members": ["U9.2"]},
            {"name": "MIC_PWR_EN", "kind": "signal", "members": ["U9.3", "U1.10"]}
        ]
    })
    report = run_gate(project)
    codes = blocker_codes(report)
    assert "LOAD_SWITCH_REQUIRED_PIN_UNRESOLVED" in codes


def test_load_switch_vout_capacitor_only_is_not_real_load(tmp_path: Path) -> None:
    project = write_project(tmp_path, {
        "schema_version": "circuit-model.v1",
        "project_id": "load-switch-cap-only",
        "topology": "load_switch_cap_only",
        "components": [
            {"ref": "U9", "role": "mic_power_switch", "value": "TPS22918DBVR"},
            {"ref": "C9", "role": "switched_rail_decoupling", "value": "1uF capacitor"}
        ],
        "nets": [
            {"name": "GND", "kind": "ground", "members": ["U9.2", "C9.2"]},
            {"name": "VBAT", "kind": "power", "members": ["U9.1"]},
            {"name": "MIC_PWR_EN", "kind": "signal", "members": ["U9.3", "U1.10"]},
            {"name": "MIC_VDD_SW", "kind": "power", "members": ["U9.6", "C9.1"]}
        ]
    })
    report = run_gate(project)
    codes = blocker_codes(report)
    assert "LOAD_SWITCH_OUTPUT_WITHOUT_LOAD" in codes


def test_usb_c_sink_requires_cc_rd(tmp_path: Path) -> None:
    project = write_project(tmp_path, {
        "schema_version": "circuit-model.v1",
        "project_id": "bad-usbc",
        "topology": "bad_usbc",
        "components": [
            {"ref": "J1", "role": "usb_c_power_input", "value": "TYPE-C-16P"}
        ],
        "nets": [
            {"name": "USB_5V", "kind": "power", "members": ["J1.A4", "J1.A9", "J1.B4", "J1.B9"]},
            {"name": "GND", "kind": "ground", "members": ["J1.A1", "J1.A12", "J1.B1", "J1.B12"]},
            {"name": "USB_D_P", "kind": "signal", "members": ["J1.A6", "J1.B6"]},
            {"name": "USB_D_N", "kind": "signal", "members": ["J1.A7", "J1.B7"]},
            {"name": "CC1", "kind": "signal", "members": ["J1.A5"]},
            {"name": "CC2", "kind": "signal", "members": ["J1.B5"]}
        ]
    })
    report = run_gate(project)
    codes = blocker_codes(report)
    assert "USB_C_CC_MISSING_RD" in codes


def test_bq24074_requires_program_pins(tmp_path: Path) -> None:
    project = write_project(tmp_path, {
        "schema_version": "circuit-model.v1",
        "project_id": "bad-charger",
        "topology": "bad_charger",
        "components": [
            {"ref": "U3", "role": "liion_charger_power_path", "value": "BQ24074"},
            {"ref": "BT1", "role": "battery", "value": "1S LiPo"}
        ],
        "nets": [
            {"name": "USB_5V", "kind": "power", "members": ["U3.13"]},
            {"name": "BAT+", "kind": "power", "members": ["U3.2", "BT1.1"]},
            {"name": "VSYS", "kind": "power", "members": ["U3.10"]},
            {"name": "GND", "kind": "ground", "members": ["U3.8", "BT1.2"]}
        ]
    })
    report = run_gate(project)
    codes = blocker_codes(report)
    assert "CHARGER_REQUIRED_PIN_UNRESOLVED" in codes
    assert "CHARGER_BAT_DUPLICATE_PIN_MISSING" in codes
    assert "CHARGER_OUT_DUPLICATE_PIN_MISSING" in codes

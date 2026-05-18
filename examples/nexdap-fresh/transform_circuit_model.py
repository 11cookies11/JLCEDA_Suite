"""Transform circuit-model.json from RP2040-main to ESP32-C3FH4X-main architecture."""
from __future__ import annotations

import json
import copy
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / "circuit-model.json"


def load_model() -> dict:
    with open(MODEL_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_model(model: dict) -> None:
    with open(MODEL_PATH, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Saved: {MODEL_PATH}")


def transform(model: dict) -> dict:
    # --- 1. Top-level metadata ---
    model["topology"] = "esp32c3_managed_rp2040_swd_coprocessor"
    model["project_id"] = "nexdap-esp32c3-managed-rp2040-swd-coprocessor"
    model["request_id"] = "nexdap-esp32c3-managed-rp2040-swd-coprocessor-v1"

    components = model["components"]
    nets = model["nets"]

    # --- 2. Component index ---
    comp_by_ref = {c["ref"]: c for c in components}

    # --- 3. Modify existing components ---
    comp_by_ref["U_ESP32"]["role"] = "esp32c3_host_controller"
    comp_by_ref["U_ESP32"]["value"] = "ESP32-C3FH4X"
    comp_by_ref["U_ESP32"]["notes"] = (
        "ESP32-C3FH4X with in-package 4MB flash. "
        "Host-facing USB on GPIO18/19. "
        "Pins 19-24 not available externally (embedded flash bus)."
    )

    comp_by_ref["U_RP2040"]["role"] = "rp2040_swd_timing_coprocessor"
    comp_by_ref["U_RP2040"]["notes"] = (
        "Managed by ESP32-C3FH4X via SWD (GPIO2=SWDIO, GPIO5=SWCLK) and RUN (GPIO3). "
        "Communicates over SPI for command/response. "
        "No direct USB connection to host."
    )

    # --- 4. Remove old components ---
    remove_refs = {"SW_RP_RST", "SW_RP_BOOT", "R_BOOT_PD", "R_TGT_TX", "R_TGT_RX"}
    components[:] = [c for c in components if c["ref"] not in remove_refs]

    # --- 5. Add new components ---
    # Find insertion points
    insert_after = {}  # ref -> index of component to insert after
    for i, c in enumerate(components):
        insert_after[c["ref"]] = i

    new_components = [
        {
            "ref": "SW_ESP_RST",
            "role": "esp32_reset_button",
            "value": "TK-6580S-2",
        },
        {
            "ref": "SW_ESP_BOOT",
            "role": "esp32_boot_button",
            "value": "TK-6580S-2",
        },
        {
            "ref": "Q_RP_BOOTSEL",
            "role": "rp2040_bootsel_open_drain_pulldown",
            "value": "2N7002",
        },
        {
            "ref": "R_RP_BOOTSEL_GATE",
            "role": "rp2040_bootsel_gate_resistor",
            "value": "100R",
        },
        {
            "ref": "R_RP_BOOTSEL_PD",
            "role": "rp2040_bootsel_gate_pulldown",
            "value": "100k",
        },
        {
            "ref": "JP_TGT_PWR",
            "role": "target_power_enable_jumper",
            "value": "2P-Jumper",
        },
    ]

    # Insert SW_ESP_RST and SW_ESP_BOOT after R_ESP_GPIO2
    idx = insert_after["R_ESP_GPIO2"]
    for comp in reversed([new_components[0], new_components[1]]):
        components.insert(idx + 1, comp)

    # Rebuild index after insertion
    for i, c in enumerate(components):
        insert_after[c["ref"]] = i

    # Insert Q_RP_BOOTSEL, R_RP_BOOTSEL_GATE, R_RP_BOOTSEL_PD after Q_NRST
    idx = insert_after["Q_NRST"]
    for comp in reversed([new_components[2], new_components[3], new_components[4]]):
        components.insert(idx + 1, comp)

    # Rebuild index
    for i, c in enumerate(components):
        insert_after[c["ref"]] = i

    # Insert JP_TGT_PWR after F_TGT
    idx = insert_after["F_TGT"]
    components.insert(idx + 1, new_components[5])

    # --- 6. Net index ---
    net_by_name = {n["name"]: n for n in nets}

    # --- 7. Remove old nets ---
    remove_nets = {
        "ESP_GPIO2",
        "ESP_UART1_TX",
        "ESP_UART1_RX",
        "TGT_UART_TX",
        "TGT_UART_RX",
        "TGT_UART_TX_OUT",
        "TGT_UART_RX_OUT",
    }
    nets[:] = [n for n in nets if n["name"] not in remove_nets]
    # Rebuild index
    net_by_name = {n["name"]: n for n in nets}

    # --- 8. Modify existing nets ---

    # USB_DP: U_RP2040.47 -> U_ESP32.26
    usb_dp = net_by_name["USB_DP"]
    usb_dp["members"] = [m for m in usb_dp["members"] if m != "U_RP2040.47"]
    usb_dp["members"].append("U_ESP32.26")

    # USB_DM: U_RP2040.46 -> U_ESP32.25
    usb_dm = net_by_name["USB_DM"]
    usb_dm["members"] = [m for m in usb_dm["members"] if m != "U_RP2040.47"]
    usb_dm["members"].append("U_ESP32.25")

    # ESP_TO_RP_IRQ: U_ESP32.25 -> U_ESP32.27
    irq1 = net_by_name["ESP_TO_RP_IRQ"]
    irq1["members"] = ["U_ESP32.27" if m == "U_ESP32.25" else m for m in irq1["members"]]

    # RP_TO_ESP_IRQ: U_ESP32.26 -> U_ESP32.28
    irq2 = net_by_name["RP_TO_ESP_IRQ"]
    irq2["members"] = ["U_ESP32.28" if m == "U_ESP32.26" else m for m in irq2["members"]]

    # ESP_RP_RUN_CTRL: remove SW_RP_RST pins
    run_ctrl = net_by_name["ESP_RP_RUN_CTRL"]
    run_ctrl["members"] = [m for m in run_ctrl["members"] if not m.startswith("SW_RP_RST")]

    # RP_BOOTSEL_QSPI_SS: remove SW_RP_BOOT + R_BOOT_PD; add Q_RP_BOOTSEL.3
    bootsel = net_by_name["RP_BOOTSEL_QSPI_SS"]
    bootsel["members"] = [m for m in bootsel["members"]
                          if not (m.startswith("SW_RP_BOOT") or m.startswith("R_BOOT_PD"))]
    bootsel["members"].append("Q_RP_BOOTSEL.3")

    # HOST_SWCLK -> ESP_RP_SWCLK: add U_ESP32.9
    swclk = net_by_name["HOST_SWCLK"]
    swclk["name"] = "ESP_RP_SWCLK"
    swclk["members"].append("U_ESP32.9")
    net_by_name = {n["name"]: n for n in nets}  # rebuild after rename

    # HOST_SWDIO -> ESP_RP_SWDIO: add U_ESP32.6 + R_ESP_GPIO2.2
    swdio = net_by_name["HOST_SWDIO"]
    swdio["name"] = "ESP_RP_SWDIO"
    swdio["members"].extend(["U_ESP32.6", "R_ESP_GPIO2.2"])
    net_by_name = {n["name"]: n for n in nets}  # rebuild after rename

    # VTREF_TARGET: U_RP2040.43 -> U_ESP32.6
    vtref = net_by_name["VTREF_TARGET"]
    vtref["members"] = ["U_ESP32.6" if m == "U_RP2040.43" else m for m in vtref["members"]]

    # ESP_CHIP_EN: add SW_ESP_RST signal pins
    chip_en = net_by_name["ESP_CHIP_EN"]
    chip_en["members"].extend(["SW_ESP_RST.1", "SW_ESP_RST.2", "SW_ESP_RST.3"])

    # ESP_GPIO9_BOOT: add SW_ESP_BOOT signal pins
    gpio9 = net_by_name["ESP_GPIO9_BOOT"]
    gpio9["members"].extend(["SW_ESP_BOOT.1", "SW_ESP_BOOT.2", "SW_ESP_BOOT.3"])

    # +5V_SW_TGT: add JP_TGT_PWR pins
    tgt_pwr = net_by_name["+5V_SW_TGT"]
    tgt_pwr["members"].extend(["JP_TGT_PWR.1", "JP_TGT_PWR.2"])
    tgt_pwr["kind"] = "power"

    # GND_HOST: remove old button/pulldown GND, add new ones
    gnd = net_by_name["GND_HOST"]
    gnd["members"] = [m for m in gnd["members"]
                      if not (m.startswith("SW_RP_RST.") or
                              m.startswith("SW_RP_BOOT.") or
                              m.startswith("R_BOOT_PD.") or
                              m == "SW_ESP_RST.2")]  # SW_ESP_RST.2 now on CHIP_EN, not GND
    gnd["members"].extend([
        "Q_RP_BOOTSEL.2",       # 2N7002 source
        "R_RP_BOOTSEL_PD.2",    # gate pulldown to GND
        "SW_ESP_RST.4", "SW_ESP_RST.5", "SW_ESP_RST.6",   # GND side of reset button
        "SW_ESP_BOOT.4", "SW_ESP_BOOT.5", "SW_ESP_BOOT.6", # GND side of boot button
    ])

    # --- 9. Add new nets ---
    new_nets = [
        {
            "name": "ESP_RP_BOOTSEL_CTRL",
            "kind": "signal",
            "members": [
                "R_RP_BOOTSEL_GATE.1",
            ],
            "_note": "ESP32 GPIO reserved for optional BOOTSEL control. Currently unused (all GPIOs consumed on FH4X). NMOS gate held low by 100k pulldown.",
        },
        {
            "name": "RP_BOOTSEL_GATE",
            "kind": "signal",
            "members": [
                "R_RP_BOOTSEL_GATE.2",
                "Q_RP_BOOTSEL.1",
                "R_RP_BOOTSEL_PD.1",
            ],
        },
    ]

    # Insert new nets before GND_HOST
    gnd_idx = next(i for i, n in enumerate(nets) if n["name"] == "GND_HOST")
    for net in reversed(new_nets):
        nets.insert(gnd_idx, net)

    # --- 10. Replace design_decisions ---
    model["design_decisions"] = [
        "ESP32-C3FH4X is the only host-facing controller providing USB, Wi-Fi, BLE, and TCP services.",
        "RP2040 does not expose USB directly to the host.",
        "USB-C D+/D- are connected to ESP32-C3 native USB pins GPIO19/GPIO18 instead of RP2040.",
        "RP2040 acts as a deterministic SWD timing coprocessor managed by ESP32-C3 over SPI (commands) and SWD (firmware management).",
        "SPI is the primary command/response channel between ESP32-C3 and RP2040 during normal operation.",
        "ESP32-C3 provides an internal SWD maintenance interface to RP2040: GPIO2=SWDIO, GPIO5=SWCLK, GPIO3=RUN.",
        "The internal ESP32-to-RP2040 SWD interface is used for first-time RP2040 programming, firmware recovery and low-level diagnostics.",
        "ESP32-C3 does not share or drive the RP2040 external QSPI Flash bus.",
        "RP2040 BOOTSEL may be controlled by an NMOS open-drain circuit (Q_RP_BOOTSEL). ESP32 control GPIO is reserved for future use.",
        "RP2040 manual BOOTSEL and RESET buttons are removed.",
        "ESP32-C3 has its own BOOT (GPIO9) and RESET (CHIP_EN) buttons for host-side maintenance.",
        "Target 5V output has a jumper (JP_TGT_PWR) to avoid conflict with self-powered target boards.",
        "VTREF is measured by ESP32-C3 ADC1_CH2 (GPIO2), shared with the RP2040 SWDIO line. ADC read only when SWD is idle.",
        "All target-facing protection retained: 22R series on SWDIO/SWCLK/SWO/nRESET, SRV05-4 ESD, 2N7002 open-drain nRESET.",
        "Target connector uses a 2x4 2.54mm header; pins 7/8 are unconnected (UART removed as FH4X has no external GPIO14/16).",
        "200mA PTC fuse on target 5V output prevents short-circuit damage.",
        "LED indicators: PWR=Green, DAP=Blue, TGT=Red.",
    ]

    return model


def validate(model: dict) -> list[str]:
    """Validate the transformed model for consistency."""
    issues = []
    components = model["components"]
    nets = model["nets"]

    comp_refs = {c["ref"] for c in components}

    # Check all net members reference existing components
    for net in nets:
        for member in net["members"]:
            if "." in member:
                ref = member.split(".")[0]
                if ref not in comp_refs:
                    issues.append(f"Net '{net['name']}': member '{member}' references unknown component '{ref}'")

    # Check no pin appears in multiple nets (except intentional U_ESP32.6)
    pin_to_nets: dict[str, list[str]] = {}
    for net in nets:
        for member in net["members"]:
            pin_to_nets.setdefault(member, []).append(net["name"])

    for pin, net_names in pin_to_nets.items():
        if len(net_names) > 1:
            if pin == "U_ESP32.6" and set(net_names) == {"ESP_RP_SWDIO", "VTREF_TARGET"}:
                continue  # Intentional: VTREF DC measurement on SWDIO line
            issues.append(f"Pin conflict: {pin} appears in nets: {net_names}")

    # Check FH4X unavailable pins (19, 24) are not used
    for net in nets:
        for member in net["members"]:
            if member.startswith("U_ESP32."):
                pin = member.split(".")[1]
                if pin in ("19", "24"):
                    issues.append(f"ESP32-C3FH4X pin {pin} not available (embedded flash): used in net '{net['name']}'")

    # Check no duplicate net names
    net_names = [n["name"] for n in nets]
    dupes = [name for name in set(net_names) if net_names.count(name) > 1]
    for name in dupes:
        issues.append(f"Duplicate net name: '{name}'")

    return issues


def main():
    model = load_model()

    # Backup original
    bak_path = MODEL_PATH.with_suffix(".json.bak")
    with open(bak_path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Backup saved: {bak_path}")

    model = transform(model)

    issues = validate(model)
    if issues:
        print("\n=== VALIDATION ISSUES ===")
        for issue in issues:
            print(f"  ! {issue}")
        print()
    else:
        print("\n=== Validation passed ===")

    save_model(model)

    # Print stats
    comps = model["components"]
    nets = model["nets"]
    print(f"Components: {len(comps)}")
    print(f"Nets: {len(nets)}")
    print(f"ESP32 GPIOs used: ", end="")
    esp32_pins = set()
    for net in nets:
        for m in net["members"]:
            if m.startswith("U_ESP32."):
                esp32_pins.add(m.split(".")[1])
    print(sorted(esp32_pins, key=lambda x: (0, int(x)) if x.isdigit() else (1, x)))


if __name__ == "__main__":
    main()

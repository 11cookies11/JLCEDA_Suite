#!/usr/bin/env python3
"""Simulation profile and plan generation for circuit models."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .circuit_model_io import load_dual_circuit_model
from ...shared.schema_versions import SIMULATION_PLAN_SCHEMA_VERSION, SIMULATION_PROFILE_SCHEMA_VERSION
from ...shared.schema_versions import SIMULATION_TASK_PLAN_SCHEMA_VERSION


@dataclass
class SimulationProfileSource:
    schema_version: str
    profile_id: str


@dataclass
class SimulationThresholds:
    vout_min_v: float = 0.0
    vout_max_v: float = 0.0
    ripple_max_mv: float = 0.0
    startup_overshoot_percent: float = 0.0
    startup_settle_ms: float = 0.0


@dataclass
class SimulationProfile:
    schema_version: str
    profile_id: str
    project_id: str
    project_name: str
    topology: str
    default_backend: str = "ngspice"
    preferred_analyses: list[str] = field(default_factory=lambda: ["op", "tran"])
    tags: list[str] = field(default_factory=list)
    thresholds: SimulationThresholds = field(default_factory=SimulationThresholds)
    notes: list[str] = field(default_factory=list)


@dataclass
class SimulationScenario:
    scenario_id: str
    title: str
    backend: str
    analysis_kind: str
    focus: str
    focus_components: list[str] = field(default_factory=list)
    focus_nets: list[str] = field(default_factory=list)
    stimuli: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SimulationPlan:
    schema_version: str
    request_id: str
    project_id: str
    project_name: str
    topology: str
    source_profile: SimulationProfileSource
    scenarios: list[SimulationScenario]
    summary: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class NgspiceTaskSourcePlan:
    schema_version: str
    request_id: str


@dataclass
class NgspiceTask:
    task_id: str
    scenario_id: str
    title: str
    backend: str
    analysis_kind: str
    command: list[str]
    netlist_path: str
    log_path: str
    execution_file: str
    feedback_file: str
    focus_components: list[str] = field(default_factory=list)
    focus_nets: list[str] = field(default_factory=list)
    stimuli: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class NgspiceTaskPlan:
    schema_version: str
    request_id: str
    project_id: str
    project_name: str
    topology: str
    source_plan: NgspiceTaskSourcePlan
    tasks: list[NgspiceTask]
    summary: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_circuit_model(path: Path) -> dict[str, Any]:
    return load_dual_circuit_model(path)


def load_simulation_profile(path: Path | None) -> SimulationProfile | None:
    if path is None:
        return None
    payload = _load_json_file(path)
    thresholds = payload.get("thresholds", {})
    return SimulationProfile(
        schema_version=str(payload.get("schema_version", SIMULATION_PROFILE_SCHEMA_VERSION)),
        profile_id=str(payload.get("profile_id", "default-profile")),
        project_id=str(payload.get("project_id", "")),
        project_name=str(payload.get("project_name", "")),
        topology=str(payload.get("topology", "")),
        default_backend=str(payload.get("default_backend", "ngspice")),
        preferred_analyses=[str(item) for item in payload.get("preferred_analyses", ["op", "tran"])],
        tags=[str(item) for item in payload.get("tags", [])],
        thresholds=SimulationThresholds(
            vout_min_v=float(thresholds.get("vout_min_v", 0.0) or 0.0),
            vout_max_v=float(thresholds.get("vout_max_v", 0.0) or 0.0),
            ripple_max_mv=float(thresholds.get("ripple_max_mv", 0.0) or 0.0),
            startup_overshoot_percent=float(thresholds.get("startup_overshoot_percent", 0.0) or 0.0),
            startup_settle_ms=float(thresholds.get("startup_settle_ms", 0.0) or 0.0),
        ),
        notes=[str(item) for item in payload.get("notes", [])],
    )


def default_simulation_profile(model: dict[str, Any]) -> SimulationProfile:
    project_name = _normalize_text(model.get("topology") or model.get("project_id") or model.get("request_id"))
    project_id = _normalize_text(model.get("project_id") or model.get("request_id") or project_name)
    return SimulationProfile(
        schema_version=SIMULATION_PROFILE_SCHEMA_VERSION,
        profile_id=f"{project_name or project_id}-profile",
        project_id=project_id or "simulation-project",
        project_name=project_name or "simulation-project",
        topology=_normalize_text(model.get("topology", "")),
        tags=["auto", "from-circuit-model"],
    )


def _component_roles(model: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for component in model.get("components", []):
        if isinstance(component, dict):
            role = _normalize_text(component.get("role", ""))
            if role:
                roles.append(role)
    return roles


def _net_names(model: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for net in model.get("nets", []):
        if isinstance(net, dict):
            name = _normalize_text(net.get("name", ""))
            if name:
                names.append(name)
    return names


def _has_role(roles: list[str], *needles: str) -> bool:
    lowered = [role.lower() for role in roles]
    return any(any(needle.lower() in role for needle in needles) for role in lowered)


def _find_refs(model: dict[str, Any], *needles: str) -> list[str]:
    refs: list[str] = []
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        role = _normalize_text(component.get("role", "")).lower()
        ref = _normalize_text(component.get("ref", ""))
        if ref and any(needle.lower() in role for needle in needles):
            refs.append(ref)
    return refs


def _find_refs_exact(model: dict[str, Any], *roles: str) -> list[str]:
    wanted = {role.lower() for role in roles}
    refs: list[str] = []
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        role = _normalize_text(component.get("role", "")).lower()
        ref = _normalize_text(component.get("ref", ""))
        if ref and role in wanted:
            refs.append(ref)
    return refs


def _power_net_names(net_names: list[str]) -> list[str]:
    matches: list[str] = []
    for net_name in net_names:
        upper = net_name.upper()
        if upper.startswith("+") or any(token in upper for token in ("VCC", "VDD", "VIN", "VOUT", "VBUS", "3V3", "5V")):
            matches.append(net_name)
    return matches


def _nets_with_tokens(net_names: list[str], *tokens: str) -> list[str]:
    matches: list[str] = []
    lowered_tokens = [token.lower() for token in tokens]
    for net_name in net_names:
        lowered = net_name.lower()
        if any(token in lowered for token in lowered_tokens):
            matches.append(net_name)
    return matches


def infer_simulation_scenarios(model: dict[str, Any], profile: SimulationProfile) -> list[SimulationScenario]:
    roles = _component_roles(model)
    net_names = _net_names(model)
    scenarios: list[SimulationScenario] = []
    primary_power_nets = _power_net_names(net_names)

    if _has_role(roles, "buck", "regulator", "ldo", "power"):
        scenarios.append(
            SimulationScenario(
                scenario_id="power-startup",
                title="Power startup check",
                backend=profile.default_backend,
                analysis_kind=profile.preferred_analyses[1] if len(profile.preferred_analyses) > 1 else "tran",
                focus="Validate power rail startup and regulation.",
                focus_components=_find_refs(model, "main_3v3_buck", "buck_", "vcc_3v3_bulk_capacitor"),
                focus_nets=primary_power_nets[:6],
                stimuli=["Input supply sweep", "Load step"],
                success_criteria=[
                    "Primary rail reaches nominal voltage.",
                    "Startup does not overshoot excessively.",
                    "Output remains stable under a modest load step.",
                ],
                notes=["Prefer a vendor model when the regulator is a switching IC."],
            )
        )

    if _has_role(roles, "usb", "vbus", "cc", "esd", "tvs"):
        scenarios.append(
            SimulationScenario(
                scenario_id="usb-input-protection",
                title="USB input protection check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Confirm VBUS protection and idle biasing.",
                focus_components=_find_refs(model, "usb_c_input", "usb_c_cc1_sink_rd", "usb_c_cc2_sink_rd", "usb_cc1_pulldown", "usb_cc2_pulldown", "usb_esd_protection", "usb_vbus_ptc_fuse", "usb_vbus_tvs_diode"),
                focus_nets=_nets_with_tokens(net_names, "USB_VBUS", "USB_DP", "USB_DM", "USB_CC", "USB_C_CC"),
                stimuli=["Apply nominal VBUS", "Observe clamp and fuse behavior"],
                success_criteria=[
                    "Normal VBUS is not clamped under nominal conditions.",
                    "Protection parts do not distort the rail during idle bias.",
                ],
                notes=["Use DC operating point first; transient only if the model supports it."],
            )
        )

    if _has_role(roles, "esp32", "esp_", "chip_en", "boot", "strap", "xtal"):
        scenarios.append(
            SimulationScenario(
                scenario_id="esp32-startup-and-strap",
                title="ESP32 startup and strap check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Check ESP32 reset, boot, strap, clock, and supply bias states at power-up.",
                focus_components=_find_refs(
                    model,
                    "esp32c3_host_controller",
                    "esp_chip_en_pullup",
                    "esp_en_reset_capacitor",
                    "esp_gpio9_boot_pullup",
                    "esp_gpio8_strap_pullup",
                    "esp_gpio2_strap_pullup",
                    "esp32_reset_button",
                    "esp32_boot_button",
                    "esp32_40mhz_crystal",
                    "esp_xtal_load_cap_1",
                    "esp_xtal_load_cap_2",
                    "esp_vdda_decoupling",
                    "esp_vdd3p3_decoupling_1",
                    "esp_vdd3p3_decoupling_2",
                    "esp_vdd3p3_bulk",
                ),
                focus_nets=_nets_with_tokens(net_names, "ESP_CHIP_EN", "ESP_GPIO9_BOOT", "ESP_GPIO8", "ESP_GPIO2", "ESP_XTAL", "+3V3_MAIN"),
                stimuli=["Power applied at nominal input", "Observe strap sampling window", "Check crystal bias and decoupling"],
                success_criteria=[
                    "Reset remains asserted long enough during startup.",
                    "Boot strap pins settle to the intended logic state.",
                    "Crystal and decoupling nets bias correctly at startup.",
                ],
                notes=["This is a functional check, not a full timing-accuracy proof."],
            )
        )

    if _has_role(roles, "rp2040", "rp_", "bootsel", "run_pullup", "qspi", "swd", "uart"):
        scenarios.append(
            SimulationScenario(
                scenario_id="rp2040-debug-and-bootsel",
                title="RP2040 debug and BOOTSEL check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Check RP2040 boot selection, SWD access, and low-speed bias paths.",
                focus_components=_find_refs(
                    model,
                    "rp2040_target_swd_uart_coprocessor",
                    "rp2040_qspi_flash",
                    "rp2040_run_pullup",
                    "rp2040_12mhz_crystal",
                    "rp_xtal_load_cap_1",
                    "rp_xtal_load_cap_2",
                    "rp_vdd_decoupling_1",
                    "rp_dvdd_decoupling",
                    "rp_vdd_bulk",
                    "vtref_adc_filter_cap",
                    "vtref_adc_divider_top",
                    "vtref_adc_divider_bottom",
                    "nreset_open_drain_nmos",
                    "rp2040_bootsel_open_drain_pulldown",
                    "rp2040_bootsel_gate_resistor",
                    "rp2040_bootsel_gate_pulldown",
                    "nreset_target_pullup",
                    "swdio_protection_resistor",
                    "swclk_protection_resistor",
                    "swo_protection_resistor",
                    "nreset_protection_resistor",
                    "tgt_uart_tx_series_resistor",
                    "tgt_uart_rx_series_resistor",
                ),
                focus_nets=_nets_with_tokens(net_names, "RP_BOOTSEL", "SWDIO", "SWCLK", "RUN", "VTREF", "UART", "QSPI"),
                stimuli=["Power applied at nominal input", "Observe boot selection and SWD bias", "Measure VTREF divider behavior"],
                success_criteria=[
                    "BOOTSEL control remains in the intended default state.",
                    "SWD and reset bias networks settle cleanly.",
                    "VTREF sensing path produces a stable reference voltage.",
                ],
                notes=["This check is aimed at low-speed control and debug paths, not firmware execution."],
            )
        )

    if _has_role(roles, "target_power_enable_jumper", "target_vbus_ptc_fuse", "target_power_led", "target_led_resistor", "target_swd_connector", "target_esd_protection"):
        scenarios.append(
            SimulationScenario(
                scenario_id="target-power-path",
                title="Target power path check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Validate target power enable, fuse, and indicator biasing.",
                focus_components=_find_refs(
                    model,
                    "target_power_enable_jumper",
                    "target_vbus_ptc_fuse",
                    "target_power_led",
                    "target_led_resistor",
                    "target_swd_connector",
                    "target_esd_protection",
                    "nreset_target_pullup",
                ),
                focus_nets=_nets_with_tokens(net_names, "+5V_TGT", "+5V_SW_TGT", "TGT", "TARGET"),
                stimuli=["Enable target power", "Apply nominal target load"],
                success_criteria=[
                    "Target power switch path delivers the expected rail.",
                    "Fuse and indicator paths do not disturb the rail at nominal load.",
                    "Target power can be isolated when the jumper is open.",
                ],
                notes=["Useful to detect power-path regressions before full board bring-up."],
            )
        )

    if _has_role(roles, "led", "indicator"):
        scenarios.append(
            SimulationScenario(
                scenario_id="indicator-current",
                title="Indicator current check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Verify LED bias current and resistor sizing.",
                focus_components=_find_refs(model, "power_indicator_led", "power_led_resistor", "dap_activity_led", "dap_led_resistor", "target_power_led", "target_led_resistor"),
                focus_nets=_nets_with_tokens(net_names, "LED_PWR", "LED_DAP", "LED_TGT"),
                stimuli=["DC operating point"],
                success_criteria=[
                    "LED current stays within the target range.",
                    "Series resistor dissipation is safe.",
                ],
                notes=["Useful as a quick sanity check for visible indicators."],
            )
        )

    if _has_role(roles, "rf", "antenna", "flash", "uart", "swd", "spi", "qspi", "vtref", "nreset"):
        scenarios.append(
            SimulationScenario(
                scenario_id="interface-bias",
                title="Interface bias and coupling check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Validate interface biasing, VTREF sensing, and basic connectivity.",
                focus_components=_find_refs(
                    model,
                    "vtref_adc_filter_cap",
                    "vtref_adc_divider_top",
                    "vtref_adc_divider_bottom",
                    "swdio_protection_resistor",
                    "swclk_protection_resistor",
                    "swo_protection_resistor",
                    "nreset_protection_resistor",
                    "target_swd_connector",
                    "tgt_uart_tx_series_resistor",
                    "tgt_uart_rx_series_resistor",
                    "rf_series_matching_inductor",
                    "rf_shunt_matching_cap",
                    "chip_antenna_2g4",
                ),
                focus_nets=_nets_with_tokens(net_names, "VTREF", "SWD", "UART", "SPI", "QSPI", "RF"),
                stimuli=["DC operating point"],
                success_criteria=[
                    "Interface bias nets sit at intended levels.",
                    "No obvious floating interface supply is detected.",
                    "VTREF sensing remains stable across the interface network.",
                ],
                notes=["This is a lightweight pre-check, not a high-frequency RF simulation."],
            )
        )

    if not scenarios:
        scenarios.append(
            SimulationScenario(
                scenario_id="baseline-op",
                title="Baseline operating-point check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Run a minimal DC sanity check.",
                focus_components=[_normalize_text(component.get("ref", "")) for component in model.get("components", []) if isinstance(component, dict)][:6],
                focus_nets=net_names[:6],
                stimuli=["DC operating point"],
                success_criteria=[
                    "Model produces a stable operating point.",
                ],
                notes=["Used when the model has not yet been classified into a more specific scenario."],
            )
        )

    return scenarios


def build_simulation_plan(model: dict[str, Any], profile: SimulationProfile | None = None) -> SimulationPlan:
    active_profile = profile or default_simulation_profile(model)
    scenarios = infer_simulation_scenarios(model, active_profile)
    project_id = _normalize_text(model.get("project_id") or active_profile.project_id or model.get("request_id"))
    project_name = _normalize_text(model.get("topology") or active_profile.project_name or project_id)
    plan = SimulationPlan(
        schema_version=SIMULATION_PLAN_SCHEMA_VERSION,
        request_id=_normalize_text(model.get("request_id") or active_profile.profile_id or project_name),
        project_id=project_id or "simulation-project",
        project_name=project_name or "simulation-project",
        topology=_normalize_text(model.get("topology", "")),
        source_profile=SimulationProfileSource(
            schema_version=active_profile.schema_version,
            profile_id=active_profile.profile_id,
        ),
        scenarios=scenarios,
        summary={
            "scenario_count": len(scenarios),
            "analysis_kinds": sorted({scenario.analysis_kind for scenario in scenarios}),
            "backend": active_profile.default_backend,
        },
        recommendations=[
            "Start with the baseline operating-point check.",
            "Prefer transient analysis for startup behavior and DC operating point for bias checks.",
        ],
    )
    return plan


def _scenario_to_task(plan: SimulationPlan, scenario: SimulationScenario, output_dir: Path) -> NgspiceTask:
    task_root = output_dir / "ngspice-tasks" / scenario.scenario_id
    netlist_path = task_root / "netlist.cir"
    log_path = task_root / "ngspice.log"
    execution_file = task_root / "ngspice-execution.json"
    feedback_file = task_root / "ngspice-feedback.json"
    command = ["ngspice", "-b", str(netlist_path), "-o", str(log_path)]
    return NgspiceTask(
        task_id=f"{plan.request_id}:{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        title=scenario.title,
        backend=scenario.backend,
        analysis_kind=scenario.analysis_kind,
        command=command,
        netlist_path=str(netlist_path),
        log_path=str(log_path),
        execution_file=str(execution_file),
        feedback_file=str(feedback_file),
        focus_components=list(scenario.focus_components),
        focus_nets=list(scenario.focus_nets),
        stimuli=list(scenario.stimuli),
        success_criteria=list(scenario.success_criteria),
        notes=list(scenario.notes),
    )


def build_ngspice_task_plan(
    model: dict[str, Any],
    *,
    profile: SimulationProfile | None = None,
    plan: SimulationPlan | None = None,
    output_dir: Path | None = None,
) -> NgspiceTaskPlan:
    active_profile = profile or default_simulation_profile(model)
    active_plan = plan or build_simulation_plan(model, active_profile)
    task_output_dir = output_dir or Path(".")
    tasks = [_scenario_to_task(active_plan, scenario, task_output_dir) for scenario in active_plan.scenarios]
    return NgspiceTaskPlan(
        schema_version=SIMULATION_TASK_PLAN_SCHEMA_VERSION,
        request_id=active_plan.request_id,
        project_id=active_plan.project_id,
        project_name=active_plan.project_name,
        topology=active_plan.topology,
        source_plan=NgspiceTaskSourcePlan(
            schema_version=active_plan.schema_version,
            request_id=active_plan.request_id,
        ),
        tasks=tasks,
        summary={
            "task_count": len(tasks),
            "scenario_count": len(active_plan.scenarios),
            "analysis_kinds": sorted({task.analysis_kind for task in tasks}),
            "backends": sorted({task.backend for task in tasks}),
        },
        recommendations=[
            "Execute startup and power-path tasks first.",
            "Use op tasks to validate bias before transient-driven startup checks.",
        ],
    )


def simulation_profile_to_dict(profile: SimulationProfile) -> dict[str, Any]:
    return asdict(profile)


def simulation_plan_to_dict(plan: SimulationPlan) -> dict[str, Any]:
    return asdict(plan)


def ngspice_task_plan_to_dict(plan: NgspiceTaskPlan) -> dict[str, Any]:
    return asdict(plan)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_simulation_artifacts(model: dict[str, Any], output_dir: Path, profile: SimulationProfile | None = None) -> dict[str, Any]:
    active_profile = profile or default_simulation_profile(model)
    plan = build_simulation_plan(model, active_profile)
    task_plan = build_ngspice_task_plan(model, profile=active_profile, plan=plan, output_dir=output_dir)
    profile_file = output_dir / "simulation-profile.json"
    plan_file = output_dir / "simulation-plan.json"
    task_plan_file = output_dir / "simulation-task-plan.json"
    write_json(profile_file, simulation_profile_to_dict(active_profile))
    write_json(plan_file, simulation_plan_to_dict(plan))
    write_json(task_plan_file, ngspice_task_plan_to_dict(task_plan))
    return {
        "profile_file": str(profile_file),
        "plan_file": str(plan_file),
        "task_plan_file": str(task_plan_file),
        "profile": simulation_profile_to_dict(active_profile),
        "plan": simulation_plan_to_dict(plan),
        "task_plan": ngspice_task_plan_to_dict(task_plan),
    }


def _print_json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 1:
        print("Usage: python simulation_planner.py <circuit-model.json> [simulation-profile.json]", file=sys.stderr)
        return 1
    model = load_circuit_model(Path(args[0]))
    profile = load_simulation_profile(Path(args[1])) if len(args) > 1 else None
    plan = build_simulation_plan(model, profile)
    return _print_json(simulation_plan_to_dict(plan))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Simulation profile and plan generation for circuit models."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .schema_versions import SIMULATION_PLAN_SCHEMA_VERSION, SIMULATION_PROFILE_SCHEMA_VERSION


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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_circuit_model(path: Path) -> dict[str, Any]:
    return _load_json_file(path)


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


def _power_net_names(net_names: list[str]) -> list[str]:
    matches: list[str] = []
    for net_name in net_names:
        upper = net_name.upper()
        if upper.startswith("+") or any(token in upper for token in ("VCC", "VDD", "VIN", "VOUT", "VBUS", "3V3", "5V")):
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
                focus_components=_find_refs(model, "buck", "regulator", "ldo", "power"),
                focus_nets=primary_power_nets[:4],
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
                focus_components=_find_refs(model, "usb", "vbus", "esd", "tvs", "fuse"),
                focus_nets=[name for name in net_names if "USB" in name.upper() or "VBUS" in name.upper()][:4],
                stimuli=["Apply nominal VBUS", "Observe clamp and fuse behavior"],
                success_criteria=[
                    "Normal VBUS is not clamped under nominal conditions.",
                    "Protection parts do not distort the rail during idle bias.",
                ],
                notes=["Use DC operating point first; transient only if the model supports it."],
            )
        )

    if _has_role(roles, "reset", "boot", "strap", "enable", "en", "run", "vref"):
        scenarios.append(
            SimulationScenario(
                scenario_id="boot-and-strap",
                title="Boot and strap state check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Check reset, boot, strap, and reference states at power-up.",
                focus_components=_find_refs(model, "reset", "boot", "strap", "enable", "vref"),
                focus_nets=[name for name in net_names if any(token in name.upper() for token in ("RESET", "BOOT", "STRAP", "VTREF", "EN"))][:6],
                stimuli=["Power applied at nominal input", "Observe strap sampling window"],
                success_criteria=[
                    "Reset remains asserted long enough during startup.",
                    "Strap pins settle to the intended logic state.",
                    "Reference voltage is present before interface use.",
                ],
                notes=["This is a functional check, not a full timing-accuracy proof."],
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
                focus_components=_find_refs(model, "led", "indicator", "current_limit_resistor"),
                focus_nets=[name for name in net_names if "LED" in name.upper() or "PWR" in name.upper()][:4],
                stimuli=["DC operating point"],
                success_criteria=[
                    "LED current stays within the target range.",
                    "Series resistor dissipation is safe.",
                ],
                notes=["Useful as a quick sanity check for visible indicators."],
            )
        )

    if _has_role(roles, "rf", "antenna", "flash", "uart", "swd", "spi", "qspi"):
        scenarios.append(
            SimulationScenario(
                scenario_id="interface-bias",
                title="Interface bias and coupling check",
                backend=profile.default_backend,
                analysis_kind="op",
                focus="Validate interface biasing and basic connectivity.",
                focus_components=_find_refs(model, "rf", "antenna", "flash", "uart", "swd", "spi", "qspi"),
                focus_nets=[name for name in net_names if any(token in name.upper() for token in ("UART", "SWD", "SPI", "QSPI", "RF"))][:6],
                stimuli=["DC operating point"],
                success_criteria=[
                    "Interface bias nets sit at intended levels.",
                    "No obvious floating interface supply is detected.",
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


def simulation_profile_to_dict(profile: SimulationProfile) -> dict[str, Any]:
    return asdict(profile)


def simulation_plan_to_dict(plan: SimulationPlan) -> dict[str, Any]:
    return asdict(plan)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_simulation_artifacts(model: dict[str, Any], output_dir: Path, profile: SimulationProfile | None = None) -> dict[str, Any]:
    active_profile = profile or default_simulation_profile(model)
    plan = build_simulation_plan(model, active_profile)
    profile_file = output_dir / "simulation-profile.json"
    plan_file = output_dir / "simulation-plan.json"
    write_json(profile_file, simulation_profile_to_dict(active_profile))
    write_json(plan_file, simulation_plan_to_dict(plan))
    return {
        "profile_file": str(profile_file),
        "plan_file": str(plan_file),
        "profile": simulation_profile_to_dict(active_profile),
        "plan": simulation_plan_to_dict(plan),
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

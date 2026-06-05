#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import textwrap
from copy import deepcopy
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape


GRID_MM = 1
DEFAULT_ROLES_PATH = Path(__file__).resolve().parents[1] / "examples" / "layout-lab" / "roles.json"
DEFAULT_PATTERNS_PATH = Path(__file__).resolve().parents[1] / "examples" / "layout-lab" / "patterns.json"
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "examples" / "layout-lab" / "rules.json"


@dataclass
class LayoutLabRules:
    pattern_colors: dict[str, str] = field(default_factory=dict)
    role_defaults: dict[str, str] = field(default_factory=dict)
    role_slot_preferences: dict[str, list[str]] = field(default_factory=dict)
    cluster_slot_order: list[str] = field(default_factory=list)
    board_defaults: dict[str, int] = field(default_factory=dict)
    templates: dict[str, dict[str, Any]] = field(default_factory=dict)


DEFAULT_RULES = LayoutLabRules(
    pattern_colors={
        "center_cluster": "#8b5cf6",
        "boot_reset_cluster": "#a855f7",
        "clock_ring": "#6d28d9",
        "power_entry_chain": "#1d4ed8",
        "power_chain": "#2563eb",
        "signal_chain": "#0f766e",
        "usb_interface_chain": "#0284c7",
        "high_current_path": "#ea580c",
        "edge_connector": "#dc2626",
        "indicator_cluster": "#16a34a",
        "analog_island": "#7c3aed",
        "rf_keepout_island": "#db2777",
        "rf_island": "#be185d",
        "diff_pair_adjacency": "#0891b2",
        "debug_access_cluster": "#7c3aed",
    },
    role_defaults={
        "mcu": "center_cluster",
        "crystal": "center_cluster",
        "decoupling": "center_cluster",
        "power_input": "power_chain",
        "regulator": "power_chain",
        "clock": "clock_ring",
        "usb": "usb_interface_chain",
        "esd": "usb_interface_chain",
        "series_resistor": "usb_interface_chain",
        "connector": "edge_connector",
        "debug": "edge_connector",
        "indicator": "indicator_cluster",
        "analog": "analog_island",
        "rf": "rf_island",
    },
    role_slot_preferences={
        "crystal": ["top_right", "top_left", "right", "left"],
        "decoupling": ["top", "bottom", "left", "right"],
        "mcu_decoupling": ["top", "bottom", "left", "right"],
        "reset_button": ["bottom_right", "bottom_left", "right", "left"],
        "boot_button": ["bottom_right", "bottom_left", "right", "left"],
        "regulator": ["left", "right", "top", "bottom"],
        "power_input": ["left", "right", "top", "bottom"],
        "indicator": ["top", "right", "bottom", "left"],
        "led": ["top", "right", "bottom", "left"],
    },
    cluster_slot_order=[
        "top_right",
        "top_left",
        "bottom_left",
        "bottom_right",
        "right",
        "left",
        "top",
        "bottom",
    ],
    board_defaults={
        "width_mm": 150,
        "height_mm": 110,
        "margin_mm": 4,
    },
    templates={},
)
ACTIVE_RULES = DEFAULT_RULES


@dataclass
class ComponentSpec:
    ref: str
    role: str
    grid_w: int
    grid_h: int
    clearance: int = 1
    pattern: str = ""
    anchor_ref: str = ""
    preferred_slot: str = ""
    edge: str = ""
    lane_y: int = 0
    region: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Placement:
    ref: str
    x: int
    y: int
    w: int
    h: int
    pattern: str
    step: int
    note: str = ""
    color: str = "#444444"

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.w, self.y + self.h


@dataclass
class CandidateOption:
    placement: Placement
    score: int
    reason: str
    breakdown: dict[str, int] = field(default_factory=dict)


class CandidateList(list[CandidateOption]):
    rejected_summary: list[str]
    rejected_samples: list[dict[str, Any]]
    attempted_count: int
    accepted_count: int

    def __init__(self, items: list[CandidateOption] | None = None) -> None:
        super().__init__(items or [])
        self.rejected_summary = []
        self.rejected_samples = []
        self.attempted_count = 0
        self.accepted_count = 0


@dataclass
class SolveStepResult:
    ref: str
    score: int
    candidate_count: int
    reason: str
    placement: Placement
    breakdown: dict[str, int] = field(default_factory=dict)
    rejected_summary: list[str] = field(default_factory=list)
    rejected_samples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BoardState:
    width: int
    height: int
    margin: int
    placements: dict[str, Placement] = field(default_factory=dict)
    keepouts: list[tuple[int, int, int, int]] = field(default_factory=list)

    def fits(self, placement: Placement) -> bool:
        return not self.fit_reasons(placement)[1]

    def fit_reasons(self, placement: Placement) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        left, bottom, right, top = placement.box
        if left < self.margin:
            reasons.append("left edge outside board margin")
        if bottom < self.margin:
            reasons.append("bottom edge outside board margin")
        if right > self.width - self.margin:
            reasons.append("right edge outside board margin")
        if top > self.height - self.margin:
            reasons.append("top edge outside board margin")
        for other in self.placements.values():
            if overlaps(placement.box, other.box):
                reasons.append(f"overlaps {other.ref}")
        for index, keepout in enumerate(self.keepouts, start=1):
            if overlaps(placement.box, keepout):
                x0, y0, x1, y1 = keepout
                reasons.append(f"overlaps keepout #{index} [{x0},{y0} -> {x1},{y1}]")
        return not reasons, reasons


class PlacementSolver(ABC):
    @abstractmethod
    def solve_cluster_pattern(
        self,
        pattern_type: str,
        members: list[str],
        anchor_ref: str,
        base_x: int | None,
        base_y: int | None,
        pattern_name: str,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_chain_pattern(
        self,
        pattern_type: str,
        members: list[str],
        direction: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_power_entry_chain(
        self,
        pattern_type: str,
        members: list[str],
        lane_y: int,
        gap: int,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_usb_interface_chain(
        self,
        pattern_type: str,
        members: list[str],
        edge: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_debug_access_cluster(
        self,
        pattern_type: str,
        members: list[str],
        edge: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_edge_sequence(
        self,
        pattern_type: str,
        members: list[str],
        edge: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_island_sequence(
        self,
        pattern_type: str,
        members: list[str],
        region: str,
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_rf_keepout_sequence(
        self,
        pattern_type: str,
        members: list[str],
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError

    @abstractmethod
    def solve_diff_pair_sequence(
        self,
        pattern_type: str,
        members: list[str],
    ) -> tuple[list["SolveStepResult"], list[ComponentSpec]]:
        raise NotImplementedError


class ConstraintSearchPlacementSolver(PlacementSolver):
    def __init__(self, board: BoardState, components: dict[str, ComponentSpec], rules: LayoutLabRules, cursor: dict[str, int]) -> None:
        self.board = board
        self.components = components
        self.rules = rules
        self.cursor = cursor

    def solve_cluster_pattern(
        self,
        pattern_type: str,
        members: list[str],
        anchor_ref: str,
        base_x: int | None,
        base_y: int | None,
        pattern_name: str,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_cluster_pattern(
            self.board,
            self.components,
            members,
            pattern_type,
            self.rules,
            anchor_ref=anchor_ref,
            base_x=base_x,
            base_y=base_y,
            pattern_name=pattern_name,
        )

    def solve_chain_pattern(
        self,
        pattern_type: str,
        members: list[str],
        direction: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_chain_pattern(self.board, self.components, members, pattern_type, direction, lane_y, gap)

    def solve_power_entry_chain(
        self,
        pattern_type: str,
        members: list[str],
        lane_y: int,
        gap: int,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_power_entry_chain(self.board, self.components, members, pattern_type, lane_y, gap)

    def solve_usb_interface_chain(
        self,
        pattern_type: str,
        members: list[str],
        edge: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_usb_interface_chain(self.board, self.components, members, pattern_type, edge, lane_y, gap)

    def solve_debug_access_cluster(
        self,
        pattern_type: str,
        members: list[str],
        edge: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_debug_access_cluster(self.board, self.components, members, pattern_type, edge, lane_y, gap, self.rules)

    def solve_edge_sequence(
        self,
        pattern_type: str,
        members: list[str],
        edge: str,
        lane_y: int,
        gap: int,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_edge_sequence(self.board, self.components, members, pattern_type, edge, lane_y, gap)

    def solve_island_sequence(
        self,
        pattern_type: str,
        members: list[str],
        region: str,
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_island_sequence(self.board, self.components, members, pattern_type, region, self.cursor)

    def solve_rf_keepout_sequence(
        self,
        pattern_type: str,
        members: list[str],
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        keepout = (
            self.board.width - 34,
            self.board.height - 24,
            self.board.width - 16,
            self.board.height - 12,
        )
        self.board.keepouts.append(keepout)
        return solve_rf_keepout_sequence(self.board, self.components, members, pattern_type, keepout)

    def solve_diff_pair_sequence(
        self,
        pattern_type: str,
        members: list[str],
    ) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
        return solve_diff_pair_sequence(self.board, self.components, members, pattern_type)


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def center_position(board: BoardState, comp: ComponentSpec) -> tuple[int, int]:
    x = round(board.width / 2 - comp.grid_w / 2)
    y = round(board.height / 2 - comp.grid_h / 2)
    return clamp(x, board.margin, board.width - board.margin - comp.grid_w), clamp(
        y, board.margin, board.height - board.margin - comp.grid_h
    )


def anchor_rect(placement: Placement) -> tuple[int, int, int, int]:
    return placement.box


def slot_position(
    anchor: Placement,
    comp: ComponentSpec,
    slot: str,
    gap: int,
) -> tuple[int, int]:
    return slot_position_from_box(anchor.box, comp, slot, gap)


def slot_position_from_box(
    box: tuple[int, int, int, int],
    comp: ComponentSpec,
    slot: str,
    gap: int,
) -> tuple[int, int]:
    ax0, ay0, ax1, ay1 = box
    aw = ax1 - ax0
    ah = ay1 - ay0

    if slot == "top":
        x = ax0 + round((aw - comp.grid_w) / 2)
        y = ay1 + gap
    elif slot == "bottom":
        x = ax0 + round((aw - comp.grid_w) / 2)
        y = ay0 - comp.grid_h - gap
    elif slot == "left":
        x = ax0 - comp.grid_w - gap
        y = ay0 + round((ah - comp.grid_h) / 2)
    elif slot == "right":
        x = ax1 + gap
        y = ay0 + round((ah - comp.grid_h) / 2)
    elif slot == "top_left":
        x = ax0 - comp.grid_w - gap
        y = ay1 + gap
    elif slot == "top_right":
        x = ax1 + gap
        y = ay1 + gap
    elif slot == "bottom_left":
        x = ax0 - comp.grid_w - gap
        y = ay0 - comp.grid_h - gap
    elif slot == "bottom_right":
        x = ax1 + gap
        y = ay0 - comp.grid_h - gap
    else:
        x = ax1 + gap
        y = ay1 + gap

    return x, y


def spiral_candidates(x: int, y: int, radius: int) -> Iterable[tuple[int, int]]:
    yield x, y
    for r in range(1, radius + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                yield x + dx, y + dy


def spiral_candidates_with_distance(x: int, y: int, radius: int) -> Iterable[tuple[int, int, int]]:
    yield x, y, 0
    for r in range(1, radius + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                yield x + dx, y + dy, r


def candidate_options_from_bases(
    board: BoardState,
    comp: ComponentSpec,
    pattern: str,
    preferred_positions: list[tuple[int, int]],
    note: str,
    step: int,
    search_radius: int = 4,
    score_bias: int = 0,
) -> CandidateList:
    options = CandidateList()
    seen: set[tuple[int, int]] = set()
    rejected: dict[str, int] = {}
    attempted = 0
    for base_rank, (base_x, base_y) in enumerate(preferred_positions):
        for x, y, radius in spiral_candidates_with_distance(base_x, base_y, radius=search_radius):
            if (x, y) in seen:
                continue
            seen.add((x, y))
            attempted += 1
            placement = Placement(
                ref=comp.ref,
                x=x,
                y=y,
                w=comp.grid_w,
                h=comp.grid_h,
                pattern=pattern,
                step=step,
                note=note,
                color=ACTIVE_RULES.pattern_colors.get(pattern, "#444444"),
            )
            ok, reasons = board.fit_reasons(placement)
            if ok:
                distance_penalty = abs(x - base_x) + abs(y - base_y)
                base_rank_penalty = base_rank * 120
                radius_penalty = radius * 12
                score = score_bias + 1000 - base_rank_penalty - radius_penalty - distance_penalty
                options.append(
                    CandidateOption(
                        placement=placement,
                        score=score,
                        reason=f"base=({base_x},{base_y}) radius={radius}",
                        breakdown={
                            "bias": score_bias,
                            "base_reward": 1000,
                            "base_rank_penalty": -base_rank_penalty,
                            "radius_penalty": -radius_penalty,
                            "distance_penalty": -distance_penalty,
                        },
                    )
                )
            else:
                for reason in reasons:
                    rejected[reason] = rejected.get(reason, 0) + 1
                if len(options.rejected_samples) < 12:
                    options.rejected_samples.append(
                        {
                            "ref": comp.ref,
                            "x": x,
                            "y": y,
                            "w": comp.grid_w,
                            "h": comp.grid_h,
                            "base": [base_x, base_y],
                            "radius": radius,
                            "reasons": list(reasons[:3]),
                        }
                    )
    options.sort(key=lambda item: (-item.score, item.placement.x, item.placement.y))
    options.rejected_summary = [f"{reason}: {count}" for reason, count in sorted(rejected.items(), key=lambda item: (-item[1], item[0]))]
    options.attempted_count = attempted
    options.accepted_count = len(options)
    return options


def place_with_search(
    board: BoardState,
    comp: ComponentSpec,
    pattern: str,
    preferred_positions: list[tuple[int, int]],
    note: str,
    step: int,
    search_radius: int = 4,
) -> Placement:
    for base_x, base_y in preferred_positions:
        for x, y in spiral_candidates(base_x, base_y, radius=search_radius):
            placement = Placement(
                ref=comp.ref,
                x=x,
                y=y,
                w=comp.grid_w,
                h=comp.grid_h,
                pattern=pattern,
                step=step,
                note=note,
                color=ACTIVE_RULES.pattern_colors.get(pattern, "#444444"),
            )
            if board.fits(placement):
                board.placements[comp.ref] = placement
                return placement
    raise RuntimeError(f"Unable to place {comp.ref} with pattern {pattern}.")


def solve_sequence_with_constraints(
    board: BoardState,
    components: list[ComponentSpec],
    candidate_factory: Any,
    apply_state: Any | None = None,
    state: dict[str, Any] | None = None,
) -> list[SolveStepResult]:
    state = dict(state or {})
    chosen: list[Placement] = []
    trace: list[SolveStepResult] = []

    def recurse(index: int) -> bool:
        if index >= len(components):
            return True

        comp = components[index]
        snapshot = deepcopy(state)
        candidates: list[CandidateOption] = candidate_factory(index, comp, chosen, state)
        candidates.sort(key=lambda item: (-item.score, item.placement.x, item.placement.y))
        rejected_summary = list(getattr(candidates, "rejected_summary", []))
        for option in candidates:
            placement = option.placement
            ok, reasons = board.fit_reasons(placement)
            if not ok:
                for reason in reasons:
                    if reason not in rejected_summary:
                        rejected_summary.append(reason)
                continue
            board.placements[comp.ref] = placement
            chosen.append(placement)
            trace.append(
                SolveStepResult(
                    ref=comp.ref,
                    score=option.score,
                    candidate_count=len(candidates),
                    reason=option.reason,
                    placement=placement,
                    breakdown=dict(option.breakdown),
                    rejected_summary=rejected_summary,
                    rejected_samples=list(getattr(candidates, "rejected_samples", [])),
                )
            )
            if apply_state is not None:
                apply_state(index, comp, placement, state)
            if recurse(index + 1):
                return True
            trace.pop()
            chosen.pop()
            del board.placements[comp.ref]
            state.clear()
            state.update(snapshot)
        if rejected_summary:
            state.setdefault("_rejected", []).append({"ref": comp.ref, "reasons": rejected_summary})
        return False

    if not recurse(0):
        rejected = state.get("_rejected", [])
        if isinstance(rejected, list) and rejected:
            compact: list[str] = []
            for item in rejected[-4:]:
                if isinstance(item, dict):
                    ref = str(item.get("ref", "")).strip()
                    reasons = item.get("reasons", [])
                    if ref and isinstance(reasons, list):
                        compact.append(f"{ref}: {', '.join(str(reason) for reason in reasons[:4])}")
            if compact:
                raise RuntimeError(
                    "Unable to satisfy placement constraints for pattern sequence. "
                    f"Rejected summary: {' | '.join(compact)}"
                )
        raise RuntimeError("Unable to satisfy placement constraints for pattern sequence.")
    return trace


def record_solved_steps(
    *,
    board: BoardState,
    steps_dir: Path,
    pattern_name: str,
    pattern_type: str,
    template: dict[str, Any],
    rules: LayoutLabRules,
    components: list[ComponentSpec],
    results: list[SolveStepResult],
    step_start: int,
    relation_builder: Any | None = None,
    explanation_kwargs_builder: Any | None = None,
) -> tuple[list[dict[str, Any]], int]:
    summary: list[dict[str, Any]] = []
    step = step_start
    for index, result in enumerate(results):
        comp = components[index]
        relation = relation_builder(index, result, components, results, board) if relation_builder else None
        explanation_kwargs = (
            explanation_kwargs_builder(index, result, comp, components, results, board) if explanation_kwargs_builder else {}
        )
        details = explain_placement(
            rules=rules,
            pattern_name=pattern_name,
            pattern_type=pattern_type,
            ref=comp.ref,
            comp=comp,
            placement=result.placement,
            template=template,
            **explanation_kwargs,
            score=result.score,
            candidate_count=result.candidate_count,
            candidate_reason=result.reason,
            score_breakdown=result.breakdown,
            rejected_summary=result.rejected_summary,
        )
        render_svg(
            board,
            steps_dir / f"{step:03d}_{comp.ref.lower()}.svg",
            title=f"{pattern_name} / {pattern_type} / {comp.ref}",
            active_ref=comp.ref,
            relation=relation,
            details=details,
            rejected_samples=result.rejected_samples,
        )
        summary.append(
            {
                "step": step,
                "ref": comp.ref,
                "pattern": pattern_type,
                "name": pattern_name,
                "placement": asdict(result.placement),
                "solver": {
                    "score": result.score,
                    "candidate_count": result.candidate_count,
                    "reason": result.reason,
                    "breakdown": result.breakdown,
                    "rejected_summary": result.rejected_summary,
                    "rejected_samples": result.rejected_samples,
                },
                "explanation": details,
            }
        )
        step += 1
    return summary, step


def solve_cluster_pattern(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    rules: LayoutLabRules,
    anchor_ref: str,
    base_x: int | None,
    base_y: int | None,
    pattern_name: str,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_refs = [anchor_ref] if anchor_ref else []
    ordered_refs.extend([ref for ref in members if ref != anchor_ref])
    ordered_components = [components[ref] for ref in ordered_refs]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        if index == 0:
            bases: list[tuple[int, int]] = []
            if base_x is not None and base_y is not None:
                bases.append((base_x, base_y))
            bases.append(center_position(board, comp))
            if pattern_type == "clock_ring":
                bases.extend(
                    [
                        (board.width // 2 + 22, board.height // 2 - 14),
                        (board.width // 2 + 30, board.height // 2 - 18),
                        (board.width // 2 + 20, board.height // 2 + 10),
                    ]
                )
            return candidate_options_from_bases(
                board,
                comp,
                pattern_type,
                bases,
                note="cluster anchor",
                step=len(chosen) + 1,
                search_radius=6,
                score_bias=60,
            )

        anchor = board.placements.get(anchor_ref) if anchor_ref else (chosen[0] if chosen else None)
        if anchor is None:
            return []
        gap = max(1, comp.clearance)
        slots = [comp.preferred_slot] if comp.preferred_slot else preferred_slots_for_role_from_rules(comp.role, rules)
        if not slots:
            slots = list(rules.cluster_slot_order)
        base_positions = [slot_position(anchor, comp, slot, gap) for slot in slots]
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            base_positions,
            note=f"cluster around {anchor.ref}",
            step=len(chosen) + 1,
            search_radius=4,
            score_bias=max(0, 50 - index * 5),
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_chain_pattern(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    direction: str,
    lane_y: int,
    gap: int,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        if index == 0:
            if direction == "right":
                base_x = board.margin + 2
            elif direction == "left":
                base_x = board.width - board.margin - comp.grid_w - 2
            else:
                base_x = board.margin + 2
            base_y = clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h)
            return candidate_options_from_bases(
                board,
                comp,
                pattern_type,
                [(base_x, base_y)],
                note="chain start",
                step=1,
                search_radius=4,
                score_bias=50,
            )

        previous = chosen[-1]
        if direction == "right":
            base = (previous.x + previous.w + gap, previous.y)
        elif direction == "left":
            base = (previous.x - comp.grid_w - gap, previous.y)
        elif direction == "up":
            base = (previous.x, previous.y + previous.h + gap)
        else:
            base = (previous.x, previous.y - comp.grid_h - gap)
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            [base],
            note="chain placement",
            step=len(chosen) + 1,
            search_radius=5,
            score_bias=max(0, 40 - index * 4),
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_edge_sequence(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    edge: str,
    lane_y: int,
    gap: int,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        if index == 0:
            if edge == "right":
                base_x = board.width - board.margin - comp.grid_w
            elif edge == "left":
                base_x = board.margin
            else:
                base_x = clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w)
            if edge == "top":
                base_y = board.height - board.margin - comp.grid_h
            elif edge == "bottom":
                base_y = board.margin
            else:
                base_y = clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h)
            return candidate_options_from_bases(
                board,
                comp,
                pattern_type,
                [(base_x, base_y)],
                note=f"edge placement on {edge}",
                step=1,
                search_radius=4,
                score_bias=45,
            )

        previous = chosen[-1]
        if edge in {"left", "right"}:
            base = (
                previous.x + previous.w + gap if edge == "left" else previous.x - comp.grid_w - gap,
                previous.y,
            )
        else:
            base = (
                previous.x,
                previous.y + previous.h + gap if edge == "bottom" else previous.y - comp.grid_h - gap,
            )
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            [base],
            note=f"edge chain from {previous.ref}",
            step=len(chosen) + 1,
            search_radius=4,
            score_bias=max(0, 30 - index * 3),
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_power_entry_chain(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    lane_y: int,
    gap: int,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        if index == 0:
            base = (board.margin, clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h))
            return candidate_options_from_bases(
                board,
                comp,
                pattern_type,
                [base],
                note="edge placement on left",
                step=1,
                search_radius=4,
                score_bias=55,
            )
        previous = chosen[-1]
        base = (previous.x + previous.w + gap, previous.y)
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            [base],
            note="chain placement",
            step=len(chosen) + 1,
            search_radius=5,
            score_bias=40 - index * 4,
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_usb_interface_chain(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    edge: str,
    lane_y: int,
    gap: int,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]
    inward = inward_direction_for_edge(edge)

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        if index == 0:
            if edge == "right":
                base = (board.width - board.margin - comp.grid_w, clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h))
            elif edge == "left":
                base = (board.margin, clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h))
            elif edge == "top":
                base = (clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w), board.height - board.margin - comp.grid_h)
            else:
                base = (clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w), board.margin)
            return candidate_options_from_bases(
                board,
                comp,
                pattern_type,
                [base],
                note=f"edge placement on {edge}",
                step=1,
                search_radius=4,
                score_bias=55,
            )
        previous = chosen[-1]
        if inward == "left":
            base = (previous.x - comp.grid_w - gap, previous.y)
        elif inward == "right":
            base = (previous.x + previous.w + gap, previous.y)
        elif inward == "up":
            base = (previous.x, previous.y + previous.h + gap)
        else:
            base = (previous.x, previous.y - comp.grid_h - gap)
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            [base],
            note=f"chain placement inward from {previous.ref}",
            step=len(chosen) + 1,
            search_radius=5,
            score_bias=42 - index * 4,
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_debug_access_cluster(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    edge: str,
    lane_y: int,
    gap: int,
    rules: LayoutLabRules,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        if index == 0:
            if edge == "right":
                base = (board.width - board.margin - comp.grid_w, clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h))
            elif edge == "left":
                base = (board.margin, clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h))
            elif edge == "top":
                base = (clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w), board.height - board.margin - comp.grid_h)
            else:
                base = (clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w), board.margin)
            return candidate_options_from_bases(
                board,
                comp,
                pattern_type,
                [base],
                note=f"edge placement on {edge}",
                step=1,
                search_radius=4,
                score_bias=55,
            )
        anchor = chosen[-1]
        slots = [comp.preferred_slot] if comp.preferred_slot else preferred_slots_for_role_from_rules(comp.role, rules)
        if not slots:
            slots = list(rules.cluster_slot_order)
        bases = [slot_position_from_box(anchor.box, comp, slot, max(1, comp.clearance)) for slot in slots]
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            bases,
            note=f"cluster around {anchor.ref}",
            step=len(chosen) + 1,
            search_radius=4,
            score_bias=45 - index * 4,
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_island_sequence(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    region: str,
    cursor: dict[str, int],
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]
    state = {"cursor": dict(cursor)}

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], solve_state: dict[str, Any]) -> list[CandidateOption]:
        local_cursor = solve_state.setdefault("cursor", {})
        if region == "top_left":
            origin_x = board.margin + 2
            origin_y = board.height - board.margin - 15
        elif region == "top_right":
            origin_x = board.width - board.margin - 40
            origin_y = board.height - board.margin - 15
        elif region == "bottom_left":
            origin_x = board.margin + 2
            origin_y = board.margin + 2
        else:
            origin_x = board.width - board.margin - 40
            origin_y = board.margin + 2
        cursor_x = int(local_cursor.get(f"{pattern_type}:{region}:x", origin_x))
        cursor_y = int(local_cursor.get(f"{pattern_type}:{region}:y", origin_y))
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            [(cursor_x, cursor_y)],
            note=f"island placement in {region}",
            step=len(chosen) + 1,
            search_radius=6,
            score_bias=35,
        )

    def apply_state(index: int, comp: ComponentSpec, placement: Placement, solve_state: dict[str, Any]) -> None:
        local_cursor = solve_state.setdefault("cursor", {})
        local_cursor[f"{pattern_type}:{region}:x"] = placement.x + placement.w + max(1, comp.clearance)
        local_cursor[f"{pattern_type}:{region}:y"] = placement.y

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory, apply_state=apply_state, state=state)
    cursor.clear()
    cursor.update(state.get("cursor", {}))
    return results, ordered_components


def solve_rf_keepout_sequence(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
    keepout: tuple[int, int, int, int],
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]
    rf_slots = ["bottom_left", "left", "bottom_right", "top_left", "top_right"]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        slot = rf_slots[min(index, len(rf_slots) - 1)]
        base = slot_position_from_box(keepout, comp, slot, gap=max(1, comp.clearance))
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            [base],
            note=f"rf placement around keepout slot {slot}",
            step=len(chosen) + 1,
            search_radius=5,
            score_bias=55 - index * 4,
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def solve_diff_pair_sequence(
    board: BoardState,
    components: dict[str, ComponentSpec],
    members: list[str],
    pattern_type: str,
) -> tuple[list[SolveStepResult], list[ComponentSpec]]:
    ordered_components = [components[ref] for ref in members]

    def candidate_factory(index: int, comp: ComponentSpec, chosen: list[Placement], state: dict[str, Any]) -> list[CandidateOption]:
        base_x = board.width // 2 - 18 + index * (comp.grid_w + 3)
        bases = [
            (base_x, board.height // 2 + 14),
            (base_x, board.height // 2 - 8),
            (base_x, board.height // 2 - 22),
        ]
        return candidate_options_from_bases(
            board,
            comp,
            pattern_type,
            bases,
            note="differential pair adjacency",
            step=len(chosen) + 1,
            search_radius=10,
            score_bias=40,
        )

    results = solve_sequence_with_constraints(board, ordered_components, candidate_factory)
    return results, ordered_components


def preferred_slots_for_role(role: str) -> list[str]:
    return preferred_slots_for_role_from_rules(role, ACTIVE_RULES)


def preferred_slots_for_role_from_rules(role: str, rules: LayoutLabRules) -> list[str]:
    role = role.lower().strip()
    slots = rules.role_slot_preferences.get(role)
    if isinstance(slots, list) and slots:
        return [str(item) for item in slots if str(item)]
    return list(rules.cluster_slot_order) or [
        "top_right",
        "top_left",
        "bottom_left",
        "bottom_right",
        "right",
        "left",
        "top",
        "bottom",
    ]


def place_cluster(
    board: BoardState,
    comp: ComponentSpec,
    anchor: Placement | None,
    step: int,
    pattern: str,
    rules: LayoutLabRules,
) -> Placement:
    if anchor is None:
        x, y = center_position(board, comp)
        return place_with_search(
            board,
            comp,
            pattern,
            [(x, y)],
            note="cluster anchor at board center",
            step=step,
        )

    gap = max(1, comp.clearance)
    slots = [comp.preferred_slot] if comp.preferred_slot else preferred_slots_for_role_from_rules(comp.role, rules)
    if not slots:
        slots = CLUSTER_SLOT_ORDER
    candidates = [slot_position(anchor, comp, slot, gap) for slot in slots]
    return place_with_search(
        board,
        comp,
        pattern,
        candidates,
        note=f"cluster around {anchor.ref}",
        step=step,
    )


def place_clock_ring(
    board: BoardState,
    comp: ComponentSpec,
    anchor: Placement | None,
    step: int,
    pattern: str,
    rules: LayoutLabRules,
) -> Placement:
    return place_cluster(board, comp, anchor, step, pattern, rules)


def place_chain(
    board: BoardState,
    comp: ComponentSpec,
    previous: Placement | None,
    step: int,
    pattern: str,
    direction: str,
    lane_y: int,
    gap: int,
) -> Placement:
    if previous is None:
        if direction == "right":
            x = board.margin + 2
        elif direction == "left":
            x = board.width - board.margin - comp.grid_w - 2
        else:
            x = board.margin + 2
        y = clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h)
    else:
        if direction == "right":
            x = previous.x + previous.w + gap
            y = previous.y
        elif direction == "left":
            x = previous.x - comp.grid_w - gap
            y = previous.y
        elif direction == "up":
            x = previous.x
            y = previous.y + previous.h + gap
        else:
            x = previous.x
            y = previous.y - comp.grid_h - gap

    return place_with_search(
        board,
        comp,
        pattern,
        [(x, y)],
        note="chain placement",
        step=step,
    )


def place_power_entry_chain(
    board: BoardState,
    comp: ComponentSpec,
    previous: Placement | None,
    step: int,
    pattern: str,
    lane_y: int,
    gap: int,
) -> Placement:
    if previous is None:
        return place_edge(
            board,
            comp,
            step,
            pattern,
            edge="left",
            lane_y=lane_y,
            gap=gap,
        )
    return place_chain(
        board,
        comp,
        previous,
        step,
        pattern,
        direction="right",
        lane_y=lane_y,
        gap=gap,
    )


def place_edge(
    board: BoardState,
    comp: ComponentSpec,
    step: int,
    pattern: str,
    edge: str,
    lane_y: int,
    gap: int,
) -> Placement:
    if edge == "right":
        x = board.width - board.margin - comp.grid_w
    elif edge == "left":
        x = board.margin
    elif edge == "top":
        x = clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w)
    else:
        x = clamp(lane_y, board.margin, board.width - board.margin - comp.grid_w)

    if edge == "top":
        y = board.height - board.margin - comp.grid_h
    elif edge == "bottom":
        y = board.margin
    else:
        y = clamp(lane_y, board.margin, board.height - board.margin - comp.grid_h)

    return place_with_search(
        board,
        comp,
        pattern,
        [(x, y)],
        note=f"edge placement on {edge}",
        step=step,
    )


def inward_direction_for_edge(edge: str) -> str:
    if edge == "right":
        return "left"
    if edge == "left":
        return "right"
    if edge == "top":
        return "down"
    return "up"


def place_usb_interface_chain(
    board: BoardState,
    comp: ComponentSpec,
    previous: Placement | None,
    step: int,
    pattern: str,
    edge: str,
    lane_y: int,
    gap: int,
) -> Placement:
    inward = inward_direction_for_edge(edge)
    if previous is None:
        return place_edge(
            board,
            comp,
            step,
            pattern,
            edge=edge,
            lane_y=lane_y,
            gap=gap,
        )
    return place_chain(
        board,
        comp,
        previous,
        step,
        pattern,
        direction=inward,
        lane_y=lane_y,
        gap=gap,
    )


def place_debug_access_cluster(
    board: BoardState,
    comp: ComponentSpec,
    previous: Placement | None,
    step: int,
    pattern: str,
    edge: str,
    lane_y: int,
    gap: int,
    rules: LayoutLabRules,
) -> Placement:
    if previous is None:
        return place_edge(
            board,
            comp,
            step,
            pattern,
            edge=edge,
            lane_y=lane_y,
            gap=gap,
        )
    return place_cluster(board, comp, previous, step, pattern, rules)


def place_rf_keepout_island(
    board: BoardState,
    comp: ComponentSpec,
    step: int,
    pattern: str,
    keepout: tuple[int, int, int, int],
    slot: str,
    gap: int,
) -> Placement:
    x, y = slot_position_from_box(keepout, comp, slot, gap)
    return place_with_search(
        board,
        comp,
        pattern,
        [(x, y)],
        note=f"rf placement around keepout slot {slot}",
        step=step,
        search_radius=5,
    )


def place_island(
    board: BoardState,
    comp: ComponentSpec,
    step: int,
    pattern: str,
    region: str,
    cursor: dict[str, int],
) -> Placement:
    if region == "top_left":
        origin_x = board.margin + 2
        origin_y = board.height - board.margin - 15
    elif region == "top_right":
        origin_x = board.width - board.margin - 40
        origin_y = board.height - board.margin - 15
    elif region == "bottom_left":
        origin_x = board.margin + 2
        origin_y = board.margin + 2
    else:
        origin_x = board.width - board.margin - 40
        origin_y = board.margin + 2

    cursor_x = cursor.setdefault(f"{pattern}:{region}:x", origin_x)
    cursor_y = cursor.setdefault(f"{pattern}:{region}:y", origin_y)
    placement = place_with_search(
        board,
        comp,
        pattern,
        [(cursor_x, cursor_y)],
        note=f"island placement in {region}",
        step=step,
    )
    cursor[f"{pattern}:{region}:x"] = placement.x + placement.w + max(1, comp.clearance)
    cursor[f"{pattern}:{region}:y"] = placement.y
    return placement


def render_svg(
    board: BoardState,
    out_path: Path,
    title: str,
    active_ref: str = "",
    relation: tuple[str, str] | None = None,
    details: list[str] | None = None,
    rejected_samples: list[dict[str, Any]] | None = None,
) -> None:
    scale = 6
    width_px = board.width * scale + 80
    height_px = board.height * scale + 120
    pieces: list[str] = []
    pieces.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}">'
    )
    pieces.append(
        "<defs>"
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 z" fill="#64748b" />'
        "</marker>"
        "</defs>"
    )
    pieces.append(f'<rect x="0" y="0" width="{width_px}" height="{height_px}" fill="#f8fafc" />')
    pieces.append(
        f'<text x="24" y="28" font-family="Arial" font-size="18" fill="#111827">{escape(title)}</text>'
    )
    pieces.append(
        f'<text x="24" y="48" font-family="Arial" font-size="12" fill="#475569">'
        f"Grid: {GRID_MM}mm x {GRID_MM}mm, board: {board.width}mm x {board.height}mm</text>"
    )

    if details:
        detail_lines = wrap_lines(details, width=42)[:8]
        panel_width = 310
        panel_height = 18 + len(detail_lines) * 14
        panel_x = width_px - panel_width - 20
        panel_y = 18
        pieces.append(
            f'<rect x="{panel_x}" y="{panel_y}" width="{panel_width}" height="{panel_height}" '
            f'rx="10" ry="10" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5" />'
        )
        pieces.append(
            f'<text x="{panel_x + 12}" y="{panel_y + 16}" font-family="Arial" font-size="11" '
            f'font-weight="bold" fill="#0f172a">摆放理由</text>'
        )
        for index, line in enumerate(detail_lines):
            pieces.append(
                f'<text x="{panel_x + 12}" y="{panel_y + 34 + index * 14}" font-family="Arial" '
                f'font-size="10" fill="#334155">{escape(line)}</text>'
            )

    legend_x = 24
    legend_y = 58
    legend_width = 260
    legend_height = 86
    pieces.append(
        f'<rect x="{legend_x}" y="{legend_y}" width="{legend_width}" height="{legend_height}" '
        f'rx="10" ry="10" fill="#ffffff" fill-opacity="0.96" stroke="#cbd5e1" stroke-width="1.5" />'
    )
    pieces.append(
        f'<text x="{legend_x + 12}" y="{legend_y + 17}" font-family="Arial" font-size="11" '
        f'font-weight="bold" fill="#0f172a">图例</text>'
    )
    legend_items = [
        ("最终选中", "#10b981", "solid"),
        ("被拒绝候选", "#ef4444", "dashed"),
        ("安全边界", "#94a3b8", "dashed"),
        ("已放置器件", "#8b5cf6", "fill"),
    ]
    for index, (label, color, style) in enumerate(legend_items):
        row_y = legend_y + 34 + index * 13
        if style == "fill":
            pieces.append(
                f'<rect x="{legend_x + 12}" y="{row_y - 9}" width="12" height="10" '
                f'fill="{color}" fill-opacity="0.22" stroke="{color}" stroke-width="2" />'
            )
        elif style == "dashed":
            pieces.append(
                f'<rect x="{legend_x + 12}" y="{row_y - 9}" width="12" height="10" '
                f'fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="4 3" />'
            )
        else:
            pieces.append(
                f'<rect x="{legend_x + 12}" y="{row_y - 9}" width="12" height="10" '
                f'fill="{color}" fill-opacity="0.22" stroke="{color}" stroke-width="2" />'
            )
        pieces.append(
            f'<text x="{legend_x + 32}" y="{row_y}" font-family="Arial" font-size="10" '
            f'fill="#334155">{escape(label)}</text>'
        )

    origin_x = 40
    origin_y = 70
    for x in range(board.width + 1):
        stroke = "#e2e8f0" if x % 5 else "#cbd5e1"
        pieces.append(
            f'<line x1="{origin_x + x * scale}" y1="{origin_y}" '
            f'x2="{origin_x + x * scale}" y2="{origin_y + board.height * scale}" '
            f'stroke="{stroke}" stroke-width="1" />'
        )
    for y in range(board.height + 1):
        stroke = "#e2e8f0" if y % 5 else "#cbd5e1"
        pieces.append(
            f'<line x1="{origin_x}" y1="{origin_y + y * scale}" '
            f'x2="{origin_x + board.width * scale}" y2="{origin_y + y * scale}" '
            f'stroke="{stroke}" stroke-width="1" />'
        )

    pieces.append(
        f'<rect x="{origin_x + board.margin * scale}" y="{origin_y + board.margin * scale}" '
        f'width="{(board.width - board.margin * 2) * scale}" '
        f'height="{(board.height - board.margin * 2) * scale}" '
        f'fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6 4" />'
    )

    for keepout in board.keepouts:
        x0, y0, x1, y1 = keepout
        pieces.append(
            f'<rect x="{origin_x + x0 * scale}" y="{origin_y + y0 * scale}" '
            f'width="{(x1 - x0) * scale}" height="{(y1 - y0) * scale}" '
            f'fill="#f87171" fill-opacity="0.18" stroke="#b91c1c" stroke-width="2" '
            f'stroke-dasharray="5 4" />'
        )

    if relation is not None:
        from_ref, to_ref = relation
        if from_ref in board.placements and to_ref in board.placements:
            a = board.placements[from_ref]
            b = board.placements[to_ref]
            ax = origin_x + (a.x + a.w / 2) * scale
            ay = origin_y + (a.y + a.h / 2) * scale
            bx = origin_x + (b.x + b.w / 2) * scale
            by = origin_y + (b.y + b.h / 2) * scale
            pieces.append(
                f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" stroke="#64748b" '
                f'stroke-width="2" stroke-dasharray="6 4" marker-end="url(#arrow)" />'
            )

    if rejected_samples:
        for sample in rejected_samples[:6]:
            try:
                x = int(sample.get("x", 0))
                y = int(sample.get("y", 0))
                w = int(sample.get("w", 1))
                h = int(sample.get("h", 1))
            except (TypeError, ValueError):
                continue
            sx = origin_x + x * scale
            sy = origin_y + y * scale
            sw = w * scale
            sh = h * scale
            pieces.append(
                f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="4" ry="4" '
                f'fill="#ef4444" fill-opacity="0.08" stroke="#ef4444" stroke-width="1.5" '
                f'stroke-dasharray="4 3" />'
            )
            pieces.append(
                f'<line x1="{sx}" y1="{sy}" x2="{sx + sw}" y2="{sy + sh}" stroke="#ef4444" stroke-width="1.2" />'
            )
            pieces.append(
                f'<line x1="{sx + sw}" y1="{sy}" x2="{sx}" y2="{sy + sh}" stroke="#ef4444" stroke-width="1.2" />'
            )

    for placement in board.placements.values():
        fill = placement.color
        stroke = "#111827" if placement.ref == active_ref else "#334155"
        stroke_width = 3 if placement.ref == active_ref else 2
        x = origin_x + placement.x * scale
        y = origin_y + placement.y * scale
        w = placement.w * scale
        h = placement.h * scale
        pieces.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" ry="6" '
            f'fill="{fill}" fill-opacity="0.18" stroke="{stroke}" stroke-width="{stroke_width}" />'
        )
        pieces.append(
            f'<text x="{x + 4}" y="{y + 14}" font-family="Arial" font-size="11" fill="#111827">'
            f"{escape(placement.ref)}</text>"
        )
        pieces.append(
            f'<text x="{x + 4}" y="{y + 27}" font-family="Arial" font-size="9" fill="#475569">'
            f"{escape(placement.pattern)}</text>"
        )

    pieces.append("</svg>")
    out_path.write_text("\n".join(pieces), encoding="utf-8")


def load_scenario(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("Scenario must be a JSON object.")
    return payload


def load_rules(
    roles_path: Path | None = None,
    patterns_path: Path | None = None,
    legacy_rules_path: Path | None = None,
) -> LayoutLabRules:
    if legacy_rules_path is not None:
        role_path = legacy_rules_path
        pattern_path = legacy_rules_path
    else:
        role_path = roles_path or DEFAULT_ROLES_PATH
        pattern_path = patterns_path or DEFAULT_PATTERNS_PATH

    if legacy_rules_path is not None or role_path == DEFAULT_RULES_PATH:
        if not role_path.exists():
            return DEFAULT_RULES
        with role_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            return DEFAULT_RULES
        pattern_colors = dict(DEFAULT_RULES.pattern_colors)
        if isinstance(payload.get("pattern_colors"), dict):
            pattern_colors.update({str(k): str(v) for k, v in payload["pattern_colors"].items() if str(k) and str(v)})
        role_defaults = dict(DEFAULT_RULES.role_defaults)
        if isinstance(payload.get("role_defaults"), dict):
            role_defaults.update({str(k): str(v) for k, v in payload["role_defaults"].items() if str(k) and str(v)})
        role_slot_preferences = {key: list(value) for key, value in DEFAULT_RULES.role_slot_preferences.items()}
        if isinstance(payload.get("role_slot_preferences"), dict):
            for key, value in payload["role_slot_preferences"].items():
                if isinstance(value, list):
                    role_slot_preferences[str(key)] = [str(item) for item in value if str(item)]
        cluster_slot_order = [str(item) for item in payload.get("cluster_slot_order", DEFAULT_RULES.cluster_slot_order) if str(item)]
        if not cluster_slot_order:
            cluster_slot_order = list(DEFAULT_RULES.cluster_slot_order)
        board_defaults = dict(DEFAULT_RULES.board_defaults)
        if isinstance(payload.get("board_defaults"), dict):
            for key, value in payload["board_defaults"].items():
                if isinstance(value, (int, float)):
                    board_defaults[str(key)] = int(value)
        templates = payload.get("templates", {})
        if not isinstance(templates, dict):
            templates = {}
        return LayoutLabRules(
            pattern_colors=pattern_colors,
            role_defaults=role_defaults,
            role_slot_preferences=role_slot_preferences,
            cluster_slot_order=cluster_slot_order,
            board_defaults=board_defaults,
            templates={str(k): v for k, v in templates.items() if isinstance(v, dict)},
        )

    role_payload: dict[str, Any] = {}
    pattern_payload: dict[str, Any] = {}
    if role_path.exists():
        with role_path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            role_payload = loaded
    if pattern_path.exists():
        with pattern_path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            pattern_payload = loaded

    pattern_colors = dict(DEFAULT_RULES.pattern_colors)
    if isinstance(pattern_payload.get("pattern_colors"), dict):
        pattern_colors.update({str(k): str(v) for k, v in pattern_payload["pattern_colors"].items() if str(k) and str(v)})

    role_defaults = dict(DEFAULT_RULES.role_defaults)
    if isinstance(role_payload.get("role_defaults"), dict):
        role_defaults.update({str(k): str(v) for k, v in role_payload["role_defaults"].items() if str(k) and str(v)})

    role_slot_preferences = {key: list(value) for key, value in DEFAULT_RULES.role_slot_preferences.items()}
    if isinstance(role_payload.get("role_slot_preferences"), dict):
        for key, value in role_payload["role_slot_preferences"].items():
            if isinstance(value, list):
                role_slot_preferences[str(key)] = [str(item) for item in value if str(item)]

    cluster_slot_order = [str(item) for item in role_payload.get("cluster_slot_order", DEFAULT_RULES.cluster_slot_order) if str(item)]
    if not cluster_slot_order:
        cluster_slot_order = list(DEFAULT_RULES.cluster_slot_order)

    board_defaults = dict(DEFAULT_RULES.board_defaults)
    if isinstance(role_payload.get("board_defaults"), dict):
        for key, value in role_payload["board_defaults"].items():
            if isinstance(value, (int, float)):
                board_defaults[str(key)] = int(value)

    templates = pattern_payload.get("templates", {})
    if not isinstance(templates, dict):
        templates = {}

    return LayoutLabRules(
        pattern_colors=pattern_colors,
        role_defaults=role_defaults,
        role_slot_preferences=role_slot_preferences,
        cluster_slot_order=cluster_slot_order,
        board_defaults=board_defaults,
        templates={str(k): v for k, v in templates.items() if isinstance(v, dict)},
    )


def pattern_template(rules: LayoutLabRules, pattern_type: str) -> dict[str, Any]:
    template = rules.templates.get(pattern_type, {})
    return template if isinstance(template, dict) else {}


def template_string(template: dict[str, Any], name: str, fallback: str = "") -> str:
    value = template.get(name, fallback)
    return str(value).strip()


def template_int(template: dict[str, Any], name: str, fallback: int) -> int:
    value = template.get(name, fallback)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def explain_placement(
    *,
    rules: LayoutLabRules,
    pattern_name: str,
    pattern_type: str,
    ref: str,
    comp: ComponentSpec,
    placement: Placement,
    template: dict[str, Any],
    anchor_ref: str = "",
    previous_ref: str = "",
    direction: str = "",
    edge: str = "",
    region: str = "",
    lane_y: int = 0,
    gap: int = 0,
    base_x: int | None = None,
    base_y: int | None = None,
    score: int | None = None,
    candidate_count: int | None = None,
    candidate_reason: str = "",
    score_breakdown: dict[str, int] | None = None,
    rejected_summary: list[str] | None = None,
) -> list[str]:
    role_default = rules.role_defaults.get(comp.role, "")
    preferred_slots = preferred_slots_for_role_from_rules(comp.role, rules)
    summary = template_string(template, "summary", "")
    lines: list[str] = [
        f"{pattern_name} / {pattern_type}",
        summary or f"Role {comp.role or 'unknown'} uses {role_default or 'no default template'}",
    ]

    if pattern_type in {"center_cluster", "boot_reset_cluster", "clock_ring"}:
        if anchor_ref and ref == anchor_ref:
            if base_x is not None and base_y is not None:
                lines.append(f"Anchor {ref} starts from configured grid ({base_x}, {base_y}).")
            else:
                lines.append(f"Anchor {ref} starts from the board center search.")
        elif anchor_ref:
            lines.append(f"Placed around anchor {anchor_ref} using {len(preferred_slots)} preferred slots.")
            if preferred_slots:
                lines.append(f"Role {comp.role} prefers: {', '.join(preferred_slots[:4])}.")
        else:
            lines.append("Placed as a local cluster without an explicit anchor.")
    elif pattern_type in {"power_chain", "signal_chain", "high_current_path"}:
        if previous_ref:
            lines.append(f"Placed after {previous_ref} to keep the chain ordered.")
        else:
            lines.append(f"Started on lane y={lane_y} and moved {direction or 'right'}.")
        lines.append(f"Chain gap is {gap} grid units.")
    elif pattern_type == "power_entry_chain":
        if previous_ref:
            lines.append(f"Continues the power path after {previous_ref}.")
        else:
            lines.append(f"Starts from the board edge and enters on lane y={lane_y}.")
        lines.append(f"Power entry gap is {gap} grid units.")
    elif pattern_type == "usb_interface_chain":
        if previous_ref:
            lines.append(f"Moves inward from {previous_ref} after the edge connector.")
        else:
            lines.append(f"Snaps to the {edge} board edge on lane y={lane_y}.")
        lines.append("Keeps protection parts in the same inward chain.")
    elif pattern_type == "debug_access_cluster":
        if previous_ref:
            lines.append(f"Clustered near {previous_ref} for edge access.")
        else:
            lines.append(f"Snaps to the {edge} board edge on lane y={lane_y}.")
        lines.append("Keeps reset and boot helpers adjacent to the debug entry.")
    elif pattern_type in {"edge_connector", "indicator_cluster"}:
        lines.append(f"Snaps to the {edge} board edge on lane y={lane_y}.")
        lines.append("Keeps the part reachable from the board perimeter.")
    elif pattern_type in {"analog_island", "rf_island"}:
        lines.append(f"Placed inside the {region} island region.")
        lines.append("Keeps this block isolated from the noisier areas.")
    elif pattern_type == "rf_keepout_island":
        lines.append("Placed around a reserved RF keepout region.")
        lines.append("Uses precomputed slots that avoid the reserved box.")
    elif pattern_type == "diff_pair_adjacency":
        lines.append("Keeps the pair adjacent and aligned in the same local zone.")
        lines.append("Searches nearby grid cells to avoid overlap.")
    else:
        lines.append("Placed by the generic search-based fallback.")

    lines.append(f"Final box: ({placement.x}, {placement.y}) size {placement.w}x{placement.h} grid.")
    if score is not None:
        lines.append(f"Solver score: {score}.")
    if candidate_count is not None:
        lines.append(f"Feasible candidates: {candidate_count}.")
    if candidate_reason:
        lines.append(f"Chosen candidate: {candidate_reason}.")
    if score_breakdown:
        score_bits = ", ".join(f"{key}={value}" for key, value in score_breakdown.items())
        lines.append(f"Score breakdown: {score_bits}.")
    if rejected_summary:
        lines.append("Rejected candidates:")
        for item in rejected_summary[:4]:
            lines.append(f"- {item}")
    if comp.notes:
        lines.append(f"Component notes: {'; '.join(comp.notes[:2])}.")
    if base_x is not None and base_y is not None and pattern_type == "clock_ring" and ref == anchor_ref:
        lines.append(f"Configured fallback anchor: ({base_x}, {base_y}).")
    return lines


def wrap_lines(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(line, width=width) or [""])
    return wrapped


def build_components(payload: dict[str, Any], rules: LayoutLabRules) -> dict[str, ComponentSpec]:
    components: dict[str, ComponentSpec] = {}
    for item in payload.get("components", []):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref", "")).strip().upper()
        if not ref:
            continue
        components[ref] = ComponentSpec(
            ref=ref,
            role=str(item.get("role", "")).strip().lower(),
            grid_w=int(item.get("grid_w", 4)),
            grid_h=int(item.get("grid_h", 3)),
            clearance=int(item.get("clearance", 1)),
            pattern=str(item.get("pattern") or rules.role_defaults.get(str(item.get("role", "")).strip().lower(), "")).strip(),
            anchor_ref=str(item.get("anchor_ref", "")).strip().upper(),
            preferred_slot=str(item.get("preferred_slot", "")).strip(),
            edge=str(item.get("edge", "")).strip().lower(),
            lane_y=int(item.get("lane_y", 0)),
            region=str(item.get("region", "")).strip().lower(),
            notes=[str(note) for note in item.get("notes", []) if str(note)],
        )
    return components


def run_sandbox(scenario: dict[str, Any], rules: LayoutLabRules, out_dir: Path) -> dict[str, Any]:
    board_data = dict(rules.board_defaults)
    scenario_board = scenario.get("board", {})
    if isinstance(scenario_board, dict):
        board_data.update(scenario_board)
    width = int(board_data.get("width_mm", 120))
    height = int(board_data.get("height_mm", 90))
    margin = int(board_data.get("margin_mm", 4))
    board = BoardState(width=width, height=height, margin=margin)
    components = build_components(scenario, rules)
    patterns = scenario.get("patterns", [])
    if not isinstance(patterns, list):
        raise ValueError("patterns must be a list.")

    steps_dir = out_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    cursor: dict[str, int] = {}
    summary: list[dict[str, Any]] = []
    step = 1
    solver = ConstraintSearchPlacementSolver(board, components, rules, cursor)

    for pattern_item in patterns:
        if not isinstance(pattern_item, dict):
            continue
        pattern_name = str(pattern_item.get("name", "")).strip()
        pattern_type = str(pattern_item.get("type", "")).strip()
        template = pattern_template(rules, pattern_type)
        members = [str(item).strip().upper() for item in pattern_item.get("members", []) if str(item).strip()]
        if not members:
            continue
        anchor_ref = str(pattern_item.get("anchor_ref", template_string(template, "anchor_ref", ""))).strip().upper()
        if not anchor_ref and template_string(template, "anchor_from", "") == "first_member":
            anchor_ref = members[0]
        direction = str(pattern_item.get("direction", template_string(template, "direction", "right"))).strip().lower()
        edge = str(pattern_item.get("edge", template_string(template, "edge", "right"))).strip().lower()
        region = str(pattern_item.get("region", template_string(template, "region", "top_left"))).strip().lower()
        lane_y = int(pattern_item.get("lane_y", template_int(template, "lane_y", 0)))
        gap = int(pattern_item.get("gap", template_int(template, "gap", 2)))
        base_x = pattern_item.get("x", template.get("fallback_x"))
        base_y = pattern_item.get("y", template.get("fallback_y"))
        base_x_int = int(base_x) if isinstance(base_x, (int, float)) else None
        base_y_int = int(base_y) if isinstance(base_y, (int, float)) else None
        anchor = board.placements.get(anchor_ref) if anchor_ref else None
        previous: Placement | None = None

        if pattern_type in {"center_cluster", "boot_reset_cluster", "clock_ring"}:
            results, ordered_components = solver.solve_cluster_pattern(
                pattern_type,
                members,
                anchor_ref=anchor_ref,
                base_x=base_x_int if base_x_int is not None else None,
                base_y=base_y_int if base_y_int is not None else None,
                pattern_name=pattern_name,
            )

            def relation_builder(index: int, result: SolveStepResult, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                if index == 0:
                    return None
                return (all_results[0].ref, result.ref)

            def explanation_builder(index: int, result: SolveStepResult, comp: ComponentSpec, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                kw: dict[str, Any] = {}
                if index == 0 and base_x_int is not None and base_y_int is not None:
                    kw["base_x"] = base_x_int
                    kw["base_y"] = base_y_int
                if index > 0:
                    kw["anchor_ref"] = all_results[0].ref
                return kw

            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                relation_builder=relation_builder,
                explanation_kwargs_builder=explanation_builder,
            )
            summary.extend(entries)
            continue

        if pattern_type in {"power_chain", "signal_chain", "high_current_path"}:
            results, ordered_components = solver.solve_chain_pattern(
                pattern_type,
                members,
                direction=direction,
                lane_y=lane_y or (board.height // 2),
                gap=gap,
            )

            def relation_builder(index: int, result: SolveStepResult, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                if index == 0:
                    return None
                return (all_results[index - 1].ref, result.ref)

            def explanation_builder(index: int, result: SolveStepResult, comp: ComponentSpec, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                kw: dict[str, Any] = {"direction": direction, "lane_y": lane_y, "gap": gap}
                if index > 0:
                    kw["previous_ref"] = all_results[index - 1].ref
                return kw

            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                relation_builder=relation_builder,
                explanation_kwargs_builder=explanation_builder,
            )
            summary.extend(entries)
            continue

        if pattern_type == "power_entry_chain":
            results, ordered_components = solver.solve_power_entry_chain(
                pattern_type,
                members,
                lane_y=lane_y or (board.height // 2),
                gap=gap,
            )

            def relation_builder(index: int, result: SolveStepResult, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                if index == 0:
                    return None
                return (all_results[index - 1].ref, result.ref)

            def explanation_builder(index: int, result: SolveStepResult, comp: ComponentSpec, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                kw: dict[str, Any] = {"lane_y": lane_y, "gap": gap, "edge": "left"}
                if index > 0:
                    kw["previous_ref"] = all_results[index - 1].ref
                return kw

            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                relation_builder=relation_builder,
                explanation_kwargs_builder=explanation_builder,
            )
            summary.extend(entries)
            continue

        if pattern_type == "usb_interface_chain":
            results, ordered_components = solver.solve_usb_interface_chain(
                pattern_type,
                members,
                edge=edge,
                lane_y=lane_y or (board.height // 2),
                gap=gap,
            )

            def relation_builder(index: int, result: SolveStepResult, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                if index == 0:
                    return None
                return (all_results[index - 1].ref, result.ref)

            def explanation_builder(index: int, result: SolveStepResult, comp: ComponentSpec, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                kw: dict[str, Any] = {"edge": edge, "lane_y": lane_y, "gap": gap}
                if index > 0:
                    kw["previous_ref"] = all_results[index - 1].ref
                return kw

            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                relation_builder=relation_builder,
                explanation_kwargs_builder=explanation_builder,
            )
            summary.extend(entries)
            continue

        if pattern_type == "debug_access_cluster":
            results, ordered_components = solver.solve_debug_access_cluster(
                pattern_type,
                members,
                edge=edge,
                lane_y=lane_y or (board.height // 2),
                gap=gap,
            )

            def relation_builder(index: int, result: SolveStepResult, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                if index == 0:
                    return None
                return (all_results[index - 1].ref, result.ref)

            def explanation_builder(index: int, result: SolveStepResult, comp: ComponentSpec, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                kw: dict[str, Any] = {"edge": edge, "lane_y": lane_y, "gap": gap}
                if index > 0:
                    kw["previous_ref"] = all_results[index - 1].ref
                return kw

            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                relation_builder=relation_builder,
                explanation_kwargs_builder=explanation_builder,
            )
            summary.extend(entries)
            continue

        if pattern_type in {"edge_connector", "indicator_cluster"}:
            results, ordered_components = solver.solve_edge_sequence(
                pattern_type,
                members,
                edge=edge,
                lane_y=lane_y or (board.height // 2),
                gap=gap,
            )
            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                explanation_kwargs_builder=lambda *_args: {"edge": edge, "lane_y": lane_y, "gap": gap},
            )
            summary.extend(entries)
            continue

        if pattern_type in {"analog_island", "rf_island"}:
            results, ordered_components = solver.solve_island_sequence(
                pattern_type,
                members,
                region=region,
            )
            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                explanation_kwargs_builder=lambda *_args: {"region": region},
            )
            summary.extend(entries)
            continue

        if pattern_type == "rf_keepout_island":
            results, ordered_components = solver.solve_rf_keepout_sequence(
                pattern_type,
                members,
            )
            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                explanation_kwargs_builder=lambda *_args: {"region": "rf_keepout"},
            )
            summary.extend(entries)
            continue

        if pattern_type == "diff_pair_adjacency":
            results, ordered_components = solver.solve_diff_pair_sequence(
                pattern_type,
                members,
            )

            def relation_builder(index: int, result: SolveStepResult, comps: list[ComponentSpec], all_results: list[SolveStepResult], _: BoardState):
                if index == 0:
                    return None
                return (all_results[index - 1].ref, result.ref)

            entries, step = record_solved_steps(
                board=board,
                steps_dir=steps_dir,
                pattern_name=pattern_name,
                pattern_type=pattern_type,
                template=template,
                rules=rules,
                components=ordered_components,
                results=results,
                step_start=step,
                relation_builder=relation_builder,
            )
            summary.extend(entries)
            continue

        raise ValueError(f"Unsupported pattern type: {pattern_type}")

    render_svg(board, out_dir / "final.svg", title="layout sandbox / final")
    (out_dir / "layout-summary.json").write_text(
        json.dumps(
            {
                "board": asdict(board),
                "placements": [asdict(item) for item in board.placements.values()],
                "steps": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_report_markdown(out_dir, scenario, board, summary)
    return {
        "board": asdict(board),
        "placements": [asdict(item) for item in board.placements.values()],
        "steps": summary,
    }


def write_report_markdown(out_dir: Path, scenario: dict[str, Any], board: BoardState, summary: list[dict[str, Any]]) -> None:
    from collections import Counter

    pattern_counts = Counter(str(step.get("pattern", "")).strip() for step in summary if str(step.get("pattern", "")).strip())
    reason_counts: Counter[str] = Counter()
    score_values: list[int] = []
    for step in summary:
        solver = step.get("solver", {})
        if isinstance(solver, dict):
            score = solver.get("score")
            if isinstance(score, int):
                score_values.append(score)
            rejected_summary = solver.get("rejected_summary", [])
            if isinstance(rejected_summary, list):
                for item in rejected_summary:
                    text = str(item)
                    if ":" in text:
                        key, value = text.rsplit(":", 1)
                        key = key.strip()
                        try:
                            count = int(value.strip())
                        except ValueError:
                            count = 1
                        reason_counts[key] += count
                    elif text.strip():
                        reason_counts[text.strip()] += 1

    avg_score = round(sum(score_values) / len(score_values), 2) if score_values else 0
    title = str(scenario.get("name", "Layout Lab")).strip() or "Layout Lab"
    lines: list[str] = []
    lines.append(f"# {title} 测试报告")
    lines.append("")
    lines.append("## 基本信息")
    lines.append(f"- 板子尺寸：{board.width}mm x {board.height}mm")
    lines.append(f"- 安全边距：{board.margin}mm")
    lines.append(f"- 元件数量：{len(board.placements)}")
    lines.append(f"- 步骤数量：{len(summary)}")
    lines.append(f"- 平均求解分数：{avg_score}")
    lines.append("")
    lines.append("## 模式分布")
    if pattern_counts:
        for pattern, count in pattern_counts.most_common():
            lines.append(f"- {pattern}：{count}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 最终排布")
    lines.append("")
    lines.append("| 元件 | 模式 | X | Y | 宽 | 高 | 分数 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for step in summary:
        placement = step.get("placement", {})
        solver = step.get("solver", {})
        lines.append(
            "| {ref} | {pattern} | {x} | {y} | {w} | {h} | {score} |".format(
                ref=str(step.get("ref", "")),
                pattern=str(step.get("pattern", "")),
                x=placement.get("x", ""),
                y=placement.get("y", ""),
                w=placement.get("w", ""),
                h=placement.get("h", ""),
                score=solver.get("score", ""),
            )
        )
    lines.append("")
    lines.append("## 主要失败原因")
    if reason_counts:
        for reason, count in reason_counts.most_common(10):
            lines.append(f"- {reason}：{count}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 输出文件")
    lines.append(f"- [最终图](./final.svg)")
    lines.append(f"- [汇总 JSON](./layout-summary.json)")
    lines.append(f"- [步骤图目录](./steps/)")
    lines.append(f"- [步骤总览](./steps.html)")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the standalone PCB layout sandbox.")
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Path to a scenario JSON file.",
    )
    parser.add_argument(
        "--roles",
        type=Path,
        default=None,
        help="Path to a roles JSON file. Defaults to examples/layout-lab/roles.json.",
    )
    parser.add_argument(
        "--patterns",
        type=Path,
        default=None,
        help="Path to a patterns JSON file. Defaults to examples/layout-lab/patterns.json.",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Legacy compatibility path for the old combined rules JSON file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Directory for SVG step images and summary JSON.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    rules = load_rules(args.roles, args.patterns, args.rules)
    global ACTIVE_RULES
    ACTIVE_RULES = rules
    scenario = load_scenario(args.scenario)
    result = run_sandbox(scenario, rules, args.out)
    print(json.dumps(
        {
            "placements": len(result["placements"]),
            "steps": len(result["steps"]),
            "output": str(args.out),
        },
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

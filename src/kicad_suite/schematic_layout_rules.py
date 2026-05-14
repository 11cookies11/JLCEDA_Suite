#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .env_utils import env


RULES_SCHEMA_VERSION = 'layout-rules.v1'
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class BlockLayoutRule:
    role_to_block: dict[str, str]
    block_order: list[str]
    role_match_rules: list[dict[str, Any]] = field(default_factory=list)
    block_pitch_x: int = 320
    block_origin_y: int = 240
    slot_pitch_y: int = 140


@dataclass
class PinAnchorRule:
    keyword_to_side: dict[str, str]
    side_offset: dict[str, tuple[int, int]]


@dataclass
class NetClassRule:
    net_name_patterns: dict[str, str]
    class_lane_y_offset: dict[str, int]
    class_lane_step: int = 30


@dataclass
class TopologyRule:
    required_role_edges: list[tuple[str, str]]
    preferred_net_flow: list[str]


@dataclass
class QualityRule:
    max_component_span_x: int = 1400
    min_component_pitch_x: int = 80
    min_component_pitch_y: int = 60
    max_net_port_cluster_height: int = 520


@dataclass
class LayoutRuleSet:
    schema_version: str
    block_layout: BlockLayoutRule
    pin_anchor: PinAnchorRule
    net_class: NetClassRule
    topology: TopologyRule
    quality: QualityRule


def build_default_layout_rules() -> LayoutRuleSet:
    rules = LayoutRuleSet(
        schema_version=RULES_SCHEMA_VERSION,
        block_layout=BlockLayoutRule(
            role_to_block={
                'input_protection': 'input',
                'input_capacitor': 'input',
                'connector': 'input',
                'buck_regulator': 'power_stage',
                'inductor': 'power_stage',
                'output_capacitor': 'output',
                'feedback_resistor_top': 'feedback',
                'feedback_resistor_bottom': 'feedback',
                'current_limit_resistor': 'power_stage',
                'indicator': 'output',
                'esp32_c3_module': 'mcu',
                'esp32_c3_bare_chip_qfn32': 'mcu',
                'rp2040_mcu': 'mcu',
                'rp2040_qfn56': 'mcu',
                'qspi': 'memory',
                'qspi_flash': 'memory',
                'chip_en_pullup_resistor': 'reset',
                'chip_en_reset_capacitor': 'reset',
                'reset_button': 'reset',
                'gpio9_boot_pullup_resistor': 'boot',
                'boot_button': 'boot',
                'gpio8_strap_pullup_resistor': 'strap',
                'crystal_12mhz': 'crystal',
                'crystal_40mhz': 'crystal',
                'xtal': 'crystal',
                'xtal_load_capacitor': 'crystal',
                'rf_series_matching_inductor': 'rf',
                'rf_shunt_matching_capacitor': 'rf',
                'antenna_connector': 'rf',
                'uart_programming_header': 'io',
                'usb_connector': 'io',
                'ldo_regulator': 'power',
                'ldo_input_capacitor': 'power',
                'ldo_output_capacitor': 'power',
                'led_current_limit_resistor': 'indicator',
                'power_indicator': 'indicator',
                'vdd3p3_bulk_capacitor': 'power',
                'vdd3p3_decoupling_capacitor': 'power',
            },
            block_order=['input', 'power', 'reset', 'mcu', 'memory', 'crystal', 'boot', 'io', 'indicator', 'power_stage', 'output', 'feedback', 'strap', 'rf'],
        ),
        pin_anchor=PinAnchorRule(
            keyword_to_side={
                'VIN': 'left',
                'EN': 'left',
                'SW': 'right',
                'VOUT': 'right',
                'FB': 'right',
                'GND': 'bottom',
                'PGND': 'bottom',
                'AGND': 'bottom',
            },
            side_offset={
                'left': (-220, 0),
                'right': (220, 0),
                'top': (0, 120),
                'bottom': (0, -120),
            },
        ),
        net_class=NetClassRule(
            net_name_patterns={
                'VIN': 'power',
                'VCC': 'power',
                'VDD': 'power',
                '+': 'power',
                'GND': 'ground',
                'FB': 'feedback',
                'COMP': 'feedback',
                'SW': 'switching',
            },
            class_lane_y_offset={
                'power': 40,
                'ground': 70,
                'switching': 100,
                'feedback': 130,
                'signal': 160,
            },
        ),
        topology=TopologyRule(
            required_role_edges=[
                ('input_capacitor', 'buck_regulator'),
                ('buck_regulator', 'inductor'),
                ('inductor', 'output_capacitor'),
                ('output_capacitor', 'feedback_resistor_top'),
                ('feedback_resistor_bottom', 'buck_regulator'),
            ],
            preferred_net_flow=['VIN_5V', 'SW', '+3V3', 'FB', 'GND'],
        ),
        quality=QualityRule(),
    )
    apply_layout_profile_rule_overrides(rules)
    return rules


def _load_layout_profile_config() -> dict[str, Any]:
    path = Path(env('KICAD_LAYOUT_PROFILES_FILE', str(REPO_ROOT / 'config' / 'kicad-layout-profiles.json')))
    if not path.exists():
        return {}
    try:
        with path.open('r', encoding='utf-8') as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def apply_layout_profile_rule_overrides(rules: LayoutRuleSet) -> None:
    defaults = _load_layout_profile_config().get('default', {})
    if not isinstance(defaults, dict):
        return

    block_order = defaults.get('block_order')
    if isinstance(block_order, list):
        merged_order = [str(item) for item in block_order if str(item)]
        for block in rules.block_layout.block_order:
            if block not in merged_order:
                merged_order.append(block)
        rules.block_layout.block_order = merged_order

    role_to_block = defaults.get('role_to_block')
    if isinstance(role_to_block, dict):
        for role, block in role_to_block.items():
            if str(role) and str(block):
                rules.block_layout.role_to_block[str(role)] = str(block)

    role_match_rules = defaults.get('role_match_rules')
    if isinstance(role_match_rules, list):
        rules.block_layout.role_match_rules = [item for item in role_match_rules if isinstance(item, dict)]


def _normalize_net_name(value: str) -> str:
    return str(value or '').strip().upper()


def _classify_net(net_name: str, rules: NetClassRule) -> str:
    normalized = _normalize_net_name(net_name)
    for pattern, net_class in rules.net_name_patterns.items():
        if pattern in normalized:
            return net_class
    return 'signal'


def _extract_member_pin(member: str) -> tuple[str, str]:
    token = str(member or '')
    if '.' not in token:
        return token, ''
    ref, pin = token.split('.', 1)
    return ref, pin.upper()


def _resolve_pin_side(pin_keyword: str, rules: PinAnchorRule) -> str:
    for keyword, side in rules.keyword_to_side.items():
        if keyword in pin_keyword:
            return side
    return 'right'


def _role_of_component(component: dict[str, Any]) -> str:
    return str(component.get('role', '') or '')


def _block_of_role(role: str, rules: BlockLayoutRule) -> str:
    return _resolve_wiring_block(role, rules)


_WIRING_SUFFIXES = sorted(
    [
        '_series_matching_inductor',
        '_shunt_matching_capacitor',
        '_current_limit_resistor',
        '_output_capacitor',
        '_input_capacitor',
        '_decoupling_capacitor',
        '_load_capacitor',
        '_pullup_resistor',
        '_reset_capacitor',
        '_bulk_capacitor',
        '_resistor',
        '_capacitor',
        '_inductor',
        '_regulator',
        '_button',
        '_connector',
        '_header',
    ],
    key=len,
    reverse=True,
)


def _resolve_wiring_block(role: str, rules: BlockLayoutRule) -> str:
    if role in rules.role_to_block:
        return rules.role_to_block[role]
    for rule in rules.role_match_rules:
        block = str(rule.get('block', '')).strip()
        if not block:
            continue
        any_contains = [str(item).lower() for item in rule.get('any_contains', []) if str(item)] if isinstance(rule.get('any_contains', []), list) else []
        all_contains = [str(item).lower() for item in rule.get('all_contains', []) if str(item)] if isinstance(rule.get('all_contains', []), list) else []
        if any_contains and not any(token in role for token in any_contains):
            continue
        if all_contains and not all(token in role for token in all_contains):
            continue
        if any_contains or all_contains:
            return block
    best_prefix = ''
    best_len = 0
    for suffix in _WIRING_SUFFIXES:
        if role.endswith(suffix) and len(suffix) > best_len:
            prefix = role[:-len(suffix)]
            if prefix:
                best_prefix = prefix
                best_len = len(suffix)
    if best_prefix:
        if best_prefix in rules.role_to_block:
            return rules.role_to_block[best_prefix]
        return best_prefix
    return role


def _index_by_ref(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for component in components:
        ref = str(component.get('ref', '') or '')
        if ref:
            output[ref] = component
    return output


def _compute_net_ports(
    nets: list[dict[str, Any]],
    placements: dict[str, dict[str, Any]],
    origin_x: int,
    origin_y: int,
    block_rule: BlockLayoutRule,
    anchor_rule: PinAnchorRule,
    net_rule: NetClassRule,
) -> list[dict[str, Any]]:
    net_ports: list[dict[str, Any]] = []
    lane_counters: dict[str, int] = {}
    anchor_side_counters: dict[str, int] = {}
    for net in nets:
        net_name = str(net.get('name', '') or '')
        if not net_name:
            continue
        members = [str(item) for item in net.get('members', []) if isinstance(item, str)]
        net_class = _classify_net(net_name, net_rule)
        lane_index = lane_counters.get(net_class, 0)
        lane_counters[net_class] = lane_index + 1

        anchor_ref = ''
        anchor_pin = ''
        for member in members:
            ref, pin = _extract_member_pin(member)
            if ref in placements and pin:
                anchor_ref = ref
                anchor_pin = pin
                break

        if anchor_ref and anchor_pin:
            anchor_pos = placements[anchor_ref]
            side = _resolve_pin_side(anchor_pin, anchor_rule)
            dx, dy = anchor_rule.side_offset.get(side, (220, 0))
            side_key = f'{anchor_ref}:{side}'
            side_index = anchor_side_counters.get(side_key, 0)
            anchor_side_counters[side_key] = side_index + 1
            if side in ('left', 'right'):
                x = int(anchor_pos['x'] + dx)
                y = int(anchor_pos['y'] + dy + side_index * net_rule.class_lane_step)
            else:
                x = int(anchor_pos['x'] + dx + side_index * net_rule.class_lane_step)
                y = int(anchor_pos['y'] + dy)
        else:
            x = int(origin_x + len(block_rule.block_order) * block_rule.block_pitch_x + 120)
            y = int(origin_y + net_rule.class_lane_y_offset.get(net_class, 160) + lane_index * net_rule.class_lane_step)

        net_ports.append(
            {
                'netName': net_name,
                'x': x,
                'y': y,
                'direction': 'BI',
                'netClass': net_class,
                'anchorRef': anchor_ref,
                'anchorPin': anchor_pin,
            }
        )
    return net_ports


def _compile_layout_context_rules(
    components: list[dict[str, Any]],
    nets: list[dict[str, Any]],
    origin_x: int,
    origin_y: int,
    rules: LayoutRuleSet | None = None,
) -> dict[str, Any]:
    active_rules = rules or build_default_layout_rules()
    block_rule = active_rules.block_layout
    anchor_rule = active_rules.pin_anchor
    net_rule = active_rules.net_class

    grouped: dict[str, list[dict[str, Any]]] = {block: [] for block in block_rule.block_order}
    grouped.setdefault('io', [])
    for component in components:
        block = _block_of_role(_role_of_component(component), block_rule)
        grouped.setdefault(block, [])
        grouped[block].append(component)

    placements: dict[str, dict[str, Any]] = {}
    for block_index, block_name in enumerate(block_rule.block_order):
        block_items = grouped.get(block_name, [])
        block_x = origin_x + (block_index * block_rule.block_pitch_x)
        block_y = origin_y if block_name != 'io' else origin_y + 80
        for slot_index, component in enumerate(block_items):
            ref = str(component.get('ref', '') or '')
            if not ref:
                continue
            placements[ref] = {
                'x': block_x,
                'y': block_y + (slot_index * block_rule.slot_pitch_y),
                'block': block_name,
                'slot': slot_index,
                'role': _role_of_component(component),
            }

    component_map = _index_by_ref(components)
    net_ports = _compute_net_ports(
        nets=nets,
        placements=placements,
        origin_x=origin_x,
        origin_y=origin_y,
        block_rule=block_rule,
        anchor_rule=anchor_rule,
        net_rule=net_rule,
    )

    net_edges: list[dict[str, Any]] = []
    for net in nets:
        net_name = str(net.get('name', '') or '')
        members = [str(item) for item in net.get('members', []) if isinstance(item, str)]
        for index in range(len(members) - 1):
            ref_a, pin_a = _extract_member_pin(members[index])
            ref_b, pin_b = _extract_member_pin(members[index + 1])
            role_a = _role_of_component(component_map.get(ref_a, {}))
            role_b = _role_of_component(component_map.get(ref_b, {}))
            net_edges.append(
                {
                    'net': net_name,
                    'from': members[index],
                    'to': members[index + 1],
                    'fromRole': role_a,
                    'toRole': role_b,
                    'fromPin': pin_a,
                    'toPin': pin_b,
                }
            )

    span_x = 0
    if placements:
        xs = [int(item['x']) for item in placements.values()]
        span_x = max(xs) - min(xs)
    net_height = 0
    if net_ports:
        ys = [int(item['y']) for item in net_ports]
        net_height = max(ys) - min(ys)

    quality = {
        'componentSpanX': span_x,
        'netPortClusterHeight': net_height,
        'checks': [
            {
                'name': 'component_span_x',
                'pass': span_x <= active_rules.quality.max_component_span_x,
                'limit': active_rules.quality.max_component_span_x,
                'value': span_x,
            },
            {
                'name': 'net_port_cluster_height',
                'pass': net_height <= active_rules.quality.max_net_port_cluster_height,
                'limit': active_rules.quality.max_net_port_cluster_height,
                'value': net_height,
            },
        ],
    }

    return {
        'schemaVersion': RULES_SCHEMA_VERSION,
        'engine': 'rules',
        'rules': asdict(active_rules),
        'componentPlacements': placements,
        'netPortPlacements': net_ports,
        'topologyEdges': net_edges,
        'quality': quality,
    }


def _estimate_node_dimensions(component: dict[str, Any], symbol_dimensions: dict[str, dict[str, float]] | None) -> tuple[float, float]:
    """Return (width, height) for a component's ELK node.

    Uses real symbol bounding-box data when available (from library pin
    positions).  Falls back to a pin-count heuristic when the symbol
    hasn't been fetched, and ultimately to a safe 160×90 default.
    """
    ref = str(component.get('ref', '') or '')
    if symbol_dimensions and ref in symbol_dimensions:
        dims = symbol_dimensions[ref]
        w = float(dims.get('width', 0) or 0)
        h = float(dims.get('height', 0) or 0)
        if w > 0 and h > 0:
            return w, h

    # Pin-count heuristic fallback – better than uniform 160×90
    selected = component.get('selected_part') if isinstance(component.get('selected_part'), dict) else None
    pin_count = 0
    if selected:
        pin_count = int(selected.get('pin_count', 0) or 0)
    if not pin_count:
        pin_count = int(component.get('pin_count', 0) or 0)

    if pin_count <= 2:
        return 60, 80
    if pin_count <= 4:
        return 80, 100
    if pin_count <= 8:
        return 120, 130
    if pin_count <= 16:
        return 160, 170
    if pin_count > 16:
        return 210, 210

    return 160, 90


def _build_elk_graph(
    components: list[dict[str, Any]],
    nets: list[dict[str, Any]],
    rules: LayoutRuleSet,
    symbol_dimensions: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for component in components:
        ref = str(component.get('ref', '') or '')
        if not ref:
            continue
        role = _role_of_component(component)
        block = _block_of_role(role, rules.block_layout)
        width, height = _estimate_node_dimensions(component, symbol_dimensions)
        nodes.append(
            {
                'id': ref,
                'width': width,
                'height': height,
                'labels': [{'text': ref}],
                'layoutOptions': {
                    # Use the existing block info as a weak ordering hint.
                    'org.eclipse.elk.layered.layering.layerConstraint': 'NONE',
                    'org.eclipse.elk.priority': str(rules.block_layout.block_order.index(block))
                    if block in rules.block_layout.block_order
                    else '99',
                },
            }
        )

    edge_index = 0
    for net in nets:
        members = [str(item) for item in net.get('members', []) if isinstance(item, str)]
        for index in range(len(members) - 1):
            src_ref, src_pin = _extract_member_pin(members[index])
            dst_ref, dst_pin = _extract_member_pin(members[index + 1])
            if not src_ref or not dst_ref:
                continue
            edges.append(
                {
                    'id': f'e{edge_index}-{net.get("name", "")}',
                    'sources': [src_ref],
                    'targets': [dst_ref],
                }
            )
            edge_index += 1

    return {
        'id': 'root',
        'layoutOptions': {
            'org.eclipse.elk.algorithm': 'layered',
            'org.eclipse.elk.direction': 'RIGHT',
            'org.eclipse.elk.spacing.nodeNode': '60',
            'org.eclipse.elk.layered.spacing.nodeNodeBetweenLayers': '90',
            'org.eclipse.elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
        },
        'children': nodes,
        'edges': edges,
    }


def _run_elk_layout(graph_payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parent / 'elk_layout_runner.mjs'
    if not script_path.exists():
        raise RuntimeError('ELK runner script is missing.')

    process = subprocess.run(
        ['node', str(script_path)],
        input=json.dumps(graph_payload),
        text=True,
        capture_output=True,
        timeout=max(1, timeout_ms) / 1000.0,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or 'ELK runner failed.'
        raise RuntimeError(message)
    return json.loads(process.stdout)


def _collect_elk_nodes(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    stack: list[dict[str, Any]] = [tree]
    while stack:
        item = stack.pop()
        node_id = str(item.get('id', '') or '')
        if node_id and node_id != 'root' and 'x' in item and 'y' in item:
            output[node_id] = item
        for child in item.get('children', []) if isinstance(item.get('children', []), list) else []:
            if isinstance(child, dict):
                stack.append(child)
    return output


def _compile_layout_context_elk(
    components: list[dict[str, Any]],
    nets: list[dict[str, Any]],
    origin_x: int,
    origin_y: int,
    rules: LayoutRuleSet,
    symbol_dimensions: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    graph = _build_elk_graph(components, nets, rules, symbol_dimensions)
    timeout_ms = int(os.environ.get('BRIDGE_ELK_TIMEOUT_MS', '2000') or '2000')
    layout_tree = _run_elk_layout(graph, timeout_ms=timeout_ms)
    elk_nodes = _collect_elk_nodes(layout_tree)

    # Start from rules result for net-port strategy, then override component XY from ELK.
    base = _compile_layout_context_rules(components, nets, origin_x, origin_y, rules)
    placements = base.get('componentPlacements', {})
    for ref, placement in list(placements.items()):
        node = elk_nodes.get(ref, {})
        if node:
            placement['x'] = int(origin_x + float(node.get('x', 0)))
            placement['y'] = int(origin_y + float(node.get('y', 0)))
            placement['engine'] = 'elk'
    base['componentPlacements'] = placements
    base['engine'] = 'elk'
    base['elk'] = {
        'nodeCount': len(elk_nodes),
    }

    # Recompute net port positions based on the updated ELK component locations.
    if elk_nodes:
        base['netPortPlacements'] = _compute_net_ports(
            nets=nets,
            placements=placements,
            origin_x=origin_x,
            origin_y=origin_y,
            block_rule=rules.block_layout,
            anchor_rule=rules.pin_anchor,
            net_rule=rules.net_class,
        )

    return base


def compile_layout_context(
    components: list[dict[str, Any]],
    nets: list[dict[str, Any]],
    origin_x: int,
    origin_y: int,
    rules: LayoutRuleSet | None = None,
    symbol_dimensions: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    active_rules = rules or build_default_layout_rules()
    engine = str(os.environ.get('BRIDGE_LAYOUT_ENGINE', 'elk') or 'elk').strip().lower()
    if engine not in ('elk', 'rules'):
        engine = 'elk'
    if engine == 'rules':
        return _compile_layout_context_rules(components, nets, origin_x, origin_y, active_rules)
    try:
        return _compile_layout_context_elk(components, nets, origin_x, origin_y, active_rules, symbol_dimensions)
    except Exception as error:  # noqa: BLE001
        fallback = _compile_layout_context_rules(components, nets, origin_x, origin_y, active_rules)
        fallback['engine'] = 'rules'
        fallback['engineFallback'] = f'elk_failed:{error}'
        return fallback

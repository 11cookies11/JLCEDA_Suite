#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import venv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from log_utils import setup_logging

logger = setup_logging()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_now() -> str:
    return utc_now().isoformat()


def write_json(status_code: int, body: Any) -> web.Response:
    return web.json_response(body, status=status_code)


def get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_cache_venv_dir() -> Path:
    return Path.home() / '.cache' / 'jlceda-suite-python-server'


def get_venv_python_path(venv_dir: Path) -> Path:
    if os.name == 'nt':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python'


def ensure_runtime_dependencies() -> None:
    try:
        __import__('aiohttp')
        return
    except ImportError:
        pass

    repo_root = get_repo_root()
    requirements_file = repo_root / 'requirements-server.txt'
    if not requirements_file.exists():
        raise RuntimeError(f'Missing requirements file: {requirements_file}')

    venv_dir = get_cache_venv_dir()
    python_path = get_venv_python_path(venv_dir)
    if not python_path.exists():
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        builder.create(str(venv_dir))

    probe = subprocess.run(
        [str(python_path), '-c', 'import aiohttp'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        subprocess.check_call([
            str(python_path),
            '-m',
            'pip',
            'install',
            '--upgrade',
            'pip',
        ])
        subprocess.check_call([
            str(python_path),
            '-m',
            'pip',
            'install',
            '-r',
            str(requirements_file),
        ])
    os.execv(
        str(python_path),
        [
            str(python_path),
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
    )


ensure_runtime_dependencies()

from aiohttp import WSMsgType, web


@dataclass
class BridgeSession:
    registration: dict[str, Any]
    websocket: web.WebSocketResponse
    connected_at: datetime
    last_seen_at: datetime


@dataclass
class PendingBridgeRequest:
    client_id: str
    future: asyncio.Future[dict[str, Any]]
    timeout_handle: asyncio.TimerHandle
    command_name: str
    started_at: datetime


@dataclass
class RequestHistoryEntry:
    request_id: str
    client_id: str
    command_name: str
    status: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    summary: str = ''
    error: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'requestId': self.request_id,
            'clientId': self.client_id,
            'commandName': self.command_name,
            'status': self.status,
            'startedAt': self.started_at.isoformat(),
            'completedAt': self.completed_at.isoformat(),
            'durationMs': self.duration_ms,
            'summary': self.summary,
            'error': self.error,
        }


@dataclass(frozen=True)
class RuleProfile:
    name: str
    description: str
    schematic_component_clearance: int
    schematic_wire_clearance: int
    schematic_placement_component_clearance: int
    schematic_placement_wire_clearance: int
    schematic_label_placement_step_floor: int
    schematic_label_gap_min: int
    schematic_label_gap_max: int
    schematic_label_clearance: int
    schematic_wire_label_clearance: int
    schematic_power_spacing: int
    schematic_power_column_count: int
    schematic_power_row_spacing_factor: float
    schematic_label_gap_ratio: float
    schematic_placement_step: int
    schematic_placement_max_ring: int
    schematic_power_keywords: list[str]
    schematic_power_role_keywords: dict[str, list[str]]
    schematic_power_connector_offset_x: int
    schematic_power_connector_offset_y: int
    schematic_power_input_capacitor_offset_x: int
    schematic_power_input_capacitor_offset_y: int
    schematic_power_regulator_offset_x: int
    schematic_power_regulator_offset_y: int
    schematic_power_output_capacitor_offset_x: int
    schematic_power_output_capacitor_offset_y: int
    schematic_power_indicator_offset_x: int
    schematic_power_indicator_offset_y: int
    schematic_power_supporting_part_offset_x: int
    schematic_power_supporting_part_offset_y: int
    pcb_component_clearance: int
    pcb_track_clearance: int
    pcb_label_clearance: int
    pcb_board_edge_clearance: int
    pcb_label_horizontal_offset_base: int
    pcb_label_horizontal_offset_max: int
    pcb_label_vertical_offset_base: int
    pcb_label_vertical_offset_max: int

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'schematic': {
                'componentClearance': self.schematic_component_clearance,
                'wireClearance': self.schematic_wire_clearance,
                'placementComponentClearance': self.schematic_placement_component_clearance,
                'placementWireClearance': self.schematic_placement_wire_clearance,
                'labelPlacementStepFloor': self.schematic_label_placement_step_floor,
                'labelGapMin': self.schematic_label_gap_min,
                'labelGapMax': self.schematic_label_gap_max,
                'labelClearance': self.schematic_label_clearance,
                'wireLabelClearance': self.schematic_wire_label_clearance,
                'powerSpacing': self.schematic_power_spacing,
                'powerColumnCount': self.schematic_power_column_count,
                'powerRowSpacingFactor': self.schematic_power_row_spacing_factor,
                'labelGapRatio': self.schematic_label_gap_ratio,
                'placementStep': self.schematic_placement_step,
                'placementMaxRing': self.schematic_placement_max_ring,
                'powerKeywords': self.schematic_power_keywords,
                'powerRoleKeywords': self.schematic_power_role_keywords,
                'powerRoleOffsets': {
                    'connector': {
                        'x': self.schematic_power_connector_offset_x,
                        'y': self.schematic_power_connector_offset_y,
                    },
                    'inputCapacitor': {
                        'x': self.schematic_power_input_capacitor_offset_x,
                        'y': self.schematic_power_input_capacitor_offset_y,
                    },
                    'regulator': {
                        'x': self.schematic_power_regulator_offset_x,
                        'y': self.schematic_power_regulator_offset_y,
                    },
                    'outputCapacitor': {
                        'x': self.schematic_power_output_capacitor_offset_x,
                        'y': self.schematic_power_output_capacitor_offset_y,
                    },
                    'indicator': {
                        'x': self.schematic_power_indicator_offset_x,
                        'y': self.schematic_power_indicator_offset_y,
                    },
                    'supportingPart': {
                        'x': self.schematic_power_supporting_part_offset_x,
                        'y': self.schematic_power_supporting_part_offset_y,
                    },
                },
            },
            'pcb': {
                'componentClearance': self.pcb_component_clearance,
                'trackClearance': self.pcb_track_clearance,
                'labelHorizontalOffsetBase': self.pcb_label_horizontal_offset_base,
                'labelHorizontalOffsetMax': self.pcb_label_horizontal_offset_max,
                'labelVerticalOffsetBase': self.pcb_label_vertical_offset_base,
                'labelVerticalOffsetMax': self.pcb_label_vertical_offset_max,
                'labelClearance': self.pcb_label_clearance,
                'boardEdgeClearance': self.pcb_board_edge_clearance,
            },
        }


def build_default_rule_profiles() -> dict[str, RuleProfile]:
    return {
        'default': RuleProfile(
            name='default',
            description='Balanced defaults for general schematic-first development.',
            schematic_component_clearance=80,
            schematic_wire_clearance=48,
            schematic_placement_component_clearance=48,
            schematic_placement_wire_clearance=40,
            schematic_label_placement_step_floor=64,
            schematic_label_gap_min=24,
            schematic_label_gap_max=56,
            schematic_label_clearance=110,
            schematic_wire_label_clearance=72,
            schematic_power_spacing=160,
            schematic_power_column_count=3,
            schematic_power_row_spacing_factor=0.7,
            schematic_label_gap_ratio=0.35,
            schematic_placement_step=40,
            schematic_placement_max_ring=8,
            schematic_power_keywords=['vin', 'vout', 'vcc', 'vdd', '3v3', '5v', 'gnd', 'reg', 'ldo', 'buck', 'boost', 'power', 'pwr', 'dc', 'usb'],
            schematic_power_role_keywords={
                'inputCapacitor': ['cap', 'decoupl'],
                'regulator': ['reg', 'ldo', 'buck', 'boost', 'ams1117', '1117'],
                'indicator': ['led', 'indicator'],
                'connector': ['conn', 'usb', 'jack', 'header'],
                'outputCapacitor': ['cap', 'bypass'],
                'supportingPart': ['support', 'aux', 'filter'],
            },
            schematic_power_connector_offset_x=-320,
            schematic_power_connector_offset_y=0,
            schematic_power_input_capacitor_offset_x=-160,
            schematic_power_input_capacitor_offset_y=-160,
            schematic_power_regulator_offset_x=0,
            schematic_power_regulator_offset_y=0,
            schematic_power_output_capacitor_offset_x=160,
            schematic_power_output_capacitor_offset_y=-160,
            schematic_power_indicator_offset_x=160,
            schematic_power_indicator_offset_y=160,
            schematic_power_supporting_part_offset_x=0,
            schematic_power_supporting_part_offset_y=160,
            pcb_component_clearance=120,
            pcb_track_clearance=70,
            pcb_label_horizontal_offset_base=28,
            pcb_label_horizontal_offset_max=64,
            pcb_label_vertical_offset_base=20,
            pcb_label_vertical_offset_max=48,
            pcb_label_clearance=90,
            pcb_board_edge_clearance=60,
        ),
        'compact': RuleProfile(
            name='compact',
            description='Tighter placement for dense schematic layouts.',
            schematic_component_clearance=64,
            schematic_wire_clearance=40,
            schematic_placement_component_clearance=40,
            schematic_placement_wire_clearance=32,
            schematic_label_placement_step_floor=56,
            schematic_label_gap_min=20,
            schematic_label_gap_max=48,
            schematic_label_clearance=96,
            schematic_wire_label_clearance=64,
            schematic_power_spacing=128,
            schematic_power_column_count=3,
            schematic_power_row_spacing_factor=0.6,
            schematic_label_gap_ratio=0.32,
            schematic_placement_step=32,
            schematic_placement_max_ring=8,
            schematic_power_keywords=['vin', 'vout', 'vcc', 'vdd', '3v3', '5v', 'gnd', 'reg', 'ldo', 'buck', 'boost', 'power', 'pwr', 'dc', 'usb'],
            schematic_power_role_keywords={
                'inputCapacitor': ['cap', 'decoupl'],
                'regulator': ['reg', 'ldo', 'buck', 'boost', 'ams1117', '1117'],
                'indicator': ['led', 'indicator'],
                'connector': ['conn', 'usb', 'jack', 'header'],
                'outputCapacitor': ['cap', 'bypass'],
                'supportingPart': ['support', 'aux', 'filter'],
            },
            schematic_power_connector_offset_x=-256,
            schematic_power_connector_offset_y=0,
            schematic_power_input_capacitor_offset_x=-128,
            schematic_power_input_capacitor_offset_y=-128,
            schematic_power_regulator_offset_x=0,
            schematic_power_regulator_offset_y=0,
            schematic_power_output_capacitor_offset_x=128,
            schematic_power_output_capacitor_offset_y=-128,
            schematic_power_indicator_offset_x=128,
            schematic_power_indicator_offset_y=128,
            schematic_power_supporting_part_offset_x=0,
            schematic_power_supporting_part_offset_y=128,
            pcb_component_clearance=96,
            pcb_track_clearance=56,
            pcb_label_horizontal_offset_base=24,
            pcb_label_horizontal_offset_max=56,
            pcb_label_vertical_offset_base=18,
            pcb_label_vertical_offset_max=40,
            pcb_label_clearance=72,
            pcb_board_edge_clearance=48,
        ),
        'power_safe': RuleProfile(
            name='power_safe',
            description='More conservative spacing around power blocks and PCB edges.',
            schematic_component_clearance=96,
            schematic_wire_clearance=56,
            schematic_placement_component_clearance=56,
            schematic_placement_wire_clearance=48,
            schematic_label_placement_step_floor=72,
            schematic_label_gap_min=28,
            schematic_label_gap_max=64,
            schematic_label_clearance=128,
            schematic_wire_label_clearance=80,
            schematic_power_spacing=192,
            schematic_power_column_count=3,
            schematic_power_row_spacing_factor=0.8,
            schematic_label_gap_ratio=0.38,
            schematic_placement_step=48,
            schematic_placement_max_ring=10,
            schematic_power_keywords=['vin', 'vout', 'vcc', 'vdd', '3v3', '5v', 'gnd', 'reg', 'ldo', 'buck', 'boost', 'power', 'pwr', 'dc', 'usb'],
            schematic_power_role_keywords={
                'inputCapacitor': ['cap', 'decoupl'],
                'regulator': ['reg', 'ldo', 'buck', 'boost', 'ams1117', '1117'],
                'indicator': ['led', 'indicator'],
                'connector': ['conn', 'usb', 'jack', 'header'],
                'outputCapacitor': ['cap', 'bypass'],
                'supportingPart': ['support', 'aux', 'filter'],
            },
            schematic_power_connector_offset_x=-384,
            schematic_power_connector_offset_y=0,
            schematic_power_input_capacitor_offset_x=-192,
            schematic_power_input_capacitor_offset_y=-192,
            schematic_power_regulator_offset_x=0,
            schematic_power_regulator_offset_y=0,
            schematic_power_output_capacitor_offset_x=192,
            schematic_power_output_capacitor_offset_y=-192,
            schematic_power_indicator_offset_x=192,
            schematic_power_indicator_offset_y=192,
            schematic_power_supporting_part_offset_x=0,
            schematic_power_supporting_part_offset_y=192,
            pcb_component_clearance=144,
            pcb_track_clearance=80,
            pcb_label_horizontal_offset_base=32,
            pcb_label_horizontal_offset_max=72,
            pcb_label_vertical_offset_base=24,
            pcb_label_vertical_offset_max=56,
            pcb_label_clearance=104,
            pcb_board_edge_clearance=72,
        ),
    }


def coerce_int(value: Any, fallback: int) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except Exception:
        return fallback


def load_rule_profiles(profile_file: Optional[str]) -> tuple[dict[str, RuleProfile], str]:
    default_profiles = build_default_rule_profiles()
    active_profile_name = 'default'

    candidate_path = Path(profile_file) if profile_file else get_repo_root() / 'config' / 'rule_profiles.json'
    if not candidate_path.exists():
        return default_profiles, active_profile_name

    try:
        with candidate_path.open('r', encoding='utf-8') as handle:
            raw_data = json.load(handle)
    except Exception:
        return default_profiles, active_profile_name

    if not isinstance(raw_data, dict):
        return default_profiles, active_profile_name

    loaded_profiles: dict[str, RuleProfile] = {}
    raw_profiles = raw_data.get('profiles')
    if isinstance(raw_profiles, dict):
        for profile_name, profile_data in raw_profiles.items():
            if not isinstance(profile_name, str) or not isinstance(profile_data, dict):
                continue

            schematic = profile_data.get('schematic') if isinstance(profile_data.get('schematic'), dict) else {}
            pcb = profile_data.get('pcb') if isinstance(profile_data.get('pcb'), dict) else {}
            loaded_profiles[profile_name] = RuleProfile(
                name=profile_name,
                description=str(profile_data.get('description', 'Custom rule profile.')),
                schematic_component_clearance=coerce_int(schematic.get('componentClearance'), 80),
                schematic_wire_clearance=coerce_int(schematic.get('wireClearance'), 48),
                schematic_placement_component_clearance=coerce_int(
                    schematic.get('placementComponentClearance'),
                    coerce_int(schematic.get('componentClearance'), 48),
                ),
                schematic_placement_wire_clearance=coerce_int(
                    schematic.get('placementWireClearance'),
                    coerce_int(schematic.get('wireClearance'), 40),
                ),
                schematic_label_placement_step_floor=coerce_int(schematic.get('labelPlacementStepFloor'), 64),
                schematic_label_gap_min=coerce_int(schematic.get('labelGapMin'), 24),
                schematic_label_gap_max=coerce_int(schematic.get('labelGapMax'), 56),
                schematic_label_clearance=coerce_int(schematic.get('labelClearance'), 110),
                schematic_wire_label_clearance=coerce_int(schematic.get('wireLabelClearance'), 72),
                schematic_power_spacing=coerce_int(schematic.get('powerSpacing'), 160),
                schematic_power_column_count=coerce_int(schematic.get('powerColumnCount'), 3),
                schematic_power_row_spacing_factor=float(schematic.get('powerRowSpacingFactor', 0.7) if isinstance(schematic.get('powerRowSpacingFactor', 0.7), (int, float)) else 0.7),
                schematic_label_gap_ratio=float(schematic.get('labelGapRatio', 0.35) if isinstance(schematic.get('labelGapRatio', 0.35), (int, float)) else 0.35),
                schematic_placement_step=coerce_int(schematic.get('placementStep'), 40),
                schematic_placement_max_ring=coerce_int(schematic.get('placementMaxRing'), 8),
                schematic_power_keywords=[str(value).strip().lower() for value in schematic.get('powerKeywords', ['vin', 'vout', 'vcc', 'vdd', '3v3', '5v', 'gnd', 'reg', 'ldo', 'buck', 'boost', 'power', 'pwr', 'dc', 'usb']) if str(value).strip()],
                schematic_power_role_keywords={
                    'inputCapacitor': [str(value).strip().lower() for value in (((schematic.get('powerRoleKeywords') or {}).get('inputCapacitor')) if isinstance(schematic.get('powerRoleKeywords'), dict) else ['cap', 'decoupl']) if str(value).strip()],
                    'regulator': [str(value).strip().lower() for value in (((schematic.get('powerRoleKeywords') or {}).get('regulator')) if isinstance(schematic.get('powerRoleKeywords'), dict) else ['reg', 'ldo', 'buck', 'boost', 'ams1117', '1117']) if str(value).strip()],
                    'indicator': [str(value).strip().lower() for value in (((schematic.get('powerRoleKeywords') or {}).get('indicator')) if isinstance(schematic.get('powerRoleKeywords'), dict) else ['led', 'indicator']) if str(value).strip()],
                    'connector': [str(value).strip().lower() for value in (((schematic.get('powerRoleKeywords') or {}).get('connector')) if isinstance(schematic.get('powerRoleKeywords'), dict) else ['conn', 'usb', 'jack', 'header']) if str(value).strip()],
                    'outputCapacitor': [str(value).strip().lower() for value in (((schematic.get('powerRoleKeywords') or {}).get('outputCapacitor')) if isinstance(schematic.get('powerRoleKeywords'), dict) else ['cap', 'bypass']) if str(value).strip()],
                    'supportingPart': [str(value).strip().lower() for value in (((schematic.get('powerRoleKeywords') or {}).get('supportingPart')) if isinstance(schematic.get('powerRoleKeywords'), dict) else ['support', 'aux', 'filter']) if str(value).strip()],
                },
                schematic_power_connector_offset_x=coerce_int((schematic.get('powerRoleOffsets') or {}).get('connector', {}).get('x') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('connector'), dict) else None, -320),
                schematic_power_connector_offset_y=coerce_int((schematic.get('powerRoleOffsets') or {}).get('connector', {}).get('y') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('connector'), dict) else None, 0),
                schematic_power_input_capacitor_offset_x=coerce_int((schematic.get('powerRoleOffsets') or {}).get('inputCapacitor', {}).get('x') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('inputCapacitor'), dict) else None, -160),
                schematic_power_input_capacitor_offset_y=coerce_int((schematic.get('powerRoleOffsets') or {}).get('inputCapacitor', {}).get('y') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('inputCapacitor'), dict) else None, -160),
                schematic_power_regulator_offset_x=coerce_int((schematic.get('powerRoleOffsets') or {}).get('regulator', {}).get('x') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('regulator'), dict) else None, 0),
                schematic_power_regulator_offset_y=coerce_int((schematic.get('powerRoleOffsets') or {}).get('regulator', {}).get('y') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('regulator'), dict) else None, 0),
                schematic_power_output_capacitor_offset_x=coerce_int((schematic.get('powerRoleOffsets') or {}).get('outputCapacitor', {}).get('x') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('outputCapacitor'), dict) else None, 160),
                schematic_power_output_capacitor_offset_y=coerce_int((schematic.get('powerRoleOffsets') or {}).get('outputCapacitor', {}).get('y') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('outputCapacitor'), dict) else None, -160),
                schematic_power_indicator_offset_x=coerce_int((schematic.get('powerRoleOffsets') or {}).get('indicator', {}).get('x') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('indicator'), dict) else None, 160),
                schematic_power_indicator_offset_y=coerce_int((schematic.get('powerRoleOffsets') or {}).get('indicator', {}).get('y') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('indicator'), dict) else None, 160),
                schematic_power_supporting_part_offset_x=coerce_int((schematic.get('powerRoleOffsets') or {}).get('supportingPart', {}).get('x') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('supportingPart'), dict) else None, 0),
                schematic_power_supporting_part_offset_y=coerce_int((schematic.get('powerRoleOffsets') or {}).get('supportingPart', {}).get('y') if isinstance(schematic.get('powerRoleOffsets'), dict) and isinstance((schematic.get('powerRoleOffsets') or {}).get('supportingPart'), dict) else None, 160),
                pcb_component_clearance=coerce_int(pcb.get('componentClearance'), 120),
                pcb_track_clearance=coerce_int(pcb.get('trackClearance'), 70),
                pcb_label_horizontal_offset_base=coerce_int(pcb.get('labelHorizontalOffsetBase'), 28),
                pcb_label_horizontal_offset_max=coerce_int(pcb.get('labelHorizontalOffsetMax'), 64),
                pcb_label_vertical_offset_base=coerce_int(pcb.get('labelVerticalOffsetBase'), 20),
                pcb_label_vertical_offset_max=coerce_int(pcb.get('labelVerticalOffsetMax'), 48),
                pcb_label_clearance=coerce_int(pcb.get('labelClearance'), 90),
                pcb_board_edge_clearance=coerce_int(pcb.get('boardEdgeClearance'), 60),
            )

    if loaded_profiles:
        default_profiles = loaded_profiles

    requested_profile = str(raw_data.get('activeProfile', 'default'))
    if requested_profile in default_profiles:
        active_profile_name = requested_profile

    return default_profiles, active_profile_name


class BridgeServer:
    def __init__(
        self,
        bridge_host: str,
        bridge_port: int,
        auth_token: str = '',
        request_timeout_ms: int = 15_000,
        control_host: str = '127.0.0.1',
        control_port: Optional[int] = None,
        control_token: str = '',
        rule_profiles: Optional[dict[str, RuleProfile]] = None,
        active_rule_profile_name: str = 'default',
    ) -> None:
        self.bridge_host = bridge_host
        self.bridge_port = bridge_port
        self.auth_token = auth_token
        self.request_timeout_ms = request_timeout_ms
        self.control_host = control_host
        self.control_port = control_port
        self.control_token = control_token
        self.rule_profiles = rule_profiles or build_default_rule_profiles()
        self.active_rule_profile_name = active_rule_profile_name if active_rule_profile_name in self.rule_profiles else 'default'

        self.sessions: dict[str, BridgeSession] = {}
        self.socket_clients: dict[int, str] = {}
        self.pending_requests: dict[str, PendingBridgeRequest] = {}
        self.request_history: list[RequestHistoryEntry] = []
        self.request_history_limit = 200
        self.server_started_at = utc_now()
        self._bridge_runner: web.AppRunner | None = None
        self._control_runner: web.AppRunner | None = None
        self._bridge_site: web.TCPSite | None = None
        self._control_site: web.TCPSite | None = None
    async def start(self) -> None:
        bridge_app = web.Application()
        bridge_app.router.add_route('*', '/{tail:.*}', self._handle_bridge_http_request)
        self._bridge_runner = web.AppRunner(bridge_app)
        await self._bridge_runner.setup()
        self._bridge_site = web.TCPSite(self._bridge_runner, self.bridge_host, self.bridge_port)
        await self._bridge_site.start()

        if self.control_port is not None:
            control_app = web.Application()
            control_app.router.add_get('/health', self._handle_control_health)
            control_app.router.add_get('/sessions', self._handle_control_sessions)
            control_app.router.add_get('/requests', self._handle_control_requests)
            control_app.router.add_get('/debug/session/{client_id}', self._handle_control_session_debug)
            control_app.router.add_get('/profiles', self._handle_control_profiles)
            control_app.router.add_get('/profile', self._handle_control_profile)
            control_app.router.add_post('/profile', self._handle_control_profile_update)
            control_app.router.add_post('/request', self._handle_control_request)
            self._control_runner = web.AppRunner(control_app)
            await self._control_runner.setup()
            self._control_site = web.TCPSite(self._control_runner, self.control_host, self.control_port)
            await self._control_site.start()

    async def stop(self) -> None:
        for pending in list(self.pending_requests.values()):
            if not pending.future.done():
                pending.future.set_exception(RuntimeError('Bridge server stopped before response was received.'))
            pending.timeout_handle.cancel()
        self.pending_requests.clear()

        for session in list(self.sessions.values()):
            await session.websocket.close()
        self.sessions.clear()
        self.socket_clients.clear()

        if self._control_runner is not None:
            await self._control_runner.cleanup()
            self._control_runner = None
            self._control_site = None

        if self._bridge_runner is not None:
            await self._bridge_runner.cleanup()
            self._bridge_runner = None
            self._bridge_site = None

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for session in self.sessions.values():
            registration = session.registration
            sessions.append({
                **registration,
                'connectedAt': session.connected_at.isoformat(),
                'lastSeenAt': session.last_seen_at.isoformat(),
            })
        return sessions

    def list_pending_requests(self) -> list[dict[str, Any]]:
        pending_requests: list[dict[str, Any]] = []
        now = utc_now()
        for request_id, pending in self.pending_requests.items():
            pending_requests.append({
                'requestId': request_id,
                'clientId': pending.client_id,
                'commandName': pending.command_name,
                'startedAt': pending.started_at.isoformat(),
                'ageMs': int((now - pending.started_at).total_seconds() * 1000),
            })
        return pending_requests

    def list_request_history(self, limit: int = 20, client_id: str = '') -> list[dict[str, Any]]:
        limit = max(1, min(limit, self.request_history_limit))
        entries = self.request_history
        if client_id:
            entries = [entry for entry in entries if entry.client_id == client_id]
        return [entry.to_dict() for entry in entries[-limit:]][::-1]

    def get_session_debug_info(self, client_id: str) -> dict[str, Any]:
        session = self.sessions.get(client_id)
        if session is None:
            raise RuntimeError(f'Unknown client session: {client_id}')

        pending_requests = [
            pending
            for pending in self.list_pending_requests()
            if pending['clientId'] == client_id
        ]

        return {
            'session': {
                **session.registration,
                'connectedAt': session.connected_at.isoformat(),
                'lastSeenAt': session.last_seen_at.isoformat(),
            },
            'pendingRequests': pending_requests,
            'recentRequests': self.list_request_history(limit=10, client_id=client_id),
            'activeProfile': self.active_rule_profile_name,
        }

    def append_request_history(
        self,
        request_id: str,
        client_id: str,
        command_name: str,
        status: str,
        started_at: datetime,
        summary: str = '',
        error: str = '',
    ) -> None:
        completed_at = utc_now()
        self.request_history.append(RequestHistoryEntry(
            request_id=request_id,
            client_id=client_id,
            command_name=command_name,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            summary=summary,
            error=error,
        ))
        if len(self.request_history) > self.request_history_limit:
            self.request_history = self.request_history[-self.request_history_limit:]

    def build_health_payload(self) -> dict[str, Any]:
        return {
            'ok': True,
            'activeProfile': self.active_rule_profile_name,
            'serverStartedAt': self.server_started_at.isoformat(),
            'sessionCount': len(self.sessions),
            'pendingRequestCount': len(self.pending_requests),
            'requestHistoryCount': len(self.request_history),
        }

    def list_rule_profiles(self) -> list[dict[str, Any]]:
        return [
            {
                **profile.to_dict(),
                'active': profile.name == self.active_rule_profile_name,
            }
            for profile in self.rule_profiles.values()
        ]

    def get_active_rule_profile(self) -> dict[str, Any]:
        profile = self.rule_profiles[self.active_rule_profile_name]
        return {
            **profile.to_dict(),
            'active': True,
        }

    def set_active_rule_profile(self, profile_name: str) -> dict[str, Any]:
        if profile_name not in self.rule_profiles:
            raise RuntimeError(f'Unknown rule profile: {profile_name}')

        self.active_rule_profile_name = profile_name
        return self.get_active_rule_profile()

    async def send_bridge_request(self, client_id: str, request: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(client_id)
        if not session or session.websocket.closed:
            raise RuntimeError(f'Client is not connected: {client_id}')

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        command = request.get('command') if isinstance(request.get('command'), dict) else {}
        command_name = f"{command.get('domain', 'unknown')}.{command.get('action', 'unknown')}"
        started_at = utc_now()

        def on_timeout() -> None:
            pending = self.pending_requests.pop(request['id'], None)
            if pending is not None and not pending.future.done():
                pending.future.set_exception(RuntimeError(f"Timed out waiting for bridge response: {request['id']}"))

        timeout_handle = loop.call_later(self.request_timeout_ms / 1000.0, on_timeout)
        self.pending_requests[request['id']] = PendingBridgeRequest(
            client_id=client_id,
            future=future,
            timeout_handle=timeout_handle,
            command_name=command_name,
            started_at=started_at,
        )

        await session.websocket.send_json({
            'type': 'bridge.request',
            'request': request,
        })

        try:
            response = await future
            result = response.get('result') if isinstance(response.get('result'), dict) else {}
            self.append_request_history(
                request_id=str(request['id']),
                client_id=client_id,
                command_name=command_name,
                status=str(response.get('status') or 'unknown'),
                started_at=started_at,
                summary=str(result.get('summary') or ''),
            )
            return response
        except Exception as error:
            self.append_request_history(
                request_id=str(request['id']),
                client_id=client_id,
                command_name=command_name,
                status='failed',
                started_at=started_at,
                error=str(error),
            )
            raise
        finally:
            pending = self.pending_requests.pop(request['id'], None)
            if pending is not None:
                pending.timeout_handle.cancel()

    async def _handle_bridge_http_request(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        can_prepare = ws.can_prepare(request)
        if not can_prepare.ok:
            raise web.HTTPNotFound()

        await ws.prepare(request)
        await self._handle_ws_connection(ws)
        return ws

    async def _handle_ws_connection(self, websocket: web.WebSocketResponse) -> None:
        try:
            async for message in websocket:
                if message.type == WSMsgType.TEXT:
                    await self._handle_socket_message(websocket, message.data)
                elif message.type == WSMsgType.ERROR:
                    break
        except Exception:
            pass
        await self._handle_socket_close(websocket)

    async def _handle_socket_message(self, websocket: web.WebSocketResponse, raw_message: str) -> None:
        try:
            message = json.loads(raw_message)
        except Exception:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'INVALID_MESSAGE',
                'message': 'Failed to parse client message as JSON.',
            })
            return

        message_type = message.get('type')
        if message_type == 'agent.register':
            await self._handle_agent_register(websocket, message)
            return
        if message_type == 'agent.heartbeat':
            await self._handle_agent_heartbeat(websocket, message)
            return
        if message_type == 'bridge.response':
            await self._handle_bridge_response(message)
            return
        if message_type == 'bridge.event':
            return

        await websocket.send_json({
            'type': 'server.error',
            'code': 'INVALID_MESSAGE',
            'message': f'Unsupported client message type: {message_type or "unknown"}',
        })

    async def _handle_agent_register(self, websocket: web.WebSocketResponse, message: dict[str, Any]) -> None:
        token = message.get('token', '')
        if self.auth_token and token != self.auth_token:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'AUTH_FAILED',
                'message': 'Agent registration token is invalid.',
            })
            await websocket.close()
            return

        client = message.get('client') or {}
        client_id = str(client.get('clientId', ''))
        if not client_id:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'INVALID_MESSAGE',
                'message': 'client.clientId is required.',
            })
            await websocket.close()
            return

        existing_session = self.sessions.get(client_id)
        if existing_session is not None:
            await existing_session.websocket.close()
            self.socket_clients.pop(id(existing_session.websocket), None)

        session = BridgeSession(
            registration=client,
            websocket=websocket,
            connected_at=utc_now(),
            last_seen_at=utc_now(),
        )
        self.sessions[client_id] = session
        self.socket_clients[id(websocket)] = client_id

        try:
            await websocket.send_json({
                'type': 'server.registered',
                'clientId': client_id,
                'session': {
                    **client,
                    'connectedAt': session.connected_at.isoformat(),
                    'lastSeenAt': session.last_seen_at.isoformat(),
                },
            })
        except Exception:
            # Transport already closed — clean up and let the client retry.
            self.sessions.pop(client_id, None)
            self.socket_clients.pop(id(websocket), None)
            await websocket.close()
            return

    async def _handle_agent_heartbeat(self, websocket: web.WebSocketResponse, message: dict[str, Any]) -> None:
        client_id = self.socket_clients.get(id(websocket))
        if not client_id or client_id != message.get('clientId'):
            await websocket.send_json({
                'type': 'server.error',
                'code': 'UNKNOWN_CLIENT',
                'message': 'Heartbeat received before agent registration.',
            })
            return

        session = self.sessions.get(client_id)
        if session is None:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'UNKNOWN_CLIENT',
                'message': f'No active session found for {client_id}.',
            })
            return

        timestamp = str(message.get('timestamp') or isoformat_now())
        try:
            session.last_seen_at = datetime.fromisoformat(timestamp)
        except Exception:
            session.last_seen_at = utc_now()

        try:
            await websocket.send_json({
                'type': 'server.heartbeat_ack',
                'clientId': client_id,
                'timestamp': isoformat_now(),
            })
        except Exception:
            pass

    async def _handle_bridge_response(self, message: dict[str, Any]) -> None:
        response = message.get('response') or {}
        request_id = response.get('id')
        client_id = message.get('clientId')
        if not request_id or not client_id:
            return

        pending = self.pending_requests.get(request_id)
        if pending is None or pending.client_id != client_id:
            return

        self.pending_requests.pop(request_id, None)
        pending.timeout_handle.cancel()
        if not pending.future.done():
            pending.future.set_result(response)

    async def _handle_socket_close(self, websocket: web.WebSocketResponse) -> None:
        client_id = self.socket_clients.pop(id(websocket), None)
        if not client_id:
            return

        session = self.sessions.get(client_id)
        if session is None or session.websocket is not websocket:
            logger.warning(f'Socket closed for {client_id} but session mismatch (session_ws={id(session.websocket) if session else None} closing_ws={id(websocket)})')
            return

        logger.info(f'Socket closed for {client_id}, removing session')
        self.sessions.pop(client_id, None)
        for request_id, pending in list(self.pending_requests.items()):
            if pending.client_id != client_id:
                continue
            pending.timeout_handle.cancel()
            if not pending.future.done():
                pending.future.set_exception(RuntimeError('Bridge session closed before response was received.'))
            self.pending_requests.pop(request_id, None)

    def _is_authorized(self, request: web.Request) -> bool:
        if not self.control_token:
            return True
        header_token = request.headers.get('x-bridge-control-token', '')
        return header_token == self.control_token

    async def _handle_control_health(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})
        return write_json(200, self.build_health_payload())

    async def _handle_control_sessions(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})
        return write_json(200, {
            'sessions': self.list_sessions(),
            'pendingRequests': self.list_pending_requests(),
        })

    async def _handle_control_requests(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})

        raw_limit = request.query.get('limit', '20')
        try:
            limit = int(raw_limit)
        except Exception:
            limit = 20
        client_id = str(request.query.get('clientId') or '')
        return write_json(200, {
            'requests': self.list_request_history(limit=limit, client_id=client_id),
        })

    async def _handle_control_session_debug(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})

        client_id = str(request.match_info.get('client_id') or '')
        if not client_id:
            return write_json(400, {
                'error': 'invalid_request',
                'message': 'client_id is required.',
            })

        try:
            payload = self.get_session_debug_info(client_id)
        except RuntimeError as error:
            return write_json(404, {
                'error': 'not_found',
                'message': str(error),
            })

        return write_json(200, payload)

    async def _handle_control_profiles(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})
        return write_json(200, {
            'activeProfile': self.active_rule_profile_name,
            'profiles': self.list_rule_profiles(),
        })

    async def _handle_control_profile(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})
        return write_json(200, {
            'activeProfile': self.active_rule_profile_name,
            'profile': self.get_active_rule_profile(),
        })

    async def _handle_control_profile_update(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})

        try:
            body = await request.json()
        except Exception:
            body = {}

        profile_name = ''
        if isinstance(body, dict):
            profile_name = str(body.get('profileName') or body.get('profile') or '')

        if not profile_name:
            return write_json(400, {
                'error': 'invalid_request',
                'message': 'profileName is required.',
            })

        try:
            profile = self.set_active_rule_profile(profile_name)
        except RuntimeError as error:
            return write_json(404, {
                'error': 'not_found',
                'message': str(error),
            })

        return write_json(200, {
            'activeProfile': self.active_rule_profile_name,
            'profile': profile,
        })

    async def _handle_control_request(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})

        try:
            body = await request.json()
        except Exception:
            body = {}

        client_id = body.get('clientId') if isinstance(body, dict) else None
        bridge_request = body.get('request') if isinstance(body, dict) else None
        if not client_id or not bridge_request:
            return write_json(400, {
                'error': 'invalid_request',
                'message': 'clientId and request are required.',
            })

        try:
            response = await self.send_bridge_request(str(client_id), bridge_request)
            return write_json(200, {'response': response})
        except Exception as error:
            return write_json(500, {
                'error': 'request_failed',
                'message': str(error),
            })


async def main() -> None:
    bridge_port = int(os.environ.get('BRIDGE_SERVER_PORT', '8787'))
    bridge_host = os.environ.get('BRIDGE_SERVER_HOST', '0.0.0.0')
    auth_token = os.environ.get('BRIDGE_SERVER_TOKEN', '')
    request_timeout_ms = int(os.environ.get('BRIDGE_SERVER_REQUEST_TIMEOUT_MS', '15000'))
    control_port_raw = os.environ.get('BRIDGE_SERVER_CONTROL_PORT')
    control_port = int(control_port_raw) if control_port_raw else None
    control_host = os.environ.get('BRIDGE_SERVER_CONTROL_HOST', '127.0.0.1')
    control_token = os.environ.get('BRIDGE_SERVER_CONTROL_TOKEN', '')

    # Require auth token when binding to a public interface
    if bridge_host == '0.0.0.0' and not auth_token:
        print(
            'ERROR: BRIDGE_SERVER_TOKEN is required when BRIDGE_SERVER_HOST is 0.0.0.0.\n'
            'Set the BRIDGE_SERVER_TOKEN environment variable to enable authentication.\n'
            'Example: BRIDGE_SERVER_TOKEN=your-secret-token npm run server:public',
            file=sys.stderr,
        )
        sys.exit(1)

    if control_host == '0.0.0.0' and not control_token:
        print(
            'ERROR: BRIDGE_SERVER_CONTROL_TOKEN is required when BRIDGE_SERVER_CONTROL_HOST is 0.0.0.0.\n'
            'Set the BRIDGE_SERVER_CONTROL_TOKEN environment variable to enable authentication.',
            file=sys.stderr,
        )
        sys.exit(1)
    rule_profile_file = os.environ.get('BRIDGE_RULE_PROFILE_FILE')
    rule_profiles, active_rule_profile_name = load_rule_profiles(rule_profile_file)
    requested_profile = os.environ.get('BRIDGE_RULE_PROFILE', active_rule_profile_name)
    if requested_profile not in rule_profiles:
        requested_profile = active_rule_profile_name

    server = BridgeServer(
        bridge_host=bridge_host,
        bridge_port=bridge_port,
        auth_token=auth_token,
        request_timeout_ms=request_timeout_ms,
        control_host=control_host,
        control_port=control_port,
        control_token=control_token,
        rule_profiles=rule_profiles,
        active_rule_profile_name=requested_profile,
    )
    await server.start()

    logger.info(f'Bridge server listening on ws://{bridge_host}:{bridge_port}')
    logger.info(f'Auth token enabled: {"yes" if auth_token else "no"}')
    logger.info(f'Rule profile active: {server.active_rule_profile_name}')
    if control_port is not None:
        logger.info(f'Control server listening on http://{control_host}:{control_port}')
        logger.info(f'Control token enabled: {"yes" if control_token else "no"}')

    stop_event = asyncio.Event()

    def request_shutdown() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in ('SIGINT', 'SIGTERM'):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, request_shutdown)
            except NotImplementedError:
                signal.signal(sig, lambda *_: request_shutdown())

    await stop_event.wait()
    await server.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

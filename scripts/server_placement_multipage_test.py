#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def env(name: str, fallback: str = '') -> str:
    value = os.environ.get(name)
    return value if isinstance(value, str) and value else fallback


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def timestamp_tag() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S')


class ControlClient:
    def __init__(self, base_url: str, token: str = '') -> None:
        self.base_url = base_url.rstrip('/')
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {'content-type': 'application/json'}
        if self.token:
            headers['x-bridge-control-token'] = self.token
        return headers

    def get_json(self, path: str) -> Any:
        req = urllib.request.Request(
            f'{self.base_url}{path}',
            headers=self._headers(),
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))

    def post_json(self, path: str, payload: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            f'{self.base_url}{path}',
            data=json.dumps(payload).encode('utf-8'),
            headers=self._headers(),
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.loads(response.read().decode('utf-8'))

    def send(self, client_id: str, request_id: str, domain: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.post_json(
            '/request',
            {
                'clientId': client_id,
                'request': {
                    'id': request_id,
                    'type': 'command.request',
                    'protocolVersion': '0.1.0',
                    'sessionId': 'placement-multipage-test-py',
                    'command': {
                        'domain': domain,
                        'action': action,
                        'requiresConfirmation': False,
                        'payload': payload,
                    },
                },
            },
        )
        return response.get('response', {})


def response_error(response: dict[str, Any]) -> str:
    if response.get('status') == 'success':
        return ''
    error = response.get('error', {})
    if isinstance(error, dict):
        return str(error.get('message') or error.get('code') or response.get('status'))
    return str(response.get('status'))


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def add_page(page_map: dict[str, dict[str, str]], item: Any) -> None:
    if not isinstance(item, dict):
        return
    page_uuid = str(item.get('uuid', '') or '')
    if not page_uuid:
        return
    page_map[page_uuid] = {'uuid': page_uuid, 'name': str(item.get('name', '') or '')}


def parse_placement_data(response: dict[str, Any]) -> dict[str, Any] | None:
    if response.get('status') != 'success':
        return None
    result = response.get('result', {})
    if isinstance(result, dict):
        data = result.get('data')
        if isinstance(data, dict):
            return data
    return None


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {'name': name, 'pass': passed, 'detail': detail}


def run() -> None:
    control_url = env('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788')
    control_token = env('BRIDGE_CONTROL_TOKEN')
    target_client_id = env('BRIDGE_TARGET_CLIENT_ID')
    keyword = env('BRIDGE_DEMO_DEVICE_KEYWORD', 'C8218')
    extra_pages = int(env('BRIDGE_DEMO_EXTRA_PAGES', '7'))
    needed_pages = int(env('BRIDGE_DEMO_NEEDED_PAGES', '6'))
    tag = timestamp_tag()

    client = ControlClient(control_url, control_token)
    sessions_payload = client.get_json('/sessions')
    sessions = as_list(sessions_payload.get('sessions', []))
    if not sessions:
        raise RuntimeError('No connected bridge sessions were found.')
    first = sessions[0] if isinstance(sessions[0], dict) else {}
    client_id = target_client_id or str(first.get('clientId', ''))
    if not client_id:
        raise RuntimeError('No bridge clientId available.')
    selected_session = next(
        (item for item in sessions if isinstance(item, dict) and str(item.get('clientId', '')) == client_id),
        first,
    )

    project_friendly_name = f'Placement MultiPage PY {tag}'
    project_name = f'placement-multipage-py-{tag}'

    created = client.send(
        client_id,
        'mpp-001',
        'project',
        'create_project',
        {
            'projectFriendlyName': project_friendly_name,
            'projectName': project_name,
            'description': 'Multipage placement verification demos (python)',
        },
    )
    if created.get('status') != 'success':
        raise RuntimeError(f'create_project failed: {response_error(created)}')
    project_uuid = str(created.get('result', {}).get('data', {}).get('projectUuid', ''))
    if not project_uuid:
        raise RuntimeError('create_project returned empty projectUuid.')

    opened = client.send(client_id, 'mpp-002', 'project', 'open_project', {'projectUuid': project_uuid})
    open_project_ok = opened.get('status') == 'success'
    for i in range(3):
        if open_project_ok:
            break
        time.sleep(0.8)
        retry = client.send(client_id, f'mpp-002-r{i + 1}', 'project', 'open_project', {'projectUuid': project_uuid})
        open_project_ok = retry.get('status') == 'success'

    active_project_uuid = project_uuid
    if not open_project_ok:
        inventory_fallback = client.send(client_id, 'mpp-002-fallback', 'project', 'get_inventory', {})
        if inventory_fallback.get('status') == 'success':
            current_uuid = str(
                inventory_fallback.get('result', {})
                .get('data', {})
                .get('current', {})
                .get('project', {})
                .get('uuid', '')
            )
            if current_uuid:
                active_project_uuid = current_uuid

    created_board = client.send(client_id, 'mpp-003', 'project', 'create_board', {})
    if created_board.get('status') != 'success':
        raise RuntimeError(f'create_board failed: {response_error(created_board)}')
    board = (
        created_board.get('result', {})
        .get('data', {})
        .get('board', {})
    )
    schematic = board.get('schematic', {}) if isinstance(board, dict) else {}
    schematic_uuid = str(schematic.get('uuid', '') if isinstance(schematic, dict) else '')
    if not schematic_uuid:
        raise RuntimeError('create_board returned empty schematic uuid.')

    page_map: dict[str, dict[str, str]] = {}
    for item in as_list(schematic.get('pages', []) if isinstance(schematic, dict) else []):
        add_page(page_map, item)

    for i in range(extra_pages):
        response = client.send(
            client_id,
            f'mpp-pg-{i + 1:02d}',
            'schematic',
            'create_schematic_page',
            {'schematicUuid': schematic_uuid},
        )
        if response.get('status') != 'success':
            continue
        data = response.get('result', {}).get('data', {})
        add_page(page_map, data.get('page'))
        for item in as_list(data.get('items', [])):
            add_page(page_map, item)
        for item in as_list(data.get('pages', [])):
            add_page(page_map, item)

    listed = client.send(client_id, 'mpp-004', 'project', 'list_schematic_pages', {'schematicUuid': schematic_uuid})
    if listed.get('status') == 'success':
        data = listed.get('result', {}).get('data', {})
        for item in as_list(data.get('items', [])):
            add_page(page_map, item)
        for item in as_list(data.get('pages', [])):
            add_page(page_map, item)
        for item in as_list(data.get('schematicPages', [])):
            add_page(page_map, item)

    page_strategy = 'schematic_pages'
    if len(page_map) < needed_pages:
        page_strategy = 'board_fallback'
        while len(page_map) < needed_pages:
            response = client.send(
                client_id,
                f'mpp-board-fb-{len(page_map) + 1:02d}',
                'project',
                'create_board',
                {},
            )
            if response.get('status') != 'success':
                break
            fb_board = response.get('result', {}).get('data', {}).get('board', {})
            fb_schematic = fb_board.get('schematic', {}) if isinstance(fb_board, dict) else {}
            for item in as_list(fb_schematic.get('pages', []) if isinstance(fb_schematic, dict) else []):
                add_page(page_map, item)
            if len(page_map) >= needed_pages:
                break

    pages = list(page_map.values())
    if len(pages) < needed_pages:
        raise RuntimeError(f'Expected at least {needed_pages} pages (or board fallback pages), got {len(pages)}.')
    pages.sort(key=lambda item: item['uuid'])

    searched = client.send(
        client_id,
        'mpp-005',
        'system',
        'api_invoke',
        {'path': 'lib_Device.search', 'args': [keyword]},
    )
    if searched.get('status') != 'success':
        raise RuntimeError(f'lib_Device.search failed: {response_error(searched)}')
    items = as_list(searched.get('result', {}).get('data', {}).get('result', []))
    if not items:
        raise RuntimeError(f'No device candidates found for keyword: {keyword}')
    first_item = items[0] if isinstance(items[0], dict) else {}
    library_uuid = str(first_item.get('libraryUuid', ''))
    device_uuid = str(first_item.get('uuid', ''))
    device_name = str(first_item.get('name', ''))
    if not library_uuid or not device_uuid:
        raise RuntimeError('Selected device has empty libraryUuid or uuid.')

    def open_page(index: int, suffix: str) -> dict[str, Any]:
        page = pages[index]
        response = client.send(
            client_id,
            f'mpp-open-{suffix}',
            'project',
            'open_document',
            {'documentUuid': page['uuid']},
        )
        if response.get('status') != 'success':
            raise RuntimeError(f'open_document failed for page {page["name"]}: {response_error(response)}')
        return response

    def place(suffix: str, x: int, y: int, rotation: int, mirror: bool) -> dict[str, Any]:
        return client.send(
            client_id,
            f'mpp-place-{suffix}',
            'schematic',
            'place_component',
            {
                'libraryUuid': library_uuid,
                'uuid': device_uuid,
                'position': {'x': x, 'y': y},
                'rotation': rotation,
                'mirror': mirror,
                'addIntoBom': True,
                'addIntoPcb': True,
            },
        )

    checks: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}

    open_page(0, 'p1')
    p1a = place('p1a', 100, 100, 0, False)
    p1b = place('p1b', 220, 100, 0, False)
    p1c = place('p1c', 340, 100, 0, False)
    p1ok = p1a.get('status') == 'success' and p1b.get('status') == 'success' and p1c.get('status') == 'success'
    checks.append(check('P1 basic placements', p1ok, '3 placements success' if p1ok else 'has failed placement'))
    evidence['p1'] = [parse_placement_data(p1a), parse_placement_data(p1b), parse_placement_data(p1c)]

    open_page(1, 'p2')
    p2a = place('p2a', 200, 200, 0, False)
    p2b = place('p2b', 200, 200, 0, False)
    p2da = parse_placement_data(p2a) or {}
    p2db = parse_placement_data(p2b) or {}
    p2_distinct_primitives = str(p2da.get('primitiveId', '')) != str(p2db.get('primitiveId', ''))
    p2_adjusted = bool(p2db.get('placementAdjusted')) is True
    p2_same_position = (
        p2da.get('position', {}).get('x') == p2db.get('position', {}).get('x')
        and p2da.get('position', {}).get('y') == p2db.get('position', {}).get('y')
    )
    p2ok = p2a.get('status') == 'success' and p2b.get('status') == 'success' and p2_distinct_primitives
    if p2ok and p2_adjusted:
        p2_detail = 'second placement auto-adjusted away from original'
    elif p2ok and p2_same_position:
        p2_detail = 'both placements succeeded at same coordinate (stacking allowed)'
    elif p2ok:
        p2_detail = 'both placements succeeded with explicit position'
    else:
        p2_detail = 'second placement failed or duplicate primitive id'
    checks.append(check('P2 same-point double placement', p2ok, p2_detail))
    evidence['p2'] = [p2da, p2db]

    open_page(2, 'p3')
    p3r0 = place('p3r0', 100, 100, 0, False)
    p3r90 = place('p3r90', 190, 100, 90, False)
    p3r180 = place('p3r180', 280, 100, 180, False)
    p3r270 = place('p3r270', 370, 100, 270, False)
    d3r0 = parse_placement_data(p3r0) or {}
    d3r90 = parse_placement_data(p3r90) or {}
    d3r180 = parse_placement_data(p3r180) or {}
    d3r270 = parse_placement_data(p3r270) or {}
    p3ok = (
        p3r0.get('status') == 'success'
        and p3r90.get('status') == 'success'
        and p3r180.get('status') == 'success'
        and p3r270.get('status') == 'success'
        and d3r0.get('rotation') == 0
        and d3r90.get('rotation') == 90
        and d3r180.get('rotation') == 180
        and d3r270.get('rotation') == 270
    )
    checks.append(check('P3 rotation set', p3ok, '0/90/180/270 all correct' if p3ok else 'rotation mismatch or failure'))
    evidence['p3'] = [d3r0, d3r90, d3r180, d3r270]

    open_page(3, 'p4')
    p4m0 = place('p4m0', 120, 120, 0, False)
    p4m1 = place('p4m1', 240, 120, 0, True)
    d4m0 = parse_placement_data(p4m0) or {}
    d4m1 = parse_placement_data(p4m1) or {}
    p4ok = p4m0.get('status') == 'success' and p4m1.get('status') == 'success' and d4m1.get('mirror') is True
    checks.append(check('P4 mirror set', p4ok, 'mirror true recorded' if p4ok else 'mirror check failed'))
    evidence['p4'] = [d4m0, d4m1]

    open_page(4, 'p5')
    stress = [place(f'p5-{i + 1}', 160, 180, 0, False) for i in range(8)]
    p5ok = all(item.get('status') == 'success' for item in stress)
    checks.append(check('P5 dense stress', p5ok, '8/8 success' if p5ok else 'stress placement failed'))
    evidence['p5'] = [parse_placement_data(item) for item in stress]

    open_page(5, 'p6')
    p6a = place('p6a', -450, -280, 0, False)
    p6b = place('p6b', 450, 280, 0, False)
    p6ok = p6a.get('status') == 'success' and p6b.get('status') == 'success'
    checks.append(check('P6 wide-range coordinates', p6ok, 'both placements success' if p6ok else 'edge coordinate failed'))
    evidence['p6'] = [parse_placement_data(p6a), parse_placement_data(p6b)]

    saved = client.send(client_id, 'mpp-save', 'schematic', 'save', {})
    save_ok = saved.get('status') == 'success'
    checks.append(check('Save schematic', save_ok, 'saved' if save_ok else 'save failed'))

    overall_pass = all(bool(item.get('pass')) for item in checks)
    report = {
        'generatedAt': iso_now(),
        'client': {
            'clientId': client_id,
            'pluginVersion': selected_session.get('pluginVersion'),
            'protocolVersion': selected_session.get('protocolVersion'),
        },
        'project': {
            'projectUuid': project_uuid,
            'activeProjectUuid': active_project_uuid,
            'openProjectSucceeded': open_project_ok,
            'projectFriendlyName': project_friendly_name,
            'projectName': project_name,
            'schematicUuid': schematic_uuid,
            'pageCount': len(pages),
            'pageStrategy': page_strategy,
        },
        'partUnderTest': {
            'keyword': keyword,
            'libraryUuid': library_uuid,
            'uuid': device_uuid,
            'name': device_name,
        },
        'checks': checks,
        'overallPass': overall_pass,
        'evidence': evidence,
    }

    out_dir = Path('.where') / 'pipeline-output' / f'placement-multipage-py-{tag}'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'placement-multipage-report.json'
    with out_path.open('w', encoding='utf-8') as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write('\n')

    print(
        json.dumps(
            {
                'overallPass': overall_pass,
                'checkCount': len(checks),
                'failedChecks': [item['name'] for item in checks if not item['pass']],
                'reportPath': str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == '__main__':
    try:
        run()
    except urllib.error.URLError as error:
        print('Server placement multipage test failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # noqa: BLE001
        print('Server placement multipage test failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from env_utils import env, is_truthy_env, to_int_env


def resolve_kicad_cli() -> str:
    explicit = env('KICAD_CLI_BIN')
    if explicit:
        return explicit
    located = shutil.which('kicad-cli') or shutil.which('kicad-cli.exe')
    if located:
        return located
    windows_roots = [
        Path('D:/Program Files/KiCad'),
        Path('C:/Program Files/KiCad'),
    ]
    candidates: list[Path] = []
    for root in windows_roots:
        if root.exists():
            candidates.extend(root.glob('*/bin/kicad-cli.exe'))
    if candidates:
        return str(sorted(candidates)[-1])
    return ''


def load_schematic_from_plan() -> str:
    plan_file = env('KICAD_EXECUTION_PLAN_FILE')
    if not plan_file:
        return ''
    try:
        with Path(plan_file).open('r', encoding='utf-8') as file:
            plan = json.load(file)
        target = plan.get('target', {})
        if isinstance(target, dict):
            return str(target.get('schematic_file', '') or '')
    except Exception:
        return ''
    return ''


def resolve_schematic_file() -> Path:
    schematic_file = env('KICAD_SCHEMATIC_FILE') or load_schematic_from_plan()
    if not schematic_file:
        raise ValueError('KICAD_SCHEMATIC_FILE or KICAD_EXECUTION_PLAN_FILE is required.')
    path = Path(schematic_file)
    if not path.exists():
        raise ValueError(f'KiCad schematic file does not exist: {path}')
    return path


def count_findings(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get('sheets'), list):
        return sum(
            len(sheet.get('violations', []))
            for sheet in payload['sheets']
            if isinstance(sheet, dict) and isinstance(sheet.get('violations', []), list)
        )
    if isinstance(payload, dict):
        total = 0
        for key, value in payload.items():
            key_text = str(key).lower()
            if key_text in {'violations', 'errors', 'warnings', 'items'} and isinstance(value, list):
                total += len(value)
            total += count_findings(value)
        return total
    if isinstance(payload, list):
        return sum(count_findings(item) for item in payload)
    return 0


def emit_summary(summary: dict[str, Any], enabled: bool) -> None:
    if enabled:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


def run(emit: bool = True) -> dict[str, Any]:
    schematic_file = resolve_schematic_file()
    output_file = Path(env('KICAD_ERC_OUTPUT_FILE') or schematic_file.with_suffix('.erc.json'))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file = Path(env('KICAD_ERC_SUMMARY_FILE') or output_file.with_suffix('.summary.json'))

    executable = resolve_kicad_cli()
    if not executable:
        summary = {
            'schema_version': 'kicad-erc-result.v1',
            'enabled': False,
            'attempted': False,
            'success': False,
            'executable': '',
            'schematic_file': str(schematic_file),
            'output_file': str(output_file),
            'summary_file': str(summary_file),
            'finding_count': 0,
            'warnings': ['kicad-cli was not found. Set KICAD_CLI_BIN or add KiCad to PATH.'],
            'error': 'KICAD_CLI_NOT_FOUND',
        }
        summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        emit_summary(summary, emit)
        return summary

    version_process = subprocess.run(
        [executable, 'version'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=to_int_env('KICAD_CLI_TIMEOUT_SEC', 60),
        check=False,
    )
    version_text = (version_process.stdout or version_process.stderr or '').strip()

    command = [
        executable,
        'sch',
        'erc',
        '--format',
        env('KICAD_ERC_FORMAT', 'json'),
        '--output',
        str(output_file),
        str(schematic_file),
    ]
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=to_int_env('KICAD_CLI_TIMEOUT_SEC', 60),
        check=False,
    )

    report_payload: Any = None
    if output_file.exists() and output_file.suffix.lower() == '.json':
        try:
            report_payload = json.loads(output_file.read_text(encoding='utf-8'))
        except Exception:
            report_payload = None

    finding_count = count_findings(report_payload)
    success = process.returncode == 0
    if is_truthy_env('KICAD_ERC_EXIT_CODE_VIOLATIONS', 'false') and finding_count > 0:
        success = False

    summary = {
        'schema_version': 'kicad-erc-result.v1',
        'enabled': True,
        'attempted': True,
        'success': success,
        'return_code': process.returncode,
        'executable': executable,
        'version': version_text,
        'command': command,
        'schematic_file': str(schematic_file),
        'output_file': str(output_file),
        'summary_file': str(summary_file),
        'finding_count': finding_count,
        'stdout': process.stdout,
        'stderr': process.stderr,
        'warnings': [] if output_file.exists() else ['ERC command completed but did not create the expected report file.'],
        'error': '' if process.returncode == 0 else 'KICAD_ERC_FAILED',
    }
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    emit_summary(summary, emit)
    return summary


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('Run KiCad ERC failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)

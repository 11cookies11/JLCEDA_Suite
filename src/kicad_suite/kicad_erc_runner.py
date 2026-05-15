#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .adapters.kicad_cli import count_findings, resolve_kicad_cli, resolve_schematic_file
from .env_utils import env, is_truthy_env, to_int_env


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

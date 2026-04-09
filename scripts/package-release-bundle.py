#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import pathlib
import time
import zipfile


def find_latest_eext(build_dist: pathlib.Path) -> pathlib.Path:
    candidates = sorted(build_dist.glob('*.eext'), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f'No .eext files found in {build_dist}')
    return candidates[0]


def add_directory(zip_file: zipfile.ZipFile, source_root: pathlib.Path, archive_root: str) -> None:
    for path in sorted(source_root.rglob('*')):
        if path.is_dir():
            continue
        relative = path.relative_to(source_root).as_posix()
        zip_file.write(path, f'{archive_root}/{relative}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Package the JLCEDA Suite skill and plugin into a release bundle.')
    parser.add_argument('--repo-root', default=None, help='Repository root directory.')
    parser.add_argument('--skill-dir', default='skills/jlceda-suite-skill', help='Skill directory relative to repo root.')
    parser.add_argument('--plugin-eext', default=None, help='Path to the plugin .eext file.')
    parser.add_argument('--skill-output', default=None, help='Output skill zip file path.')
    parser.add_argument('--output', default=None, help='Output zip file path.')
    args = parser.parse_args()

    repo_root = pathlib.Path(args.repo_root or pathlib.Path(__file__).resolve().parents[1]).resolve()
    skill_dir = (repo_root / args.skill_dir).resolve()
    build_dist = repo_root / 'build' / 'dist'
    plugin_eext = pathlib.Path(args.plugin_eext).resolve() if args.plugin_eext else find_latest_eext(build_dist)
    skill_output = pathlib.Path(args.skill_output).resolve() if args.skill_output else build_dist / 'jlceda-suite-skill.zip'
    output = pathlib.Path(args.output).resolve() if args.output else build_dist / 'jlceda-suite-release.zip'

    if not skill_dir.is_dir():
        raise FileNotFoundError(f'Skill directory not found: {skill_dir}')
    if not plugin_eext.is_file():
        raise FileNotFoundError(f'Plugin package not found: {plugin_eext}')

    output.parent.mkdir(parents=True, exist_ok=True)
    skill_output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(skill_output, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        add_directory(zip_file, skill_dir, skill_dir.name)

    manifest = {
        'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'plugin': {
            'fileName': plugin_eext.name,
        },
        'skill': {
            'name': skill_dir.name,
        },
    }

    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        add_directory(zip_file, skill_dir, f'skill/{skill_dir.name}')
        zip_file.write(plugin_eext, f'plugin/{plugin_eext.name}')
        zip_file.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')

    print(str(output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

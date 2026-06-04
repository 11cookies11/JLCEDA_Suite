#!/usr/bin/env python3
"""Path validation helpers."""

from __future__ import annotations

from pathlib import Path

from ....shared.validation.common import OLD_REPO_PATH_PATTERNS, TEXT_SUFFIXES


def walk_text_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"fp-lib-table", "sym-lib-table"}:
            files.append(path)
    return files


def scan_for_stale_paths(project_dir: Path) -> list[str]:
    findings: list[str] = []
    for path in walk_text_files(project_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for needle in OLD_REPO_PATH_PATTERNS:
            if needle in text:
                findings.append(f"{path}: contains stale path {needle}")
                break
    return findings

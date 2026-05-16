#!/usr/bin/env python3
"""Adapter helpers for the repository JLC MCP bridge."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def resolve_bridge_script(bridge_script: str | Path | None = None) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return Path(bridge_script) if bridge_script else repo_root / "scripts" / "jlc_mcp_bridge.mjs"


def extract_bridge_results(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result", payload)
    if isinstance(result, dict):
        raw_results = result.get("results", [])
        if isinstance(raw_results, list):
            return [item for item in raw_results if isinstance(item, dict)]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def run_bridge_search(
    *,
    query: str,
    limit: int = 10,
    source: str = "lcsc",
    bridge_script: str | Path | None = None,
    timeout: float = 30.0,
    **kwargs: object,
) -> list[dict]:
    script = resolve_bridge_script(bridge_script)
    if not script.exists():
        return []

    command = [
        "node",
        str(script),
        "search",
        "--query",
        query,
        "--source",
        source,
        "--limit",
        str(limit),
    ]
    if bool(kwargs.get("in_stock", kwargs.get("is_available", True))):
        command.append("--in-stock")
    if bool(kwargs.get("basic_only", False)):
        command.append("--basic-only")

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if proc.returncode != 0:
        return []

    try:
        payload: Any = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    return extract_bridge_results(payload)


def is_http_backend_reachable(base_url: str = "http://localhost:3847") -> bool:
    try:
        request = urllib.request.Request(f"{base_url}/api/search?q=test&limit=1")
        urllib.request.urlopen(request, timeout=2.0)
        return True
    except (urllib.error.URLError, OSError):
        return False

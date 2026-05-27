"""External tool configuration helpers for model-api operations."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DEFAULT_EXTERNAL_TOOLS_CONFIG: dict[str, Any] = {
    "schema_version": "external-tools-config.v1",
    "kicad": {
        "cli_bin": "",
        "timeout_sec": 60,
        "output_dir": ".where/model-api-output",
        "project_name": "",
        "erc": {
            "format": "json",
            "output_file": "",
            "summary_file": "",
            "exit_code_violations": False,
        },
    },
    "ngspice": {
        "bin": "ngspice",
        "timeout_sec": 60,
    },
    "simulation": {
        "output_dir": ".where/model-api-simulation",
    },
}


def load_external_tools_config(path: str | Path | None = None) -> dict[str, Any]:
    config = _deep_merge({}, DEFAULT_EXTERNAL_TOOLS_CONFIG)
    if not path:
        default_local = Path("config/external-tools.local.json")
        path = default_local if default_local.exists() else None
    if path:
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError(f"{config_path} must contain a JSON object.")
        config = _deep_merge(config, loaded)
    return config


def external_tools_config_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    config_path = payload.get("config", payload.get("config_path", ""))
    return load_external_tools_config(str(config_path) if config_path else None)


@contextmanager
def external_tool_env(config: dict[str, Any], overrides: dict[str, str] | None = None) -> Iterator[None]:
    updates = _env_updates(config)
    if overrides:
        updates.update({key: value for key, value in overrides.items() if value})
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _env_updates(config: dict[str, Any]) -> dict[str, str]:
    kicad = _as_dict(config.get("kicad"))
    erc = _as_dict(kicad.get("erc"))
    ngspice = _as_dict(config.get("ngspice"))
    updates: dict[str, str] = {}
    _add(updates, "KICAD_CLI_BIN", kicad.get("cli_bin"))
    _add(updates, "KICAD_CLI_TIMEOUT_SEC", kicad.get("timeout_sec"))
    _add(updates, "KICAD_OUTPUT_DIR", kicad.get("output_dir"))
    _add(updates, "KICAD_PROJECT_NAME", kicad.get("project_name"))
    _add(updates, "KICAD_ERC_FORMAT", erc.get("format"))
    _add(updates, "KICAD_ERC_OUTPUT_FILE", erc.get("output_file"))
    _add(updates, "KICAD_ERC_SUMMARY_FILE", erc.get("summary_file"))
    _add(updates, "KICAD_ERC_EXIT_CODE_VIOLATIONS", erc.get("exit_code_violations"))
    _add(updates, "NGSPICE_BIN", ngspice.get("bin"))
    _add(updates, "NGSPICE_TIMEOUT_SEC", ngspice.get("timeout_sec"))
    return updates


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _add(updates: dict[str, str], key: str, value: Any) -> None:
    if value not in (None, ""):
        updates[key] = str(value).lower() if isinstance(value, bool) else str(value)

"""Create part.lock.yaml from selector JSON and JLC MCP install report.

Usage:
  python scripts/write_jlc_mcp_part_lock.py --selections selected-parts.json --install-report jlc-mcp-install-report.json --project-dir .where/project
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.kicad_lib_importer import _yaml_dumps


def _arg_value(name: str, default: str = "") -> str:
    for idx, arg in enumerate(sys.argv):
        if arg == name and idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return default


def _selection_map(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for item in data:
        selected = item.get("selected")
        if isinstance(selected, dict) and selected.get("lcsc_id"):
            result[str(selected["lcsc_id"])] = {
                "requirement_id": item.get("requirement_id", ""),
                "summary": item.get("summary", ""),
                **selected,
            }
    return result


def _install_results(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    return [item for item in results if isinstance(item, dict)]


def _nested_result(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result")
    if not isinstance(result, dict):
        return {}
    inner = result.get("result")
    return inner if isinstance(inner, dict) else result


def _risk_for(selection: dict[str, Any], install: dict[str, Any]) -> str:
    if selection.get("needs_review"):
        return "high"
    validation = _nested_result(install).get("validation", {})
    if isinstance(validation, dict) and validation.get("pin_pad_match") is False:
        return "medium"
    return "low"


def _find_project_symbol(project_dir: Path, lcsc_id: str) -> dict[str, Any]:
    symbols_dir = project_dir / "libraries" / "symbols"
    best: dict[str, Any] = {}
    if not symbols_dir.exists():
        return best

    for path in sorted(symbols_dir.glob("*.kicad_sym")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if lcsc_id not in text:
            continue
        symbol_match = re.search(r'\(symbol\s+"([^"]+)"', text)
        pin_count = len(re.findall(r"\(\s*pin\s+", text))
        candidate = {
            "symbol_ref": f"{path.stem}:{symbol_match.group(1)}" if symbol_match else "",
            "pin_count": pin_count,
            "symbol_file": str(path),
        }
        if pin_count > int(best.get("pin_count", -1)):
            best = candidate
    return best


def _risk_report(parts: list[dict[str, Any]]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# JLC MCP Part Risk Report",
        f"Generated: {now}",
        "",
        "## Installed Parts",
        "",
    ]
    for part in parts:
        lines.append(f"- **{part['role']}** {part['mpn']} `{part['lcsc_id']}` `{part['kicad_symbol']}` `{part['kicad_footprint']}`")
        if part["risk"] != "low":
            lines.append(f"  - Risk: {part['risk']} - {part['note']}")
    lines.extend([
        "",
        "## Summary",
        "",
        f"- Total locked parts: {len(parts)}",
        f"- Low risk: {sum(1 for p in parts if p['risk'] == 'low')}",
        f"- Medium risk: {sum(1 for p in parts if p['risk'] == 'medium')}",
        f"- High risk: {sum(1 for p in parts if p['risk'] == 'high')}",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    selections_path = Path(_arg_value("--selections"))
    install_report_path = Path(_arg_value("--install-report"))
    project_dir = Path(_arg_value("--project-dir"))
    project_name = _arg_value("--project-name", project_dir.name)

    if not selections_path.exists() or not install_report_path.exists() or not project_dir:
        print(__doc__.strip())
        sys.exit(2)

    selections = _selection_map(selections_path)
    parts: list[dict[str, Any]] = []
    for install in _install_results(install_report_path):
        if not install.get("ok"):
            continue
        lcsc_id = str(install.get("lcsc_id", ""))
        selection = selections.get(lcsc_id, {})
        inner = _nested_result(install)
        validation = inner.get("validation", {}) if isinstance(inner.get("validation"), dict) else {}
        project_symbol = _find_project_symbol(project_dir, lcsc_id)
        pin_count = project_symbol.get("pin_count", validation.get("pin_count"))
        pad_count = validation.get("pad_count")
        pin_pad_match = validation.get("pin_pad_match")
        if isinstance(pin_count, int) and isinstance(pad_count, int):
            pin_pad_match = pin_count == pad_count
        risk = _risk_for(selection, install)
        if pin_pad_match is True and not selection.get("needs_review"):
            risk = "low"
        note = "JLC MCP validation passed."
        if risk == "medium":
            note = "JLC MCP validation warning; inspect symbol pins and footprint pads before schematic acceptance."
        elif risk == "high":
            note = "Selected part requires review before schematic acceptance."
        parts.append({
            "ref": "",
            "role": install.get("requirement_id", selection.get("requirement_id", "")),
            "mpn": install.get("mpn", selection.get("mpn", "")),
            "value": selection.get("description", selection.get("mpn", "")),
            "lcsc_id": lcsc_id,
            "package": selection.get("package", ""),
            "source": "jlc_mcp",
            "kicad_symbol": project_symbol.get("symbol_ref") or inner.get("symbol_ref", ""),
            "kicad_footprint": inner.get("footprint_ref", ""),
            "risk": risk,
            "note": note,
            "price": selection.get("price"),
            "stock": selection.get("stock", 0),
            "validation": {
                "pin_pad_match": pin_pad_match,
                "pin_count": pin_count,
                "pad_count": pad_count,
            },
            "status": "review" if risk != "low" else "locked",
        })

    lock_data = {
        "schema_version": "part-lock.v1",
        "project": project_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parts": parts,
    }

    project_dir.mkdir(parents=True, exist_ok=True)
    lock_path = project_dir / "part.lock.yaml"
    report_path = project_dir / "part-risk-report.md"
    lock_path.write_text(_yaml_dumps(lock_data) + "\n", encoding="utf-8")
    report_path.write_text(_risk_report(parts), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "part_count": len(parts),
        "lock_file": str(lock_path),
        "risk_report_file": str(report_path),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

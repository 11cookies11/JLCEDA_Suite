#!/usr/bin/env python3
import base64
import io
import json
import math
import sys
import zipfile
from typing import Any, Dict, List, Optional


def parse_source_record(line: str) -> Optional[Dict[str, Dict[str, Any]]]:
    separator_index = line.find("||")
    if separator_index < 0:
        return None

    header_text = line[:separator_index]
    body_text = line[separator_index + 2 :]
    if body_text.endswith("|"):
        body_text = body_text[:-1]

    try:
        return {
            "header": json.loads(header_text),
            "body": json.loads(body_text),
        }
    except Exception:
        return None


def normalize_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)

    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
            if math.isfinite(parsed):
                return parsed
        except Exception:
            return None

    return None


def normalize_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return False


def transform_point(point: Dict[str, float], placement: Dict[str, Any]) -> Dict[str, float]:
    mirrored = {"x": -point["x"], "y": point["y"]} if placement["mirror"] else point
    rotation = int(placement["rotation"]) % 360

    if rotation == 90:
        return {"x": placement["x"] - mirrored["y"], "y": placement["y"] + mirrored["x"]}
    if rotation == 180:
        return {"x": placement["x"] - mirrored["x"], "y": placement["y"] - mirrored["y"]}
    if rotation == 270:
        return {"x": placement["x"] + mirrored["y"], "y": placement["y"] - mirrored["x"]}
    return {"x": placement["x"] + mirrored["x"], "y": placement["y"] + mirrored["y"]}


def approx_equal(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def points_equal(left: Dict[str, float], right: Dict[str, float], tolerance: float) -> bool:
    return approx_equal(left["x"], right["x"], tolerance) and approx_equal(left["y"], right["y"], tolerance)


def point_on_segment(point: Dict[str, float], start: Dict[str, float], end: Dict[str, float], tolerance: float) -> bool:
    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]
    length_squared = dx * dx + dy * dy

    if length_squared == 0:
        return points_equal(point, start, tolerance)

    cross = (point["y"] - start["y"]) * dx - (point["x"] - start["x"]) * dy
    if abs(cross) > tolerance * math.sqrt(length_squared):
        return False

    dot = (point["x"] - start["x"]) * dx + (point["y"] - start["y"]) * dy
    if dot < -tolerance:
        return False
    if dot > length_squared + tolerance:
        return False
    return True


def parse_components(source: str) -> List[Dict[str, Any]]:
    components: List[Dict[str, Any]] = []
    for line in source.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        record = parse_source_record(trimmed)
        if not record or str(record["header"].get("type", "")) != "COMPONENT":
            continue

        body = record["body"]
        symbol = body.get("symbol") if isinstance(body.get("symbol"), dict) else None
        components.append({
            "primitiveId": str(record["header"].get("id", "")),
            "x": normalize_number(body.get("x")) or 0.0,
            "y": normalize_number(body.get("y")) or 0.0,
            "rotation": normalize_number(body.get("rotation")) or 0.0,
            "mirror": normalize_boolean(body.get("isMirror")),
            "componentType": body.get("componentType") if isinstance(body.get("componentType"), str) else None,
            "designator": body.get("designator") if isinstance(body.get("designator"), str) else None,
            "name": body.get("name") if isinstance(body.get("name"), str) else None,
            "uniqueId": body.get("uniqueId") if isinstance(body.get("uniqueId"), str) else None,
            "symbol": {
                "libraryUuid": str(symbol.get("libraryUuid", "")),
                "uuid": str(symbol.get("uuid", "")),
            } if symbol else None,
        })
    return components


def parse_source_wires(source: str) -> List[Dict[str, Any]]:
    wire_groups: Dict[str, Dict[str, Any]] = {}

    for line in source.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        record = parse_source_record(trimmed)
        if not record:
            continue

        header_type = str(record["header"].get("type", ""))
        record_id = str(record["header"].get("id", ""))
        body = record["body"]

        if header_type == "LINE":
            line_group = str(body.get("lineGroup", ""))
            if not line_group:
                continue

            start_x = normalize_number(body.get("startX"))
            start_y = normalize_number(body.get("startY"))
            end_x = normalize_number(body.get("endX"))
            end_y = normalize_number(body.get("endY"))
            if start_x is None or start_y is None or end_x is None or end_y is None:
                continue

            group = wire_groups.get(line_group) or {"wireId": line_group, "segments": []}
            group["segments"].append({
                "wireId": line_group,
                "start": {"x": start_x, "y": start_y},
                "end": {"x": end_x, "y": end_y},
            })
            wire_groups[line_group] = group
            continue

        if header_type == "ATTR" and str(body.get("key", "")) == "NET":
            parent_id = str(body.get("parentId", ""))
            if not parent_id:
                continue
            group = wire_groups.get(parent_id) or {"wireId": parent_id, "segments": []}
            if isinstance(body.get("value"), str):
                group["net"] = body.get("value")
            wire_groups[parent_id] = group
            continue

        if header_type == "WIRE":
            wire_groups.setdefault(record_id, {"wireId": record_id, "segments": []})

    return list(wire_groups.values())


def extract_symbol_source_text(symbol_bytes: bytes) -> Optional[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(symbol_bytes), "r") as archive:
            best_source: Optional[str] = None
            best_pin_count = -1

            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                try:
                    text = archive.read(entry).decode("utf-8", errors="replace")
                except Exception:
                    continue

                pin_count = 0
                for line in text.splitlines():
                    record = parse_source_record(line.strip())
                    if not record:
                        continue
                    if str(record["header"].get("type", "")) == "PIN":
                        pin_count += 1
                        continue
                    body = record["body"]
                    if body.get("pinNumber") is not None or body.get("pinNo") is not None or body.get("number") is not None:
                        pin_count += 1

                if pin_count > best_pin_count or (pin_count == best_pin_count and "DOCHEAD" in text):
                    best_pin_count = pin_count
                    best_source = text

            return best_source
    except Exception:
        return None


def parse_symbol_pins(symbol_bytes_base64: str) -> List[Dict[str, Any]]:
    if not symbol_bytes_base64:
        return []

    try:
        symbol_bytes = base64.b64decode(symbol_bytes_base64)
    except Exception:
        return []

    source = extract_symbol_source_text(symbol_bytes)
    if not source:
        return []

    pins: List[Dict[str, Any]] = []
    for line in source.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        record = parse_source_record(trimmed)
        if not record:
            continue

        header_type = str(record["header"].get("type", ""))
        body = record["body"]
        pin_number = body.get("pinNumber") if isinstance(body.get("pinNumber"), str) else body.get("pinNo") if isinstance(body.get("pinNo"), str) else body.get("number") if isinstance(body.get("number"), str) else None
        pin_name = body.get("pinName") if isinstance(body.get("pinName"), str) else body.get("name") if isinstance(body.get("name"), str) else None
        if header_type != "PIN" and pin_number is None and pin_name is None:
            continue

        pins.append({
            "pinNumber": pin_number or str(len(pins) + 1),
            "pinName": pin_name,
            "x": normalize_number(body.get("x")) or normalize_number(body.get("centerX")) or 0.0,
            "y": normalize_number(body.get("y")) or normalize_number(body.get("centerY")) or 0.0,
            "rotation": normalize_number(body.get("rotation")) or 0.0,
            "pinLength": normalize_number(body.get("pinLength")) or normalize_number(body.get("length")) or 0.0,
        })

    return pins


def build_absolute_pins(components: List[Dict[str, Any]], symbol_files: Dict[str, str]) -> List[Dict[str, Any]]:
    pins: List[Dict[str, Any]] = []

    for component in components:
        symbol_pins = parse_symbol_pins(symbol_files.get(component["primitiveId"], ""))
        resolved_pins = symbol_pins
        for pin in resolved_pins:
            transformed = transform_point(
                {"x": pin["x"], "y": pin["y"]},
                {
                    "x": component["x"],
                    "y": component["y"],
                    "rotation": component["rotation"],
                    "mirror": component["mirror"],
                },
            )
            pins.append({
                "x": transformed["x"],
                "y": transformed["y"],
                "componentId": component["primitiveId"],
                "designator": component.get("designator"),
                "componentType": component.get("componentType"),
                "pinNumber": pin["pinNumber"],
                "pinName": pin.get("pinName"),
                "noConnected": False,
            })

    return pins


def collect_wire_endpoints(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    endpoints: List[Dict[str, Any]] = []
    for segment_index, segment in enumerate(segments):
        endpoints.append({"point": segment["start"], "wireId": segment["wireId"], "net": segment.get("net"), "end": "start", "segmentIndex": segment_index})
        endpoints.append({"point": segment["end"], "wireId": segment["wireId"], "net": segment.get("net"), "end": "end", "segmentIndex": segment_index})
    return endpoints


def point_connected(point: Dict[str, float], segments: List[Dict[str, Any]], pins: List[Dict[str, Any]], tolerance: float, ignore_segment_index: Optional[int] = None) -> bool:
    for pin in pins:
        if points_equal(point, pin, tolerance):
            return True

    for segment_index, segment in enumerate(segments):
        if ignore_segment_index is not None and segment_index == ignore_segment_index:
            continue
        if point_on_segment(point, segment["start"], segment["end"], tolerance):
            return True

    return False


def summarize_component(component: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "primitiveId": component.get("primitiveId"),
        "designator": component.get("designator"),
        "name": component.get("name"),
        "componentType": component.get("componentType"),
        "uniqueId": component.get("uniqueId"),
        "position": {
            "x": component.get("x"),
            "y": component.get("y"),
        },
        "rotation": component.get("rotation"),
        "mirror": component.get("mirror"),
        "symbol": component.get("symbol"),
    }


def collect_pins(payload: Dict[str, Any]) -> Dict[str, Any]:
    pins = build_absolute_pins(payload.get("components", []), payload.get("symbolFiles", {}))
    return {"pins": pins}


def inspect_connectivity(payload: Dict[str, Any]) -> Dict[str, Any]:
    tolerance = float(payload.get("tolerance", 0.75))
    max_issues = int(payload.get("maxIssues", 100))
    all_schematic_pages = bool(payload.get("allSchematicPages", True))
    source_text = payload.get("sourceText", "")
    components = payload.get("components", [])
    symbol_files = payload.get("symbolFiles", {})

    wires = parse_source_wires(source_text)
    segments: List[Dict[str, Any]] = []
    for wire in wires:
        for segment in wire["segments"]:
            segments.append({
                "wireId": wire["wireId"],
                "net": wire.get("net"),
                "start": segment["start"],
                "end": segment["end"],
            })

    pins = build_absolute_pins(components, symbol_files)
    wire_endpoints = collect_wire_endpoints(segments)
    issues: List[Dict[str, Any]] = []

    for endpoint in wire_endpoints:
        if point_connected(endpoint["point"], segments, pins, tolerance, endpoint["segmentIndex"]):
            continue
        issues.append({
            "type": "dangling_wire_endpoint",
            "severity": "warning",
            "message": f'Wire endpoint at ({endpoint["point"]["x"]}, {endpoint["point"]["y"]}) is not connected.',
            "point": endpoint["point"],
            "wireId": endpoint["wireId"],
            "wireNet": endpoint.get("net"),
        })
        if len(issues) >= max_issues:
            break

    if len(issues) < max_issues:
        for pin in pins:
            if pin.get("noConnected"):
                continue
            connected = any(point_on_segment(pin, segment["start"], segment["end"], tolerance) for segment in segments)
            if connected:
                continue
            issues.append({
                "type": "unconnected_pin",
                "severity": "warning",
                "message": f'Pin {pin.get("designator") or pin.get("componentId") or "unknown"}.{pin.get("pinNumber") or "?"} ({pin.get("pinName") or "unnamed"}) is not connected.',
                "point": {"x": pin["x"], "y": pin["y"]},
                "componentId": pin.get("componentId"),
                "designator": pin.get("designator"),
                "pinNumber": pin.get("pinNumber"),
                "pinName": pin.get("pinName"),
            })
            if len(issues) >= max_issues:
                break

    if len(issues) < max_issues:
        for segment in segments:
            if points_equal(segment["start"], segment["end"], tolerance):
                issues.append({
                    "type": "zero_length_segment",
                    "severity": "info",
                    "message": f'Wire {segment["wireId"]} contains a zero-length segment at ({segment["start"]["x"]}, {segment["start"]["y"]}).',
                    "point": segment["start"],
                    "wireId": segment["wireId"],
                    "wireNet": segment.get("net"),
                })
                if len(issues) >= max_issues:
                    break

    connected_pins = sum(1 for pin in pins if any(point_on_segment(pin, segment["start"], segment["end"], tolerance) for segment in segments))
    connected_endpoints = sum(1 for endpoint in wire_endpoints if point_connected(endpoint["point"], segments, pins, tolerance, endpoint["segmentIndex"]))

    return {
        "summary": "schematic connectivity diagnostics collected",
        "data": {
            "tolerance": tolerance,
            "allSchematicPages": all_schematic_pages,
            "componentCount": len(components),
            "pinCount": len(pins),
            "wireCount": len(wires),
            "segmentCount": len(segments),
            "connectedPinCount": connected_pins,
            "connectedEndpointCount": connected_endpoints,
            "issueCount": len(issues),
            "components": [summarize_component(component) for component in components],
            "issues": issues,
        },
    }


def main() -> None:
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        raise SystemExit("No input provided.")

    payload = json.loads(raw_input)
    action = payload.get("action")
    if action == "collect_pins":
        output = collect_pins(payload)
    elif action == "inspect_connectivity":
        output = inspect_connectivity(payload)
    else:
        raise SystemExit(f"Unsupported action: {action}")

    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.stderr.write(f"{error}\n")
        raise

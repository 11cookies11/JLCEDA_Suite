"""Parse EasyEDA shape strings into structured data for KiCad conversion.

EasyEDA encodes shapes as ``~``-separated and ``^^``-separated strings.
Each shape type (Pin, Rectangle, Arc, Polyline, Text, Circle, Pad) has
a fixed number of fields in a specific order.

Format reference: https://docs.easyeda.com/en/Documentation/API-File-Format/
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# EasyEDA coordinate scale: 1 KiCad unit = 10 EasyEDA units
EASYEDA_SCALE = 10.0


def eda_to_kicad_pos(val: float) -> float:
    return val / EASYEDA_SCALE


def eda_to_kicad_angle(val: float) -> float:
    return -val  # EasyEDA uses CW, KiCad uses CCW


@dataclass
class ParsedShape:
    type: str  # 'pin', 'rect', 'arc', 'polyline', 'text', 'circle', 'pad', 'hole'
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedComponent:
    """Parsed EasyEDA component ready for KiCad conversion."""
    lcsc_id: str = ""
    title: str = ""
    package_title: str = ""
    doc_type: int = 0  # 1=symbol, 2=footprint/spice, 3=subpart, 4=package
    prefix: str = "U"
    name: str = ""
    bbox: dict[str, float] = field(default_factory=dict)
    shapes: list[ParsedShape] = field(default_factory=list)
    # Footprint-specific
    pads: list[ParsedShape] = field(default_factory=list)
    fp_shapes: list[ParsedShape] = field(default_factory=list)
    fp_texts: list[ParsedShape] = field(default_factory=list)


def parse_easyeda_component(data_str: dict[str, Any], package_data_str: dict[str, Any] | None = None, title: str = "", pkg_title: str = "") -> ParsedComponent:
    """Parse EasyEDA component data into a structured form ready for KiCad conversion."""
    comp = ParsedComponent(title=title, package_title=pkg_title)

    head = data_str.get("head", {}) if isinstance(data_str, dict) else {}
    comp.doc_type = head.get("docType", 1)
    comp.prefix = head.get("c_para", {}).get("prefix", "U") if isinstance(head.get("c_para"), dict) else "U"

    # BBox
    bbox = data_str.get("BBox", {}) if isinstance(data_str, dict) else {}
    if isinstance(bbox, dict):
        comp.bbox = {k: float(v) for k, v in bbox.items() if isinstance(v, (int, float))}

    # Parse symbol shapes
    shapes = data_str.get("shape", []) if isinstance(data_str, dict) else []
    if isinstance(shapes, list):
        for s in shapes:
            if isinstance(s, str):
                parsed = _parse_shape_string(s)
                if parsed:
                    comp.shapes.append(parsed)

    # Parse footprint (package) data
    if isinstance(package_data_str, dict):
        # Pads
        pads = package_data_str.get("shape", [])
        if isinstance(pads, list):
            for s in pads:
                if isinstance(s, str):
                    parsed = _parse_pad_string(s)
                    if parsed:
                        comp.pads.append(parsed)

        # Footprint shapes (silkscreen, courtyard, etc.)
        for layer_key in ("shape", "layout"):
            extra = package_data_str.get(layer_key, [])
            if isinstance(extra, list):
                for s in extra:
                    if isinstance(s, str):
                        parsed = _parse_fp_shape(s)
                        if parsed:
                            comp.fp_shapes.append(parsed)

        # Footprint text
        texts = package_data_str.get("text", [])
        if isinstance(texts, list):
            for s in texts:
                if isinstance(s, str):
                    parsed = _parse_fp_shape(s)
                    if parsed:
                        comp.fp_texts.append(parsed)

    return comp


def _parse_shape_string(raw: str) -> ParsedShape | None:
    """Parse a symbol-level shape string (pin, rect, arc, polyline, circle, text)."""
    if not raw:
        return None
    fields = raw.split("~")
    if len(fields) < 2:
        return None
    stype = fields[0]
    try:
        if stype == "P":
            return _parse_pin(fields)
        if stype == "R":
            return _parse_rect(fields)
        if stype == "A":
            return _parse_arc(fields)
        if stype == "L":
            return _parse_polyline(fields)
        if stype == "T":
            return _parse_text(fields)
        if stype == "C":
            return _parse_circle(fields)
    except (IndexError, ValueError):
        pass
    return None


def _parse_pin(f: list[str]) -> ParsedShape:
    props: dict[str, Any] = {"show": f[1] == "show" if len(f) > 1 else True}
    # f[2] is often '0' (unknown field)
    # f[3] may be pin number or pin length depending on format version
    # f[4], f[5] = x, y position
    # f[6] = rotation

    if len(f) > 3:
        val3 = f[3]
        try:
            float(val3)
            # Looks like a number — could be pin number or pin length
            props["number"] = val3
            props["length"] = 20.0  # default
        except ValueError:
            props["number"] = ""
    if len(f) > 4:
        try:
            props["x"] = float(f[4])
        except ValueError:
            pass
    if len(f) > 5:
        try:
            props["y"] = float(f[5])
        except ValueError:
            pass
    if len(f) > 6:
        try:
            props["rotation"] = float(f[6])
        except ValueError:
            props["rotation"] = 0.0

    # Parse ^^ sub-data for pin name, number, graphics
    _parse_pin_subdata(f, props)
    return ParsedShape(type="pin", props=props)


def _parse_pin_subdata(f: list[str], props: dict[str, Any]) -> None:
    """Parse the ^^-separated sub-data embedded in the last pin field(s).

    The tricky part: the raw shape string uses BOTH ``~`` and ``^^`` as
    separators.  After the initial split on ``~``, the sub-data fields
    (f[8:]) are fragmented.  We rejoin them with ``~`` before splitting
    on ``^^``.
    """
    if len(f) <= 8:
        return
    # Rejoin the sub-data portion with ~ to restore the original ^^ structure
    raw = "~".join(f[8:])
    if not raw:
        return
    parts = raw.split("^^")
    # parts[0] = display settings (often '0')
    # parts[1] = "x~y" position for text
    # parts[2] = "svgPath~color" graphics path
    # parts[3] = "show~x~y~rotation~name~align" name info
    # parts[4] = color for name
    # parts[5] = "show~x~y~rotation~number~align" number info
    # parts[6] = color for number
    # parts[7] = dot (0 or 1)
    # parts[8] = "x~y" dot position
    # parts[9] = clock (0 or 1)
    # parts[10] = clock SVG path

    # Extract pin name from parts[3]
    if len(parts) > 3:
        name_info = parts[3].split("~")
        if len(name_info) > 4:
            name = name_info[4]
            if name and name not in ("", "start", "end"):
                props["name"] = name
            elif not props.get("name"):
                # fallback: use pin number as name
                pass
        if len(name_info) > 3:
            try:
                props["name_rotation"] = float(name_info[3])
            except ValueError:
                pass

    # Extract pin number from parts[5] (number info may override f[3])
    if len(parts) > 5:
        num_info = parts[5].split("~")
        if len(num_info) > 4:
            num = num_info[4]
            if num and num != "start" and num != "end":
                props["number"] = num

    # Dot marker
    if len(parts) > 7:
        props["dot"] = parts[7] if parts[7] != "0" else ""

    # Clock marker
    if len(parts) > 9:
        props["clock"] = parts[9] if parts[9] != "0" else ""

    # SVG path for pin graphics (used to determine pin length)
    if len(parts) > 2:
        path_data = parts[2].split("~")
        if path_data:
            svg = path_data[0]
            # Extract length from horizontal/vertical movement in path
            import re as _re
            nums = _re.findall(r'[-+]?\d*\.?\d+', svg)
            if nums:
                vals = [float(n) for n in nums]
                if len(vals) >= 2:
                    dx = abs(vals[0] - vals[-2]) if len(vals) >= 4 else abs(vals[0])
                    if dx < 1:
                        dx = 10
                    props["length"] = dx


def _parse_rect(f: list[str]) -> ParsedShape:
    props = {"x": float(f[1]), "y": float(f[2]), "width": float(f[3]), "height": float(f[4])}
    if len(f) > 6:
        props["fill"] = f[6]
    return ParsedShape(type="rect", props=props)


def _parse_arc(f: list[str]) -> ParsedShape:
    # Format: A~M x y A rx ry rotation arc-flag sweep-flag x2 y2~~color~...
    path = f[1] if len(f) > 1 else ""
    props = {"path": path}
    if len(f) > 3:
        props["color"] = f[3]
    return ParsedShape(type="arc", props=props)


def _parse_polyline(f: list[str]) -> ParsedShape:
    path = f[1] if len(f) > 1 else ""
    props = {"path": path}
    if len(f) > 3:
        props["color"] = f[3]
    return ParsedShape(type="polyline", props=props)


def _parse_text(f: list[str]) -> ParsedShape:
    # Format: T~type~x~y~rotation~text~font_info~color~...
    props: dict[str, Any] = {"text_type": f[1] if len(f) > 1 else "reference"}
    if len(f) > 2:
        props["x"] = float(f[2])
    if len(f) > 3:
        props["y"] = float(f[3])
    if len(f) > 4:
        try:
            props["rotation"] = float(f[4])
        except ValueError:
            props["rotation"] = 0.0
    if len(f) > 5:
        props["text"] = _decode_name(f[5])
    return ParsedShape(type="text", props=props)


def _parse_circle(f: list[str]) -> ParsedShape:
    # Format: C~cx~cy~rx~ry~color~...
    props: dict[str, Any] = {}
    if len(f) > 1:
        props["cx"] = float(f[1])
    if len(f) > 2:
        props["cy"] = float(f[2])
    if len(f) > 3:
        props["rx"] = float(f[3])
    if len(f) > 4:
        props["ry"] = float(f[4])
    return ParsedShape(type="circle", props=props)


def _parse_pad_string(raw: str) -> ParsedShape | None:
    """Parse a footprint pad/hole shape string."""
    if not raw:
        return None
    fields = raw.split("~")
    if len(fields) < 2:
        return None
    stype = fields[0]
    if stype == "PAD":
        return _parse_pad(fields)
    if stype == "HOLE":
        return _parse_hole(fields)
    if stype == "CIRCLE":
        return _parse_fp_circle(fields)
    if stype in ("TRACK", "ARC", "TEXT", "RECT", "SOLIDREGION"):
        return None  # skip complex shapes for now
    return None


def _parse_fp_circle(f: list[str]) -> ParsedShape:
    """Parse a CIRCLE shape from footprint data — treated as a pad."""
    props: dict[str, Any] = {}
    if len(f) > 1:
        try:
            props["x"] = float(f[1])
        except ValueError:
            pass
    if len(f) > 2:
        try:
            props["y"] = float(f[2])
        except ValueError:
            pass
    if len(f) > 3:
        try:
            props["radius"] = float(f[3])
        except ValueError:
            pass
    if len(f) > 4:
        try:
            props["drill"] = float(f[4])
        except ValueError:
            pass
    if len(f) > 5:
        props["layer"] = f[5]
    # Derive pad dimensions from radius
    r = props.get("radius", 0.5)
    props["width"] = r * 2
    props["height"] = r * 2
    props["hole_r"] = props.get("drill", 0)
    props["shape"] = "ELLIPSE"
    # Assign pad number based on order
    props["number"] = ""
    return ParsedShape(type="pad", props=props)


def _parse_pad(f: list[str]) -> ParsedShape:
    # PAD~SHAPE~x~y~width~height~layer~number~unknown~rotation~extent~...
    # or: PAD~x~y~width~height~hole_r~layer~number~soldermask~...
    props: dict[str, Any] = {}
    # Check if f[1] is a shape name or a coordinate
    try:
        float(f[1])
        coord_start = 1
    except ValueError:
        props["shape"] = f[1]  # OVAL, RECT, ELLIPSE, POLYGON
        coord_start = 2

    if len(f) > coord_start:
        try:
            props["x"] = float(f[coord_start])
        except ValueError:
            pass
    if len(f) > coord_start + 1:
        try:
            props["y"] = float(f[coord_start + 1])
        except ValueError:
            pass
    if len(f) > coord_start + 2:
        try:
            props["width"] = float(f[coord_start + 2])
        except ValueError:
            pass
    if len(f) > coord_start + 3:
        try:
            props["height"] = float(f[coord_start + 3])
        except ValueError:
            pass

    # Try to find pin number in fields
    for field in f[coord_start + 4:]:
        if field and field.isdigit():
            props["number"] = field
            break

    # Default hole radius
    props.setdefault("hole_r", 0.0)
    props.setdefault("layer", "1")
    props.setdefault("shape", props.get("shape", "ELLIPSE"))
    return ParsedShape(type="pad", props=props)


def _parse_hole(f: list[str]) -> ParsedShape:
    props: dict[str, Any] = {}
    if len(f) > 1:
        props["x"] = float(f[1])
    if len(f) > 2:
        props["y"] = float(f[2])
    if len(f) > 3:
        props["radius"] = float(f[3])
    if len(f) > 4:
        props["plated"] = f[4] != "NTPH"
    return ParsedShape(type="hole", props=props)


def _parse_fp_shape(raw: str) -> ParsedShape | None:
    """Parse a footprint-level shape (track, arc, text, circle, rect)."""
    if not raw:
        return None
    fields = raw.split("~")
    if len(fields) < 2:
        return None
    stype = fields[0]
    props: dict[str, Any] = {}
    try:
        if stype == "TRACK":
            props["width"] = float(fields[1]) if len(fields) > 1 else 0
            coords = fields[2].split() if len(fields) > 2 else []
            props["points"] = [(float(coords[i]), float(coords[i + 1])) for i in range(0, len(coords) - 1, 2) if i + 1 < len(coords)]
            if len(fields) > 3:
                props["layer"] = fields[3]
            return ParsedShape(type="fp_line", props=props)
        if stype == "ARC":
            props["width"] = float(fields[1]) if len(fields) > 1 else 0
            return ParsedShape(type="fp_arc", props=props)
        if stype == "TEXT":
            if len(fields) > 1:
                props["text"] = _decode_name(fields[1])
            if len(fields) > 2:
                props["x"] = float(fields[2])
            if len(fields) > 3:
                props["y"] = float(fields[3])
            if len(fields) > 4:
                try:
                    props["rotation"] = float(fields[4])
                except ValueError:
                    props["rotation"] = 0
            if len(fields) > 5:
                props["layer"] = fields[5]
            return ParsedShape(type="fp_text", props=props)
        if stype in ("CIRCLE", "C"):
            if len(fields) > 1:
                props["cx"] = float(fields[1])
            if len(fields) > 2:
                props["cy"] = float(fields[2])
            if len(fields) > 3:
                props["r"] = float(fields[3])
            if len(fields) > 4:
                props["width"] = float(fields[4])
            if len(fields) > 5:
                props["layer"] = fields[5]
            return ParsedShape(type="fp_circle", props=props)
        if stype == "SOLIDREGION":
            return ParsedShape(type="fp_solid", props=props)
    except (IndexError, ValueError):
        pass
    return None


def _decode_name(raw: str) -> str:
    """Decode EasyEDA name encoding (^^ → newline, ^^ prefix groups)."""
    if not raw:
        return ""
    parts = raw.split("^^")
    if len(parts) > 1:
        # Last non-empty part is usually the actual name
        for p in reversed(parts):
            if p.strip():
                return p.strip()
        return parts[-1].strip()
    # URL-encoded?
    if "%" in raw:
        try:
            from urllib.parse import unquote
            return unquote(raw)
        except Exception:
            pass
    return raw.strip()


def _decode_path_svg(path: str) -> list[dict[str, Any]]:
    """Parse an SVG-like path string into a list of command dicts.

    Returns list of {'cmd': 'M'|'L'|'A'|'h'|'v'|..., 'args': [float,...]}.
    """
    import re
    tokens = re.findall(r'[A-Za-z]|[-+]?\d*\.?\d+(?:e[-+]?\d+)?', path)
    result: list[dict[str, Any]] = []
    current_cmd = ""
    current_args: list[float] = []
    for t in tokens:
        if t and t[0].isalpha():
            if current_cmd and current_args:
                result.append({"cmd": current_cmd, "args": current_args})
            current_cmd = t
            current_args = []
        else:
            try:
                current_args.append(float(t))
            except ValueError:
                pass
    if current_cmd and current_args:
        result.append({"cmd": current_cmd, "args": current_args})
    return result

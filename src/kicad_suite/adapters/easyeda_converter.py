"""Convert parsed EasyEDA component data to KiCad symbol and footprint files.

Generates valid ``.kicad_sym`` and ``.kicad_mod`` s-expression output.
"""

from __future__ import annotations

import math
from typing import Any

from .easyeda_parser import (
    ParsedComponent,
    ParsedShape,
    eda_to_kicad_pos,
    eda_to_kicad_angle,
    _decode_path_svg,
)

# EasyEDA pin direction mapping: rotation → KiCad orientation
_ROTATION_TO_DIRECTION = {
    0: "right",
    90: "down",
    180: "left",
    270: "up",
}

# EasyEDA pin electrical type mapping
_ELEC_TYPE_MAP = {
    "0": "input",
    "1": "output",
    "2": "bidirectional",
    "3": "power_in",
    "4": "power_out",
    "5": "open_collector",
    "6": "open_emitter",
    "7": "passive",
    "8": "tri_state",
}


def build_kicad_symbol(comp: ParsedComponent, lib_name: str = "JLC-MCP") -> str:
    """Generate a KiCad 10 ``(symbol ...)`` block from a parsed EasyEDA component."""
    symbol_name = _sanitize_symbol_name(comp.title or comp.lcsc_id or "UNKNOWN")

    # Pin name offset
    total_pin_length = 0.0
    for s in comp.shapes:
        if s.type == "pin":
            length = float(s.props.get("length", 20))
            if length > total_pin_length:
                total_pin_length = length

    pin_name_offset = eda_to_kicad_pos(total_pin_length + 50)

    lines: list[str] = []
    lines.append(f'  (symbol "{symbol_name}"')

    # KiCad 10 required symbol-level fields
    lines.append('    (pin_numbers (hide yes))')
    lines.append(f'    (pin_names (offset {pin_name_offset:.3f}))')
    lines.append('    (exclude_from_sim no)')
    lines.append('    (in_bom yes)')
    lines.append('    (on_board yes)')
    lines.append('    (duplicate_pin_numbers_are_jumpers no)')

    # Properties
    prefix = comp.prefix or "U"
    ref_y = eda_to_kicad_pos(comp.bbox.get("height", 0) / 2 + 50)
    val_y = eda_to_kicad_pos(-comp.bbox.get("height", 0) / 2 - 50)
    fp_y = eda_to_kicad_pos(-80)

    lines.append(f'    (property "Reference" "{prefix}" (at 0 {ref_y} 0)'
                 f' (show_name no) (do_not_autoplace no)'
                 f' (effects (font (size 1.27 1.27)) (justify right)))')
    lines.append(f'    (property "Value" "{symbol_name}" (at 0 {val_y} 0)'
                 f' (show_name no) (do_not_autoplace no)'
                 f' (effects (font (size 1.27 1.27)) (justify right)))')
    lines.append(f'    (property "Footprint" "" (at 0 {fp_y} 0)'
                 f' (show_name no) (do_not_autoplace no) (hide yes)'
                 f' (effects (font (size 1.27 1.27)) (justify right)))')
    lines.append(f'    (property "Datasheet" "" (at 0 0 0)'
                 f' (show_name no) (do_not_autoplace no) (hide yes)'
                 f' (effects (font (size 1.27 1.27)) (justify right)))')
    lines.append(f'    (property "ki_locked" "" (at 0 0 0)'
                 f' (show_name no) (do_not_autoplace no) (hide yes)'
                 f' (effects (font (size 1.27 1.27)) (justify right)))')

    # Symbol body — draw the actual EasyEDA shapes (rectangles, polylines)
    # and compute body edges from them for pin placement.
    body_shapes: list[ParsedShape] = [s for s in comp.shapes if s.type != "pin"]
    pin_shapes: list[ParsedShape] = [s for s in comp.shapes if s.type == "pin" and s.props.get("show", True)]

    # Use shapes (rectangles) for body edges; fall back to BBox
    bx = eda_to_kicad_pos(comp.bbox.get("x", 0))
    by = eda_to_kicad_pos(comp.bbox.get("y", 0))
    bw = eda_to_kicad_pos(comp.bbox.get("width", 200))
    bh = eda_to_kicad_pos(comp.bbox.get("height", 200))
    body_l, body_r = bx - bw / 2, bx + bw / 2
    body_t, body_b = by + bh / 2, by - bh / 2

    lines.append(f'    (symbol "{symbol_name}_0_1"')
    for s in body_shapes:
        _symbol_shape_lines(s, lines)
    # If no explicit body shapes, draw fallback rectangle from BBox
    if not body_shapes:
        lines.append(f'      (rectangle (start {body_l} {body_b}) (end {body_r} {body_t})')
        lines.append(f'        (fill (type background)))')

    for s in pin_shapes:
        _symbol_pin_lines(s, lines, pin_name_offset, body_l, body_r, body_t, body_b)

    lines.append("    )")
    lines.append("  )")
    return "\n".join(lines)


def _sanitize_symbol_name(name: str) -> str:
    """Clean a name for use as a KiCad symbol name (no spaces, colons, etc.)."""
    result = name.replace(" ", "_").replace(":", "_").replace("/", "_")
    result = "".join(c for c in result if c.isalnum() or c in "_-.")
    return result[:80] or "UNKNOWN"


def _symbol_shape_lines(s: ParsedShape, lines: list[str]) -> None:
    """Add graphic shape lines (rectangle, polyline, circle) to a symbol."""
    try:
        if s.type == "rect":
            x = eda_to_kicad_pos(float(s.props.get("x", 0)))
            y = eda_to_kicad_pos(float(s.props.get("y", 0)))
            w = eda_to_kicad_pos(float(s.props.get("width", 20)))
            h = eda_to_kicad_pos(float(s.props.get("height", 20)))
            fill_type = "background" if s.props.get("fill") else "none"
            lines.append(f'      (rectangle (start {x - w / 2} {y - h / 2}) (end {x + w / 2} {y + h / 2})')
            lines.append(f'        (fill (type {fill_type})))')

        elif s.type == "polyline":
            path = s.props.get("path", "")
            cmds = _decode_path_svg(path)
            pts: list[tuple[float, float]] = []
            cx, cy = 0.0, 0.0
            for cmd in cmds:
                c = cmd["cmd"]
                args = cmd["args"]
                if c == "M":
                    cx, cy = args[0], args[1]
                    pts.append((eda_to_kicad_pos(cx), eda_to_kicad_pos(cy)))
                elif c == "L":
                    for i in range(0, len(args), 2):
                        cx, cy = args[i], args[i + 1]
                        pts.append((eda_to_kicad_pos(cx), eda_to_kicad_pos(cy)))
                elif c == "h":
                    cx += args[0]
                    pts.append((eda_to_kicad_pos(cx), eda_to_kicad_pos(cy)))
            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    lines.append(f'      (polyline (pts (xy {pts[i][0]:.3f} {pts[i][1]:.3f}) (xy {pts[i + 1][0]:.3f} {pts[i + 1][1]:.3f}))')
                    lines.append(f'        (stroke (width 0.254) (type default)))')

        elif s.type == "circle":
            cx = eda_to_kicad_pos(float(s.props.get("cx", 0)))
            cy = eda_to_kicad_pos(float(s.props.get("cy", 0)))
            r = eda_to_kicad_pos(float(s.props.get("rx", 10)))
            lines.append(f'      (circle (center {cx:.3f} {cy:.3f}) (radius {r:.3f})')
            lines.append(f'        (fill (type none)))')

        elif s.type == "arc":
            path = s.props.get("path", "")
            cmds = _decode_path_svg(path)
            for cmd in cmds:
                if cmd["cmd"] == "M":
                    pass  # skip move
                elif cmd["cmd"] == "A" and len(cmd["args"]) >= 7:
                    rx, ry, rot, arc, sweep, ex, ey = cmd["args"][:7]
                    # Calculate start point from previous move
                    # (simplified — full arc math is more complex)
                    pass
    except (ValueError, IndexError):
        pass


def _symbol_pin_lines(
    s: ParsedShape, lines: list[str], name_offset: float,
    body_left: float = -5.08, body_right: float = 5.08,
    body_top: float = 2.54, body_bottom: float = -2.54,
) -> None:
    """Generate pin s-expression for a symbol.  Pins are clamped to the body edges."""
    x = eda_to_kicad_pos(float(s.props.get("x", 0)))
    y = eda_to_kicad_pos(float(s.props.get("y", 0)))
    length = eda_to_kicad_pos(float(s.props.get("length", 20)))
    rotation = float(s.props.get("rotation", 0))
    name = s.props.get("name", "")
    number = s.props.get("number", "")

    direction = _ROTATION_TO_DIRECTION.get(int(rotation) % 360, "right")

    # Clamp the pin tip to the body edge so it always touches the rectangle
    if direction == "right":
        sx = max(x, body_right)
        sy = y
        ex = sx + length
        ey = y
    elif direction == "left":
        sx = min(x, body_left)
        sy = y
        ex = sx - length
        ey = y
    elif direction == "up":
        sx = x
        sy = max(y, body_top)
        ex = x
        ey = sy + length
    else:  # down
        sx = x
        sy = min(y, body_bottom)
        ex = x
        ey = sy - length

    ki_angle = int(eda_to_kicad_angle(rotation)) % 360
    lines.append(f'      (pin passive line (at {sx:.3f} {sy:.3f} {ki_angle}) (length {length:.3f})')
    lines.append(f'        (name "{name}" (effects (font (size 1.27 1.27))))')
    lines.append(f'        (number "{number}" (effects (font (size 1.27 1.27))))')
    lines.append("      )")


# -- Footprint conversion ----------------------------------------------------


def build_kicad_footprint(comp: ParsedComponent, lib_name: str = "JLC-MCP") -> str:
    """Generate a ``.kicad_mod`` s-expression string from parsed EasyEDA footprint data."""
    fp_name = _sanitize_symbol_name(comp.package_title or f"{comp.title}_footprint")
    lines = [
        f'(footprint "{fp_name}"',
        '  (version 20240108)',
        f'  (generator "hwtool_jlc")',
        f'  (layer "F.Cu")',
    ]

    # Text
    lines.append(f'  (fp_text reference "REF**" (at 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))')
    lines.append(f'  (fp_text value "{fp_name}" (at 0 2) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))')

    # Pads
    for pad in comp.pads:
        _footprint_pad_lines(pad, lines)

    # Holes
    for shape in comp.pads:
        if shape.type == "hole":
            _footprint_hole_lines(shape, lines)

    # Silkscreen and courtyard shapes
    for shape in comp.fp_shapes:
        _footprint_shape_lines(shape, lines)

    # Footprint texts (like pin-1 marker)
    for text in comp.fp_texts:
        _footprint_text_lines(text, lines)

    lines.append(")")
    return "\n".join(lines)


def _footprint_pad_lines(pad: ParsedShape, lines: list[str]) -> None:
    """Generate a pad s-expression."""
    p = pad.props
    x = eda_to_kicad_pos(float(p.get("x", 0)))
    y = -eda_to_kicad_pos(float(p.get("y", 0)))  # EasyEDA Y is inverted
    w = eda_to_kicad_pos(float(p.get("width", 20)))
    h = eda_to_kicad_pos(float(p.get("height", 20)))
    hole = eda_to_kicad_pos(float(p.get("hole_r", 0)) * 2)
    number = p.get("number", "")
    shape = p.get("shape", "ELLIPSE")
    layer = p.get("layer", "1")

    # Map shape to KiCad pad type
    if shape in ("OVAL", "RECT"):
        pad_type = "smd"
        pad_shape = "rect"
    elif shape == "POLYGON":
        pad_type = "smd"
        pad_shape = "rect"
    else:
        pad_type = "smd"
        pad_shape = "roundrect"

    # Layer mapping
    layers = ['"F.Cu"', '"F.Paste"', '"F.Mask"']
    if layer in ("11", "all"):
        layers = ['"*.Cu"', '"*.Mask"']

    if hole > 0:
        pad_type = "thru_hole"
        pad_shape = "circle"

    lines.append(f'  (pad "{number}" {pad_type} {pad_shape} (at {x:.3f} {y:.3f}) (size {w:.3f} {h:.3f})')
    if hole > 0:
        lines.append(f'    (drill {hole:.3f})')
    lines.append(f'    (layers {" ".join(layers)}))')


def _footprint_hole_lines(hole: ParsedShape, lines: list[str]) -> None:
    """Generate an NPTH hole."""
    h = hole.props
    x = eda_to_kicad_pos(float(h.get("x", 0)))
    y = -eda_to_kicad_pos(float(h.get("y", 0)))
    r = eda_to_kicad_pos(float(h.get("radius", 10)))
    plated = h.get("plated", False)
    layer = '"*.Cu" "*.Mask"' if plated else '"*.Cu"'
    lines.append(f'  (pad "" np_thru_hole circle (at {x:.3f} {y:.3f}) (size {r * 2:.3f} {r * 2:.3f})')
    lines.append(f'    (drill {r * 2:.3f}) (layers {layer}))')


def _footprint_shape_lines(shape: ParsedShape, lines: list[str]) -> None:
    """Generate silkscreen/fab lines and arcs."""
    p = shape.props
    try:
        if shape.type == "fp_line":
            pts = p.get("points", [])
            w = float(p.get("width", 1.5))
            kw = eda_to_kicad_pos(w)
            layer = _map_fp_layer(p.get("layer", ""))
            for i in range(len(pts) - 1):
                x1 = eda_to_kicad_pos(pts[i][0])
                y1 = -eda_to_kicad_pos(pts[i][1])
                x2 = eda_to_kicad_pos(pts[i + 1][0])
                y2 = -eda_to_kicad_pos(pts[i + 1][1])
                lines.append(f'  (fp_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f})')
                lines.append(f'    (stroke (width {kw:.3f}) (type solid)) (layer "{layer}"))')

        elif shape.type == "fp_circle":
            cx = eda_to_kicad_pos(float(p.get("cx", 0)))
            cy = -eda_to_kicad_pos(float(p.get("cy", 0)))
            r = eda_to_kicad_pos(float(p.get("r", 10)))
            w = eda_to_kicad_pos(float(p.get("width", 1.5)))
            layer = _map_fp_layer(p.get("layer", ""))
            lines.append(f'  (fp_circle (center {cx:.3f} {cy:.3f}) (end {cx + r:.3f} {cy:.3f})')
            lines.append(f'    (stroke (width {w:.3f}) (type solid)) (layer "{layer}"))')
    except (ValueError, IndexError):
        pass


def _footprint_text_lines(text: ParsedShape, lines: list[str]) -> None:
    """Generate footprint text."""
    p = text.props
    try:
        x = eda_to_kicad_pos(float(p.get("x", 0)))
        y = -eda_to_kicad_pos(float(p.get("y", 0)))
        rot = float(p.get("rotation", 0))
        txt = p.get("text", "")
        layer = _map_fp_layer(p.get("layer", ""))
        lines.append(f'  (fp_text user "{txt}" (at {x:.3f} {y:.3f} {rot:.0f})')
        lines.append(f'    (effects (font (size 1 1) (thickness 0.15))) (layer "{layer}"))')
    except (ValueError, IndexError):
        pass


def _map_fp_layer(raw: str) -> str:
    """Map EasyEDA layer numbers to KiCad layer names."""
    layer_map = {
        "1": "F.Cu",
        "2": "B.Cu",
        "3": "F.SilkS",
        "4": "B.SilkS",
        "5": "F.Paste",
        "6": "B.Paste",
        "7": "F.Mask",
        "8": "B.Mask",
        "10": "Edge.Cuts",
        "11": "F.Cu",  # multilayer pad
        "12": "Cmts.User",
        "13": "F.Fab",
        "21": "F.Cu",
        "22": "B.Cu",
    }
    return layer_map.get(raw, "F.SilkS")


def make_two_pin_symbol(ref: str, value: str, lib_name: str = "JLC-MCP") -> str:
    """Fallback: minimal 2-pin symbol for a component without full EasyEDA data."""
    name = _sanitize_symbol_name(value)
    return f"""  (symbol "{name}"
    (pin_numbers (hide yes))
    (pin_names (offset 2.54))
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (duplicate_pin_numbers_are_jumpers no)
    (property "Reference" "{ref[0] if ref else 'U'}" (at 0 5.08 0)
      (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27)) (justify right)))
    (property "Value" "{name}" (at 0 -5.08 0)
      (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27)) (justify right)))
    (property "Footprint" "" (at 0 -7.62 0)
      (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27)) (justify right)))
    (property "Datasheet" "" (at 0 0 0)
      (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27)) (justify right)))
    (property "ki_locked" "" (at 0 0 0)
      (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27)) (justify right)))
    (symbol "{name}_0_1"
      (rectangle (start -5.08 -2.54) (end 5.08 2.54)
        (fill (type background)))
      (pin passive line (at -5.08 0 0) (length 2.54)
        (name "1" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 5.08 0 180) (length 2.54)
        (name "2" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
    )
  )"""

"""Lightweight S-expression parser/emitter for KiCad file formats.

KiCad uses S-expression syntax for .kicad_sym, .kicad_sch, .kicad_mod,
.kicad_pcb, and related files.  This module replaces ad-hoc regex parsing
with a structured tree representation, avoiding the well-known corner
cases of regex-based S-expression handling (e.g. alphanumeric pin
numbers like "A1B12" being split into "A1" + "B12").

``parse(text)`` returns an :class:`SExprNode` tree; ``node.emit()``
serializes it back to KiCad-compatible text.

Usage::

    tree = parse(open("JLC-MCP.kicad_sym").read())
    for sym in tree.find("symbol"):
        name = sym.values[0]  # symbol name, e.g. "STM32F103C8T6"
        for pin in sym.find("pin"):
            num = pin.get("number")  # pin number, e.g. "32" or "A6"

Design goals
------------
- Zero external dependencies (stdlib only).
- Single-pass tokenizer + recursive-descent parser.
- Round-trip fidelity: ``parse(s).emit()`` is valid KiCad input (not
  necessarily byte-identical, but semantically equivalent).
- Small memory footprint — a 120 KB symbol library parses to ~2 MB.
"""

from __future__ import annotations

import io
from typing import Any


class SExprNode:
    """One node in a KiCad S-expression tree.

    Attributes
    ----------
    tag: str
        The keyword immediately after the opening paren, e.g. ``"symbol"``.
    values: list[str]
        Bare string tokens that appear before the first child node (if any).
    children: list[SExprNode]
        Nested child nodes, in document order.
    """

    __slots__ = ("tag", "values", "children")

    def __init__(self, tag: str = "") -> None:
        self.tag: str = tag
        self.values: list[str] = []
        self.children: list[SExprNode] = []

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def find(self, tag: str) -> list[SExprNode]:
        """Return direct children whose *tag* equals *tag*."""
        return [c for c in self.children if c.tag == tag]

    def find_all(self, tag: str) -> list[SExprNode]:
        """Recursively find all descendants whose *tag* equals *tag*."""
        result: list[SExprNode] = []
        for child in self.children:
            if child.tag == tag:
                result.append(child)
            result.extend(child.find_all(tag))
        return result

    def get(self, key: str) -> str | None:
        """Return the first value of the first child with *tag* == *key*.

        This is a convenience for the common KiCad pattern::

            (number "32")   →  node.get("number") → "32"
        """
        for child in self.children:
            if child.tag == key and child.values:
                return child.values[0]
        return None

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def set(self, key: str, value: str) -> SExprNode:
        """Update or create a child ``(key "value")``.

        If a child with *tag* == *key* already exists its first value is
        replaced; otherwise a new child is appended.
        """
        for child in self.children:
            if child.tag == key:
                if child.values:
                    child.values[0] = value
                else:
                    child.values.append(value)
                return child
        new_child = SExprNode(key)
        new_child.values.append(value)
        self.children.append(new_child)
        return new_child

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def emit(self, indent: int = 0, width: int = 2) -> str:
        """Return this node and its subtree as a KiCad S-expression string.

        *indent* is the starting indentation level (in spaces);
        *width* is the number of spaces per level.
        """
        buf = io.StringIO()
        self._emit_into(buf, indent, width)
        return buf.getvalue()

    def _emit_into(self, buf: io.StringIO, indent: int, width: int) -> None:
        prefix = " " * (indent * width)
        buf.write(prefix)
        buf.write("(")
        buf.write(self.tag)

        for v in self.values:
            buf.write(" ")
            buf.write(_quote_value(v))

        if self.children:
            buf.write("\n")
            for child in self.children:
                child._emit_into(buf, indent + 1, width)
                buf.write("\n")
            buf.write(prefix)
        buf.write(")")

    def __repr__(self) -> str:
        return f"SExprNode({self.tag!r}, values={self.values!r}, children={len(self.children)})"


# ======================================================================
# Tokenizer
# ======================================================================


def _tokenize(text: str) -> list[str]:
    """Split KiCad S-expression *text* into a flat list of tokens.

    Tokens are ``(``, ``)``, quoted strings (``"..."``), and bare words.
    Comments starting with ``;`` to end-of-line are silently discarded.
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # Whitespace
        if ch in " \t\r\n":
            i += 1
            continue

        # Line comments
        if ch == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue

        # Parens
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue

        # Quoted string
        if ch == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2  # skip escaped char
                elif text[j] == '"':
                    break
                else:
                    j += 1
            tokens.append(text[i : j + 1])
            i = j + 1
            continue

        # Bare word (stop at whitespace, paren, quote, or semicolon)
        j = i
        while j < n and text[j] not in ' \t\r\n();"':
            j += 1
        tokens.append(text[i:j])
        i = j

    return tokens


# ======================================================================
# Parser
# ======================================================================


def parse(text: str) -> SExprNode:
    """Parse a complete KiCad S-expression *text* into a tree."""
    tokens = _tokenize(text)
    root = SExprNode(tag="(root)")
    pos = 0
    while pos < len(tokens):
        if tokens[pos] != "(":
            # Top-level bare token — wrap it
            pos += 1
            continue
        node, pos = _parse_node(tokens, pos)
        root.children.append(node)
    return root


def _parse_node(tokens: list[str], pos: int) -> tuple[SExprNode, int]:
    """Parse one S-expression node starting at ``(``."""
    assert tokens[pos] == "(", f"Expected '(' at {pos}, got {tokens[pos]!r}"
    pos += 1  # skip '('

    if pos >= len(tokens) or tokens[pos] == ")":
        # Empty list
        return SExprNode(tag=""), pos + 1

    tag = tokens[pos]
    pos += 1

    node = SExprNode(tag=_unquote(tag))

    # Collect values and children until ')'
    while pos < len(tokens) and tokens[pos] != ")":
        token = tokens[pos]
        if token == "(":
            child, pos = _parse_node(tokens, pos)
            node.children.append(child)
        else:
            node.values.append(_unquote(token))
            pos += 1

    if pos < len(tokens) and tokens[pos] == ")":
        pos += 1  # skip ')'

    return node, pos


# ======================================================================
# Helpers
# ======================================================================


def _unquote(s: str) -> str:
    """Strip surrounding double-quotes and unescape backslash sequences."""
    if s.startswith('"') and s.endswith('"'):
        inner = s[1:-1]
        if "\\" in inner:
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return s


def _quote_value(s: str) -> str:
    """Quote *s* for safe inclusion in an S-expression.

    Bare words that are alphanumeric + ``_-./:+`` don't need quoting;
    everything else is wrapped in double-quotes.
    """
    if not s:
        return '""'
    # If already safe as a bare symbol, emit unquoted.
    if all(c.isalnum() or c in "_-./+:" for c in s) and not s[0].isdigit():
        return s
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ======================================================================
# High-level helpers for KiCad symbol libraries
# ======================================================================


def symbols_in_library(text: str) -> dict[str, SExprNode]:
    """Parse a ``.kicad_sym`` library and return ``{symbol_name: node}``.

    Multi-unit sub-symbols like ``"RP2040_0_1"`` are excluded; only the
    top-level symbol entries are returned.
    """
    import re
    root = parse(text)
    result: dict[str, SExprNode] = {}
    for sym in root.find_all("symbol"):
        name = sym.values[0] if sym.values else ""
        if name and not re.search(r"_\d+_\d+$", name):
            result[name] = sym
    return result


def pins_of_symbol(sym: SExprNode) -> list[dict[str, str]]:
    """Return ``[{number:, name:, type:}, ...]`` for every unit/pin in *sym*."""
    pins: list[dict[str, str]] = []
    for child in sym.children:
        if child.tag == "symbol":  # KiCad unit sub-symbol
            for pin in child.find("pin"):
                pins.append({
                    "number": pin.get("number") or "",
                    "name": pin.get("name") or "",
                    "type": pin.values[0] if pin.values else "",
                })
        elif child.tag == "pin":  # simple two-pin symbol
            pins.append({
                "number": child.get("number") or "",
                "name": child.get("name") or "",
                "type": child.values[0] if child.values else "",
            })
    return pins

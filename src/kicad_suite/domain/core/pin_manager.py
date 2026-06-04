"""Pin Manager: GPIO/pin resource tracker built on IR pinmap data.

Prevents AI agents from assigning two functions to the same GPIO.

GPIO capabilities are loaded from ``config/gpio-capabilities.json``.
Add new MCU families by editing that file ???no code changes needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Lazy-loaded cache of gpio-capabilities.json.
_cap_db_cache: dict[str, dict[str, list[str]]] | None = None
_config_path: Path | None = None


def _load_capability_db() -> dict[str, dict[str, list[str]]]:
    """Load gpio-capabilities.json (cached)."""
    global _cap_db_cache, _config_path
    if _cap_db_cache is not None:
        return _cap_db_cache
    from ...shared.env_utils import repo_root
    path = _config_path or repo_root() / 'config' / 'gpio-capabilities.json'
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        _cap_db_cache = {
            str(mcu): {
                str(pin): [str(c) for c in caps]
                for pin, caps in pins.items() if isinstance(caps, list)
            }
            for mcu, pins in raw.items() if isinstance(pins, dict)
        }
    else:
        _cap_db_cache = {}
    return _cap_db_cache


def set_capability_config_path(path: str | Path) -> None:
    """Override the default config path (for testing)."""
    global _config_path, _cap_db_cache
    _config_path = Path(path)
    _cap_db_cache = None


def reload_capability_db() -> dict[str, dict[str, list[str]]]:
    """Force-reload gpio-capabilities.json."""
    global _cap_db_cache
    _cap_db_cache = None
    return _load_capability_db()


class PinManager:
    """Track pin assignments, detect conflicts, and manage GPIO resources.

    Built on top of IR pinmap data.  Works with any MCU; the MCU-specific
    capability database is optional (falls back to ``["digital"]`` for any
    pin not in the database).
    """

    def __init__(
        self,
        ir: dict[str, Any],
        mcu_family: str = "",
    ) -> None:
        self._ir = ir
        self._mcu_family = mcu_family
        full_db = _load_capability_db()
        self._cap_db = full_db.get(mcu_family, {})

        # Build lookup: signal_name ->pin_number (from pinmap + net members).
        self._signal_to_pin: dict[str, str] = {}
        self._pin_to_signal: dict[str, str] = {}
        self._locked_pins: set[str] = set()

        pinmap = ir.get("pinmap", {})
        if isinstance(pinmap, dict):
            for ref, pins in pinmap.items():
                if isinstance(pins, dict):
                    for pin, entry in pins.items():
                        if isinstance(entry, dict):
                            net = str(entry.get("net", ""))
                            role = str(entry.get("role", ""))
                            signal = role if role else net
                            if signal:
                                full_pin = f"{ref}.{pin}"
                                self._signal_to_pin[signal] = full_pin
                                self._pin_to_signal[full_pin] = signal
                                if entry.get("locked"):
                                    self._locked_pins.add(full_pin)

    # -- queries ----------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        """Return all assigned pins with metadata."""
        result: list[dict[str, Any]] = []
        for signal, pin_ref in sorted(self._signal_to_pin.items()):
            ref, pin = pin_ref.rsplit(".", 1) if "." in pin_ref else ("", pin_ref)
            result.append({
                "pin": pin,
                "component_ref": ref,
                "signal": signal,
                "locked": pin_ref in self._locked_pins,
                "capabilities": self._capabilities(pin),
            })
        return result

    def list_free(self, mcu_ref: str = "") -> list[dict[str, Any]]:
        """Return GPIO pins that are not yet assigned to any signal."""
        if not mcu_ref:
            return []
        used_pins: set[str] = set()
        for pin_ref in self._pin_to_signal:
            ref, pin = pin_ref.rsplit(".", 1) if "." in pin_ref else ("", pin_ref)
            if ref == mcu_ref:
                used_pins.add(pin)
        free: list[dict[str, Any]] = []
        for gpio, caps in (self._cap_db or {}).items():
            if gpio not in used_pins:
                free.append({"pin": gpio, "component_ref": mcu_ref, "capabilities": caps})
        return free

    def get_owner(self, pin: str, ref: str = "") -> dict[str, Any] | None:
        """Return the signal assigned to *pin* on *ref*, or None if free."""
        pin_ref = f"{ref}.{pin}" if ref else pin
        signal = self._pin_to_signal.get(pin_ref)
        if signal is None:
            # Try prefix match.
            for pr, sig in self._pin_to_signal.items():
                if pr.endswith(f".{pin}"):
                    return {
                        "pin": pin,
                        "component_ref": pr.split(".", 1)[0],
                        "signal": sig,
                        "locked": pr in self._locked_pins,
                        "capabilities": self._capabilities(pin),
                    }
            return None
        return {
            "pin": pin,
            "component_ref": ref,
            "signal": signal,
            "locked": pin_ref in self._locked_pins,
            "capabilities": self._capabilities(pin),
        }

    def check_conflict(self, pin: str, ref: str, signal: str) -> str | None:
        """Return an error message if *pin* on *ref* is already taken by another signal.

        Returns ``None`` if no conflict.
        """
        pin_ref = f"{ref}.{pin}"
        existing = self._pin_to_signal.get(pin_ref)
        if existing and existing != signal:
            locked = " (LOCKED)" if pin_ref in self._locked_pins else ""
            return f"Pin {pin} on {ref} is already assigned to '{existing}'{locked}, cannot assign to '{signal}'"
        return None

    def check_pin_capability(self, pin: str, required_cap: str) -> str | None:
        """Return an error if *pin* does not support *required_cap*.

        Returns ``None`` if the pin has the required capability.
        """
        caps = [c.lower() for c in self._capabilities(pin)]
        req = required_cap.lower()
        if req not in caps and "digital" in caps:
            return None  # digital pins can do anything basic
        if req not in caps:
            return f"Pin {pin} does not support {required_cap}. Available: {caps}"
        return None

    def is_locked(self, pin: str, ref: str = "") -> bool:
        """Return True if *pin* on *ref* is locked."""
        pin_ref = f"{ref}.{pin}" if ref else pin
        if pin_ref in self._locked_pins:
            return True
        for pr in self._locked_pins:
            if pr.endswith(f".{pin}"):
                return True
        return False

    # -- utilities --------------------------------------------------------

    def _capabilities(self, pin: str) -> list[str]:
        if self._cap_db and pin in self._cap_db:
            return list(self._cap_db[pin])
        return ["digital"]


def build_pin_assignment_table(pin_manager: PinManager) -> str:
    """Render a Markdown pin-assignment table."""
    rows = ["| Pin | Component | Signal | Locked | Capabilities |",
            "|-----|-----------|--------|--------|--------------|"]
    for entry in pin_manager.list_all():
        lock = "LOCKED" if entry["locked"] else ""
        caps = ", ".join(entry.get("capabilities", [])[:3])
        rows.append(
            f"| {entry['pin']} | {entry['component_ref']} | {entry['signal']} | {lock} | {caps} |"
        )
    return "\n".join(rows)

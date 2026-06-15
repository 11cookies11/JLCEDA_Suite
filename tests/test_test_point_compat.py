from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.symbol_footprint_resolver import symbol_mapping_for
from kicad_suite.domain.core.ir_compiler import build_ir
from kicad_suite.shared.test_point_compat import (
    DEFAULT_TEST_POINT_DISPLAY_NAME,
    DEFAULT_TEST_POINT_FOOTPRINT,
    DEFAULT_TEST_POINT_PACKAGE,
    DEFAULT_TEST_POINT_SYMBOL_REF,
    normalize_test_point_selected_part,
)


class TestTestPointCompatibility(unittest.TestCase):
    def test_normalize_test_point_selected_part_replaces_placeholder_names(self) -> None:
        component = {"role": "test_point"}
        selected_part = {
            "display_name": "TP_1P",
            "symbol_ref": "TP_1P",
            "package": "TP-SMD",
            "kicad_footprint_hint": "TP-SMD_1P",
        }

        normalized = normalize_test_point_selected_part(component, selected_part)

        self.assertEqual(normalized["display_name"], DEFAULT_TEST_POINT_DISPLAY_NAME)
        self.assertEqual(normalized["package"], DEFAULT_TEST_POINT_PACKAGE)
        self.assertEqual(normalized["mechanical_package"], DEFAULT_TEST_POINT_PACKAGE)
        self.assertEqual(normalized["symbol_ref"], DEFAULT_TEST_POINT_SYMBOL_REF)
        self.assertEqual(normalized["kicad_footprint_hint"], DEFAULT_TEST_POINT_FOOTPRINT)

    def test_symbol_mapping_for_test_point_uses_standard_library_names(self) -> None:
        component = {
            "ref": "TP1",
            "role": "test_point",
            "value": "+3V3",
            "selected_part": {
                "display_name": "TP_1P",
                "symbol_ref": "TP_1P",
                "kicad_footprint_hint": "TP-SMD_1P",
                "package": "TP-SMD",
            },
        }

        lib_id, footprint, notes = symbol_mapping_for(component)

        self.assertEqual(lib_id, DEFAULT_TEST_POINT_SYMBOL_REF)
        self.assertEqual(footprint, DEFAULT_TEST_POINT_FOOTPRINT)
        self.assertTrue(notes)

    def test_build_ir_normalizes_test_point_selected_parts(self) -> None:
        ir = build_ir(
            {
                "components": [
                    {
                        "ref": "TP1",
                        "role": "test_point",
                        "value": "+3V3",
                        "selected_part": {
                            "display_name": "TP_1P",
                            "symbol_ref": "TP_1P",
                            "kicad_footprint_hint": "TP-SMD_1P",
                            "package": "TP-SMD",
                        },
                    }
                ],
                "nets": [],
                "sheets": [],
            }
        )

        selected_part = ir["components"][0]["selected_part"]
        self.assertEqual(selected_part["display_name"], DEFAULT_TEST_POINT_DISPLAY_NAME)
        self.assertEqual(selected_part["package"], DEFAULT_TEST_POINT_PACKAGE)
        self.assertEqual(selected_part["mechanical_package"], DEFAULT_TEST_POINT_PACKAGE)
        self.assertEqual(selected_part["symbol_ref"], DEFAULT_TEST_POINT_SYMBOL_REF)
        self.assertEqual(selected_part["kicad_footprint_hint"], DEFAULT_TEST_POINT_FOOTPRINT)


if __name__ == "__main__":
    unittest.main()

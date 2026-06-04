"""Tests for LCSC resolver backends and normalization."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.lcsc_resolver import (
    LcscOpenApiBackend,
    _extract_jlc_mcp_results,
    _extract_lcsc_product_dicts,
    _normalize_result,
)


class TestLcscOpenApiBackend(unittest.TestCase):
    def test_unconfigured_backend_returns_no_results(self):
        backend = LcscOpenApiBackend(key="", secret="")
        self.assertFalse(backend.configured)
        self.assertEqual(backend.search("STM32G431", limit=3), [])

    def test_extracts_nested_product_payloads(self):
        payload = {
            "code": 200,
            "data": {
                "page": {
                    "list": [
                        {
                            "lcscPartNumber": "C529365",
                            "productModel": "STM32G431CBT6",
                            "brandName": "ST",
                        }
                    ]
                }
            },
        }

        products = _extract_lcsc_product_dicts(payload)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["lcscPartNumber"], "C529365")


class TestLcscNormalization(unittest.TestCase):
    def test_normalizes_openapi_product_fields(self):
        part = _normalize_result({
            "_source": "jlcpcb_parts",
            "lcscPartNumber": "C529365",
            "productModel": "STM32G431CBT6",
            "brandName": "STMicroelectronics",
            "encapStandard": "LQFP-48",
            "stockNumber": "1200",
            "productDesc": "ARM Cortex-M4 MCU",
            "productPrice": "2.50",
        })

        self.assertEqual(part.lcsc_id, "C529365")
        self.assertEqual(part.mpn, "STM32G431CBT6")
        self.assertEqual(part.manufacturer, "STMicroelectronics")
        self.assertEqual(part.package, "LQFP-48")
        self.assertEqual(part.stock, 1200)
        self.assertEqual(part.price, 2.5)

    def test_extracts_jlc_mcp_bridge_results(self):
        products = _extract_jlc_mcp_results({
            "ok": True,
            "result": {
                "success": True,
                "results": [
                    {"lcsc_id": "C14663", "name": "CC0603KRX7R9BB104"},
                    "ignored",
                ],
            },
        })

        self.assertEqual(products, [{"lcsc_id": "C14663", "name": "CC0603KRX7R9BB104"}])

    def test_normalizes_jlc_mcp_fields(self):
        part = _normalize_result({
            "_source": "jlcpcb_parts",
            "lcsc_id": "C14663",
            "name": "CC0603KRX7R9BB104",
            "manufacturer": "YAGEO",
            "description": "100nF 50V X7R",
            "package": "0603",
            "stock": 1000,
            "price": 0.0031,
            "library_type": "basic",
        })

        self.assertEqual(part.lcsc_id, "C14663")
        self.assertEqual(part.mpn, "CC0603KRX7R9BB104")
        self.assertEqual(part.basic_or_extended, "Basic")


if __name__ == "__main__":
    unittest.main()

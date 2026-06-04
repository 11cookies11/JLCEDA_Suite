"""Tests for Part Selector module."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.lcsc_resolver import PartRequirement, ResolvedPart, ResolverResult
from kicad_suite.domain.core.part_selector import (
    RiskItem,
    SelectedPart,
    SelectionResult,
    classify_package_risk,
    package_risk_note,
    select_part,
    select_parts,
)


def _make_candidate(**overrides: object) -> ResolvedPart:
    defaults: dict[str, object] = dict(
        lcsc_id="C2040",
        mpn="AMS1117-3.3",
        manufacturer="AMS",
        package="SOT-223",
        description="3.3V LDO, 1A",
        stock=5000,
        basic_or_extended="Basic",
        price=0.12,
        has_easyeda_symbol=True,
        has_easyeda_footprint=True,
        has_3d_model=True,
        source="jlcpcb_parts",
        confidence=0.85,
    )
    defaults.update(overrides)
    defaults.pop("_scan_text", None)
    return ResolvedPart(**defaults)  # type: ignore[arg-type]


def _make_requirement(**overrides: object) -> PartRequirement:
    defaults: dict[str, object] = dict(
        id="test_req",
        function="3.3V LDO regulator",
        preferred_mpn=["AMS1117-3.3"],
        package_preferred=["SOT-223"],
        output_voltage=3.3,
        assembly="JLCPCB",
        price_max=0.50,
    )
    defaults.update(overrides)
    return PartRequirement(**defaults)  # type: ignore[arg-type]


def _make_result(candidates: list[ResolvedPart], **overrides: object) -> ResolverResult:
    defaults: dict[str, object] = dict(
        id="test_req",
        candidates=candidates,
        query_context={},
    )
    defaults.update(overrides)
    return ResolverResult(**defaults)  # type: ignore[arg-type]


class TestScorePart(unittest.TestCase):
    """Scoring algorithm tests."""

    def test_mpn_exact_match_yields_highest_score(self):
        candidate = _make_candidate(mpn="AMS1117-3.3")
        req = _make_requirement(preferred_mpn=["AMS1117-3.3"])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertGreaterEqual(sel.selected.composite_score, 50.0)
        self.assertTrue(any("MPN exact match" in r for r in sel.selected.reasons))

    def test_mpn_partial_match(self):
        candidate = _make_candidate(mpn="AMS1117-3.3-TR")
        req = _make_requirement(preferred_mpn=["AMS1117"])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("MPN partial match" in r for r in sel.selected.reasons))

    def test_package_exact_match(self):
        candidate = _make_candidate(package="SOT-223")
        req = _make_requirement(package_preferred=["SOT-223"])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Package exact match" in r for r in sel.selected.reasons))

    def test_package_partial_match(self):
        candidate = _make_candidate(package="SOT-223-3")
        req = _make_requirement(package_preferred=["SOT-223"])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Package" in r for r in sel.selected.reasons))

    def test_basic_part_bonus(self):
        candidate = _make_candidate(basic_or_extended="Basic")
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Basic Part" in r for r in sel.selected.reasons))

    def test_extended_part_no_bonus(self):
        candidate = _make_candidate(basic_or_extended="Extended")
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertFalse(any("Basic Part" in r for r in sel.selected.reasons))

    def test_high_stock_bonus(self):
        candidate = _make_candidate(stock=15000)
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Very high stock" in r for r in sel.selected.reasons))

    def test_medium_stock_bonus(self):
        candidate = _make_candidate(stock=500)
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Adequate stock" in r for r in sel.selected.reasons))

    def test_low_stock_no_bonus(self):
        candidate = _make_candidate(stock=50)
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertFalse(any("stock" in r.lower() for r in sel.selected.reasons if "risk" not in r.lower()))

    def test_complex_package_penalty_bga(self):
        candidate = _make_candidate(package="BGA-256")
        req = _make_requirement(package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Complex package penalty" in r for r in sel.selected.reasons))

    def test_complex_package_penalty_qfn(self):
        candidate = _make_candidate(package="QFN-32")
        req = _make_requirement(package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Complex package penalty" in r for r in sel.selected.reasons))

    def test_price_within_budget(self):
        candidate = _make_candidate(price=0.10)
        req = _make_requirement(price_max=0.50)
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("within budget" in r for r in sel.selected.reasons))

    def test_library_completeness_bonus(self):
        candidate = _make_candidate(has_easyeda_symbol=True, has_easyeda_footprint=True, has_3d_model=True)
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any("Complete EasyEDA library" in r for r in sel.selected.reasons))

    def test_score_never_negative(self):
        candidate = _make_candidate(
            package="BGA-256",
            stock=0,
            basic_or_extended="Extended",
            price=None,
            has_easyeda_symbol=False,
            has_easyeda_footprint=False,
            has_3d_model=False,
            source="easyeda_community",
            mpn="unknown",
            lcsc_id="",
        )
        req = _make_requirement(preferred_mpn=[], package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertGreaterEqual(sel.selected.composite_score, 0.0)


class TestRiskAssessment(unittest.TestCase):
    """Risk assessment tests."""

    def test_bga_package_high_risk(self):
        candidate = _make_candidate(package="BGA-256")
        req = _make_requirement(package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        pkg_risks = [r for r in sel.selected.risks if r.category == "package_risk"]
        self.assertTrue(any(r.level == "high" for r in pkg_risks))

    def test_qfn_package_medium_risk(self):
        candidate = _make_candidate(package="QFN-32")
        req = _make_requirement(package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        pkg_risks = [r for r in sel.selected.risks if r.category == "package_risk"]
        self.assertTrue(any(r.level == "medium" for r in pkg_risks))

    def test_low_stock_high_risk(self):
        candidate = _make_candidate(stock=50)
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        stock_risks = [r for r in sel.selected.risks if r.category == "stock_risk"]
        self.assertTrue(any(r.level == "high" for r in stock_risks))

    def test_missing_price_risk(self):
        candidate = _make_candidate(price=None)
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any(r.category == "missing_data" and "Price" in r.message for r in sel.selected.risks))

    def test_community_source_risk(self):
        candidate = _make_candidate(source="easyeda_community", lcsc_id="")
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any(r.category == "source_risk" for r in sel.selected.risks))

    def test_price_exceeds_budget_risk(self):
        candidate = _make_candidate(price=2.00)
        req = _make_requirement(price_max=0.50)
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(any(r.category == "price_risk" for r in sel.selected.risks))

    def test_low_score_high_risk(self):
        candidate = _make_candidate(
            package="BGA-100",
            stock=0,
            has_easyeda_symbol=False,
            has_easyeda_footprint=False,
            has_3d_model=False,
            source="easyeda_community",
            lcsc_id="",
            basic_or_extended="Extended",
            price=None,
        )
        req = _make_requirement(preferred_mpn=[], package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        score_risks = [r for r in sel.selected.risks if r.category == "score_too_low"]
        self.assertTrue(any(r.level == "high" for r in score_risks))


class TestNeedsReview(unittest.TestCase):
    """Needs-review determination tests."""

    def test_low_score_needs_review(self):
        candidate = _make_candidate(
            package="BGA-100",
            stock=0,
            has_easyeda_symbol=False,
            has_easyeda_footprint=False,
            has_3d_model=False,
        )
        req = _make_requirement(preferred_mpn=[], package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(sel.selected.needs_review)

    def test_high_risk_triggers_review(self):
        candidate = _make_candidate(stock=5)  # triggers stock_risk high
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertTrue(sel.selected.needs_review)

    def test_good_candidate_no_review(self):
        candidate = _make_candidate()
        req = _make_requirement()
        result = _make_result([candidate])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertFalse(sel.selected.needs_review)


class TestSelectParts(unittest.TestCase):
    """Batch selection tests."""

    def test_empty_candidates_returns_none(self):
        req = _make_requirement()
        result = _make_result([])
        sel = select_part(req, result)
        self.assertIsNone(sel.selected)
        self.assertEqual(sel.all_candidates, [])

    def test_selects_highest_scored(self):
        best = _make_candidate(mpn="AMS1117-3.3", price=0.10, stock=10000)
        worse = _make_candidate(mpn="AMS1117-3.3-TR", price=0.15, stock=1000)
        req = _make_requirement()
        result = _make_result([worse, best])
        sel = select_part(req, result)
        assert sel.selected is not None
        self.assertEqual(sel.selected.mpn, "AMS1117-3.3")

    def test_select_parts_batch(self):
        reqs = [
            _make_requirement(id="ldo", function="3.3V LDO"),
            _make_requirement(id="cap", function="100nF capacitor"),
        ]
        results = [
            _make_result([_make_candidate(lcsc_id="C1001", mpn="LDO-1")], id="ldo"),
            _make_result([_make_candidate(lcsc_id="C1002", mpn="CAP-1")], id="cap"),
        ]
        selections = select_parts(reqs, results)
        self.assertEqual(len(selections), 2)
        self.assertIsNotNone(selections[0].selected)
        self.assertIsNotNone(selections[1].selected)

    def test_select_parts_missing_resolver_result(self):
        reqs = [_make_requirement(id="ldo")]
        results: list[ResolverResult] = []
        selections = select_parts(reqs, results)
        self.assertEqual(len(selections), 1)
        self.assertIsNone(selections[0].selected)

    def test_below_min_score_returns_none(self):
        candidate = _make_candidate(
            package="BGA-100", stock=0, price=None,
            has_easyeda_symbol=False, has_easyeda_footprint=False, has_3d_model=False,
            source="easyeda_community", lcsc_id="",
        )
        req = _make_requirement(preferred_mpn=[], package_preferred=[])
        result = _make_result([candidate])
        sel = select_part(req, result, min_score=30.0)
        self.assertIsNone(sel.selected)


class TestPackageRiskClassifier(unittest.TestCase):
    """EasyEDA import risk classification tests."""

    def test_0603_resistor_low_risk(self):
        self.assertEqual(classify_package_risk("0603"), "low")

    def test_0805_capacitor_low_risk(self):
        self.assertEqual(classify_package_risk("0805"), "low")

    def test_sot23_low_risk(self):
        self.assertEqual(classify_package_risk("SOT-23"), "low")

    def test_sop_low_risk(self):
        self.assertEqual(classify_package_risk("SOP-8"), "low")

    def test_qfn_low_risk(self):
        self.assertEqual(classify_package_risk("QFN-32"), "low")

    def test_bga_medium_risk(self):
        self.assertEqual(classify_package_risk("BGA-256"), "medium")

    def test_sot223_low_risk(self):
        self.assertEqual(classify_package_risk("SOT-223"), "low")

    def test_3225_crystal_low_risk(self):
        self.assertEqual(classify_package_risk("3225"), "low")

    def test_module_medium_risk(self):
        self.assertEqual(classify_package_risk("SMD Module"), "medium")

    def test_usb_c_high_risk(self):
        self.assertEqual(classify_package_risk("USB-C 16P"), "high")

    def test_fpc_high_risk(self):
        self.assertEqual(classify_package_risk("FPC-30"), "high")

    def test_tf_card_high_risk(self):
        self.assertEqual(classify_package_risk("TF-Card Slot"), "high")

    def test_dc_jack_high_risk(self):
        self.assertEqual(classify_package_risk("DC Jack 2.1mm"), "high")

    def test_unknown_package_medium(self):
        self.assertEqual(classify_package_risk("Mystery-Package-XYZ"), "medium")


class TestPackageRiskNote(unittest.TestCase):
    """Risk note generation tests."""

    def test_low_risk_note(self):
        note = package_risk_note("0603", "low")
        self.assertIn("Standard package", note)

    def test_medium_module_note(self):
        note = package_risk_note("SMD Module", "medium")
        self.assertIn("Module", note)

    def test_high_usb_note(self):
        note = package_risk_note("USB-C 16P", "high")
        self.assertIn("USB", note)

    def test_high_fpc_note(self):
        note = package_risk_note("FPC-30", "high")
        self.assertIn("FPC", note)


if __name__ == "__main__":
    unittest.main()

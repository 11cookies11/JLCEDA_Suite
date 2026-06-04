"""Tests for agent-friendly ERC classification."""

from __future__ import annotations

from kicad_suite.application_services.erc_classifier import classify_erc_report


def test_classify_generated_symbol_pin_noise() -> None:
    report = {
        "sheets": [
            {
                "path": "/power/",
                "violations": [
                    {
                        "type": "pin_to_pin",
                        "severity": "warning",
                        "description": "Unspecified connected to Input",
                        "items": [
                            {"description": "Symbol U2 pin 2 [VOUT, Unspecified, Line]"},
                            {"description": "Symbol R3 pin 1 [1, Input, Line]"},
                        ],
                    }
                ],
            }
        ]
    }

    classification = classify_erc_report(report)

    assert classification["finding_count"] == 1
    assert classification["counts"]["library_noise"] == 1
    assert classification["counts"]["must_fix"] == 0


def test_classify_unknown_error_as_must_fix() -> None:
    report = {
        "sheets": [
            {
                "path": "/mcu/",
                "violations": [
                    {
                        "type": "multiple_net_names",
                        "severity": "error",
                        "description": "Two net names on the same wire",
                        "items": [
                            {"description": "Label +3V3"},
                            {"description": "Label GND"},
                        ],
                    }
                ],
            }
        ]
    }

    classification = classify_erc_report(report)

    assert classification["finding_count"] == 1
    assert classification["counts"]["must_fix"] == 1
    assert classification["counts"]["library_noise"] == 0


def test_classify_warning_as_review_required() -> None:
    report = {
        "sheets": [
            {
                "path": "/",
                "violations": [
                    {
                        "type": "footprint_filter",
                        "severity": "warning",
                        "description": "Assigned footprint does not match filters",
                        "items": [{"description": "Symbol U1"}],
                    }
                ],
            }
        ]
    }

    classification = classify_erc_report(report)

    assert classification["finding_count"] == 1
    assert classification["counts"]["review_required"] == 1

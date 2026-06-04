"""Tests for source/resolved circuit model merging."""

from __future__ import annotations

from kicad_suite.domain.core.circuit_model_io import merge_circuit_models


def test_merge_deduplicates_scalar_risks() -> None:
    source = {
        "schema_version": "circuit-model.v1",
        "risks": [
            "Generated JLC symbols may still need pin-type normalization.",
        ],
    }
    resolved = {
        "risks": [
            "Generated JLC symbols may still need pin-type normalization.",
        ],
    }

    merged = merge_circuit_models(source, resolved)

    assert merged["risks"] == [
        "Generated JLC symbols may still need pin-type normalization.",
    ]


def test_merge_deduplicates_keyless_object_risks() -> None:
    risk = {"title": "Review generated symbol pin types", "status": "open"}
    merged = merge_circuit_models({"risks": [risk]}, {"risks": [risk]})

    assert merged["risks"] == [risk]


def test_source_keyless_risks_replace_stale_resolved_keyless_risks() -> None:
    merged = merge_circuit_models(
        {"risks": ["New source risk"]},
        {"risks": ["Old resolved risk"]},
    )

    assert merged["risks"] == ["New source risk"]

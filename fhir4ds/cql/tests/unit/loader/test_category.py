"""Unit tests for category mapping + text normalization.

Reference: FDD §3c step 1, §3e.
"""

from __future__ import annotations

import pytest

from fhir4ds.cql.loader.category import (
    RESOURCE_TYPE_TO_CATEGORY,
    normalize_text,
    resolve_category,
)


def test_resolve_category_known_resource_types():
    assert resolve_category("Condition") == "condition"
    assert resolve_category("Observation") == "lab"
    assert resolve_category("MedicationRequest") == "medication"
    assert resolve_category("MedicationStatement") == "medication"
    assert resolve_category("Medication") == "medication"
    assert resolve_category("Procedure") == "procedure"
    assert resolve_category("Immunization") == "vaccine"
    assert resolve_category("BodyStructure") == "body_structure"


def test_resolve_category_unknown_returns_none():
    """Unknown resource types return None (no crash)."""
    assert resolve_category("Patient") is None
    assert resolve_category("FooBar") is None
    assert resolve_category("") is None


def test_resolve_category_override_takes_precedence():
    """User-provided overrides win over the default map."""
    overrides = {"Observation": "vital", "CustomResource": "lab"}
    assert resolve_category("Observation", overrides) == "vital"
    assert resolve_category("CustomResource", overrides) == "lab"
    # Non-overridden types fall through to default
    assert resolve_category("Condition", overrides) == "condition"


def test_resolve_category_override_with_empty_dict():
    """Empty override dict falls through to default."""
    assert resolve_category("Condition", {}) == "condition"


def test_resource_type_to_category_map_immutability_safety():
    """Spot-check the map is the documented one."""
    expected_keys = {
        "Condition", "Observation", "MedicationRequest", "MedicationStatement",
        "Medication", "Procedure", "Immunization", "BodyStructure",
    }
    assert set(RESOURCE_TYPE_TO_CATEGORY.keys()) == expected_keys


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Type 2 Diabetes Mellitus", "type 2 diabetes mellitus"),
        ("  Extra  Whitespace  ", "extra whitespace"),
        ("Punctuation! Strip, It.", "punctuation strip it"),
        ("Already-Normalized", "already normalized"),
        ("Tabs\tAnd\nNewlines", "tabs and newlines"),
        ("TRAILING      ", "trailing"),
        ("", ""),
        ("   ", ""),
        ("ALL CAPS", "all caps"),
        ("MiXeD CaSe", "mixed case"),
        ("Hyphen-Word", "hyphen word"),
        ("Multi   Space", "multi space"),
        ("Comma,Sep,No,Space", "comma sep no space"),
    ],
)
def test_normalize_text_cases(raw, expected):
    assert normalize_text(raw) == expected


def test_normalize_text_idempotent():
    """normalize_text is idempotent — applying twice equals applying once."""
    samples = [
        "Type 2 Diabetes Mellitus",
        "Some   Messy !@#  Text",
        "Already clean",
        "",
        "   ",
    ]
    for s in samples:
        once = normalize_text(s)
        twice = normalize_text(once)
        assert once == twice, f"Idempotency broken for {s!r}: {once!r} vs {twice!r}"


def test_normalize_text_nfkc_normalization():
    """NFKC folds fullwidth digits and ligatures to canonical forms."""
    # Fullwidth digit
    assert normalize_text("Ｔ２ＤＭ") == "t2dm"
    # Ligature fi
    assert normalize_text("ﬁnancial") == "financial"


def test_normalize_text_rejects_non_string():
    with pytest.raises(TypeError, match="expected str"):
        normalize_text(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="expected str"):
        normalize_text(42)  # type: ignore[arg-type]

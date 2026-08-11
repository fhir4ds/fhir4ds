"""Unit tests for derived_from_text_extension builder/parser."""

from __future__ import annotations

import pytest

from fhir4ds.cql.loader.derived_from_text_extension import (
    DERIVED_FROM_TEXT_EXTENSION_URL,
    build_derived_from_text_extension,
    is_derived_from_text,
    parse_derived_from_text_extension,
)


def test_builder_produces_correct_sub_extension_shape():
    """Builder produces exactly the 5 sub-extensions with documented URLs/value types."""
    ext = build_derived_from_text_extension(
        source_ref="Observation/abc",
        source_path="note[0].text",
        span_start=12,
        span_end=27,
        matched_text="chest pain",
    )
    assert ext["url"] == DERIVED_FROM_TEXT_EXTENSION_URL
    subs = ext["extension"]
    assert len(subs) == 5
    by_url = {s["url"]: s for s in subs}
    assert set(by_url.keys()) == {
        "source-ref", "source-path", "span-start",
        "span-end", "matched-text",
    }
    assert by_url["source-ref"]["valueString"] == "Observation/abc"
    assert by_url["source-path"]["valueString"] == "note[0].text"
    assert by_url["span-start"]["valueInteger"] == 12
    assert by_url["span-end"]["valueInteger"] == 27
    assert by_url["matched-text"]["valueString"] == "chest pain"


def test_builder_round_trips_with_parser():
    """Parser round-trips the builder output."""
    ext = build_derived_from_text_extension(
        source_ref="DocumentReference/doc-1",
        source_path="content[0].attachment.data",
        span_start=0,
        span_end=11,
        matched_text="hypertension",
    )
    resource = {"resourceType": "Condition", "extension": [ext]}
    parsed = parse_derived_from_text_extension(resource)
    assert parsed is not None
    assert parsed["source_ref"] == "DocumentReference/doc-1"
    assert parsed["source_path"] == "content[0].attachment.data"
    assert parsed["span_start"] == 0
    assert parsed["span_end"] == 11
    assert parsed["matched_text"] == "hypertension"


def test_all_five_sub_fields_present():
    """All 5 sub-fields are present after parsing (none should be None)."""
    ext = build_derived_from_text_extension(
        source_ref="Encounter/enc-1",
        source_path="reason[0].valueString",
        span_start=3,
        span_end=18,
        matched_text="chest discomfort",
    )
    resource = {"extension": [ext]}
    parsed = parse_derived_from_text_extension(resource)
    assert parsed is not None
    for field_name in (
        "source_ref", "source_path", "span_start", "span_end", "matched_text",
    ):
        assert parsed[field_name] is not None, f"{field_name} should not be None"


def test_parser_returns_none_when_extension_absent():
    """Parser returns None when the resource lacks the extension."""
    resource = {
        "resourceType": "Condition",
        "extension": [{"url": "http://example.com/other", "extension": []}],
    }
    parsed = parse_derived_from_text_extension(resource)
    assert parsed is None


def test_is_derived_from_text_predicate():
    """is_derived_from_text returns True iff the extension is present."""
    ext = build_derived_from_text_extension(
        source_ref="Observation/x",
        source_path="note[0].text",
        span_start=0,
        span_end=1,
        matched_text="x",
    )
    resource_with = {"extension": [ext]}
    resource_without = {"extension": []}
    assert is_derived_from_text(resource_with) is True
    assert is_derived_from_text(resource_without) is False


def test_builder_rejects_negative_offsets():
    """Builder rejects negative span offsets."""
    with pytest.raises(ValueError):
        build_derived_from_text_extension(
            source_ref="Observation/x",
            source_path="note[0].text",
            span_start=-1,
            span_end=5,
            matched_text="x",
        )


def test_builder_coerces_int_like_offsets():
    """Builder accepts int-like values (numpy ints, Decimals) via int() coercion."""
    class IntLike:
        def __int__(self):
            return 42
    ext = build_derived_from_text_extension(
        source_ref="Observation/x",
        source_path="note[0].text",
        span_start=IntLike(),
        span_end=IntLike(),
        matched_text="x",
    )
    subs = {s["url"]: s for s in ext["extension"]}
    assert subs["span-start"]["valueInteger"] == 42
    assert subs["span-end"]["valueInteger"] == 42

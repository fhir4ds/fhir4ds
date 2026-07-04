"""Unit tests for autocoding_extension builder/parser.

Reference: FDD §3d, §7 INV-5.
"""

from __future__ import annotations

import math

import pytest

from fhir4ds.cql.loader.autocoding_extension import (
    AUTOCODING_EXTENSION_URL,
    build_autocoding_extension,
    is_autocoded,
    parse_autocoding_extension,
)


def test_build_autocoding_extension_six_fields_exact_shape():
    """INV-5: builder produces exactly the 6 sub-extensions with documented URLs and value types."""
    ext = build_autocoding_extension(
        engine="medterm4ds",
        engine_version="0.0.1",
        search_mode="hybrid",
        score=0.87,
        match_grade="certain",
        index_version="2026AA-bm25-v3",
    )

    assert ext["url"] == AUTOCODING_EXTENSION_URL
    subs = ext["extension"]
    assert len(subs) == 6

    # Build a URL → (value-type, value) map for assertion clarity.
    by_url = {s["url"]: s for s in subs}
    assert set(by_url.keys()) == {
        "engine", "engine-version", "search-mode",
        "score", "match-grade", "index-version",
    }

    # Value types per FDD §3d
    assert by_url["engine"]["valueString"] == "medterm4ds"
    assert by_url["engine-version"]["valueString"] == "0.0.1"
    assert by_url["search-mode"]["valueCode"] == "hybrid"
    assert by_url["score"]["valueDecimal"] == pytest.approx(0.87)
    assert by_url["match-grade"]["valueCode"] == "certain"
    assert by_url["index-version"]["valueString"] == "2026AA-bm25-v3"


def test_build_autocoding_extension_index_version_none_normalized_to_unknown():
    """index_version=None is normalized to 'unknown' literal (so field always present)."""
    ext = build_autocoding_extension(
        engine="medterm4ds",
        engine_version="0.0.1",
        search_mode="hybrid",
        score=0.5,
        match_grade="probable",
        index_version=None,
    )
    by_url = {s["url"]: s for s in ext["extension"]}
    assert by_url["index-version"]["valueString"] == "unknown"


@pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), float("-inf")])
def test_build_autocoding_extension_rejects_non_finite_score(bad_score):
    """NaN/inf scores would break json.dumps(allow_nan=False). ValueError raised."""
    with pytest.raises(ValueError, match="finite"):
        build_autocoding_extension(
            engine="medterm4ds",
            engine_version="0.0.1",
            search_mode="hybrid",
            score=bad_score,
            match_grade="certain",
            index_version="v1",
        )


def test_build_autocoding_extension_coerces_int_score():
    """Integer scores are coerced to float (json-safe)."""
    ext = build_autocoding_extension(
        engine="medterm4ds",
        engine_version="0.0.1",
        search_mode="hybrid",
        score=1,  # int
        match_grade="certain",
        index_version="v1",
    )
    by_url = {s["url"]: s for s in ext["extension"]}
    assert isinstance(by_url["score"]["valueDecimal"], float)
    assert by_url["score"]["valueDecimal"] == 1.0


def test_parse_autocoding_extension_round_trip():
    """parse_autocoding_extension inverts build_autocoding_extension."""
    ext = build_autocoding_extension(
        engine="medterm4ds",
        engine_version="0.0.1",
        search_mode="hybrid",
        score=0.42,
        match_grade="certain",
        index_version="v9",
    )
    coding = {"system": "http://snomed.info/sct", "code": "73211009", "extension": [ext]}
    parsed = parse_autocoding_extension(coding)
    assert parsed is not None
    assert parsed["engine"] == "medterm4ds"
    assert parsed["engine_version"] == "0.0.1"
    assert parsed["search_mode"] == "hybrid"
    assert parsed["score"] == pytest.approx(0.42)
    assert parsed["match_grade"] == "certain"
    assert parsed["index_version"] == "v9"


def test_parse_autocoding_extension_returns_none_for_plain_coding():
    """Plain Coding without the extension returns None."""
    coding = {"system": "http://snomed.info/sct", "code": "73211009"}
    assert parse_autocoding_extension(coding) is None


def test_parse_autocoding_extension_returns_none_for_other_extension():
    """Coding with a different extension returns None."""
    coding = {
        "extension": [
            {"url": "http://example.org/other", "extension": []}
        ]
    }
    assert parse_autocoding_extension(coding) is None


def test_parse_autocoding_extension_missing_sub_fields_return_none():
    """Forward compat: missing sub-extension fields parse to None, not KeyError."""
    coding = {
        "extension": [
            {
                "url": AUTOCODING_EXTENSION_URL,
                "extension": [
                    {"url": "engine", "valueString": "medterm4ds"},
                ],
            }
        ]
    }
    parsed = parse_autocoding_extension(coding)
    assert parsed is not None
    assert parsed["engine"] == "medterm4ds"
    assert parsed["score"] is None  # missing
    assert parsed["match_grade"] is None  # missing


def test_is_autocoded_true_for_coding_with_extension():
    coding = {
        "extension": [
            build_autocoding_extension(
                engine="medterm4ds", engine_version="0.0.1",
                search_mode="hybrid", score=0.1,
                match_grade="certain", index_version="v1",
            )
        ]
    }
    assert is_autocoded(coding) is True


def test_is_autocoded_false_for_plain_coding():
    assert is_autocoded({"system": "http://snomed.info/sct", "code": "X"}) is False


def test_parse_autocoding_extension_handles_non_dict_input():
    assert parse_autocoding_extension(None) is None  # type: ignore[arg-type]
    assert parse_autocoding_extension("not a dict") is None  # type: ignore[arg-type]

"""Regression tests for CQL regex UDFs (Matches / ReplaceMatches / SplitOnMatches).

These tests lock in the spec-compliant null semantics mandated by CQL §17:

  * Matches / ReplaceMatches / SplitOnMatches return None *only* when one of
    their input arguments is null.
  * A syntactically valid pattern that the implementation declines to
    evaluate (e.g. the ReDoS guard) must raise a typed error rather than
    silently returning None, so the rejection is visible and does not
    propagate as a misleading null through downstream boolean logic.

History: QA-001 (CQL-12 SKEPTIC iteration 1) found that ``_compile_cql_regex``
silently returned ``None`` for ReDoS-flagged patterns, causing
``cqlRegexMatches('aaa', r'(a+)+')`` to return ``None`` instead of raising.
The CQL spec only authorizes ``None`` when an input argument is null.
"""
from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb.extension import register_cql
from fhir4ds.cql.duckdb.udf.string import (
    CQLRegexPatternRejected,
    cqlRegexMatches,
    cqlRegexReplaceMatches,
    cqlRegexSplitOnMatches,
)


def _fresh_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    register_cql(con)
    return con


class TestCqlRegexMatchesNullSemantics:
    """CQL §17 Matches: 'If either argument is null, the result is null.'"""

    def test_both_arguments_null_returns_none(self) -> None:
        assert cqlRegexMatches(None, None) is None

    def test_string_null_returns_none(self) -> None:
        assert cqlRegexMatches(None, r"\d+") is None

    def test_pattern_null_returns_none(self) -> None:
        assert cqlRegexMatches("abc", None) is None

    def test_valid_pattern_returns_bool(self) -> None:
        # CQL spec normative examples (cql.hl7.org/09-b-cqlreference.html)
        assert cqlRegexMatches("1,2three", r"\d,\d\w+") is True
        assert cqlRegexMatches("abc", r"\d+") is False
        assert cqlRegexMatches("   ", r"\W+") is True

    def test_redos_pattern_raises_typed_error(self) -> None:
        """ReDoS-guarded patterns must raise, not silently return None.

        Regression for QA-001: silent None violated the CQL §17 contract.
        """
        with pytest.raises(CQLRegexPatternRejected):
            cqlRegexMatches("aaa", r"(a+)+")
        with pytest.raises(CQLRegexPatternRejected):
            cqlRegexMatches("aaa", r"(a|a)+")


class TestCqlRegexReplaceMatchesNullSemantics:
    """CQL §17 ReplaceMatches: 'If any argument is null, the result is null.'"""

    def test_any_null_argument_returns_none(self) -> None:
        assert cqlRegexReplaceMatches(None, "x", "y") is None
        assert cqlRegexReplaceMatches("abc", None, "y") is None
        assert cqlRegexReplaceMatches("abc", "x", None) is None

    def test_valid_substitution(self) -> None:
        # CQL spec normative example
        assert cqlRegexReplaceMatches("ABCDE", "C", "XYZ") == "ABXYZDE"
        # \$ literal dollar
        assert (
            cqlRegexReplaceMatches("All that glitters is not gold", r"\s", r"\$")
            == "All$that$glitters$is$not$gold"
        )

    def test_redos_pattern_raises_typed_error(self) -> None:
        with pytest.raises(CQLRegexPatternRejected):
            cqlRegexReplaceMatches("aaa", r"(a+)+", "x")

    def test_invalid_backref_raises_typed_error(self) -> None:
        """Replacement referencing a group the pattern does not capture must
        raise, not silently return None or silently substitute empty.

        Regression for CQL-12 EXPLORER QA-001: previously the Python helper
        caught re.error ('invalid group reference') and returned None,
        violating the CQL §17 contract that None is authorized only when
        an input argument is null. The C++ extension's std::regex_replace
        silently substitutes empty for unmatched group references, which
        is a documented intentional platform diff (see
        extensions/cql/AGENTS.md).
        """
        with pytest.raises(CQLRegexPatternRejected):
            # Pattern 'a' has no capture groups; '$1' references group 1.
            cqlRegexReplaceMatches("abc", "a", "$1")
        with pytest.raises(CQLRegexPatternRejected):
            # Pattern '(a)' captures group 1 only; '$2' references group 2.
            cqlRegexReplaceMatches("abc", "(a)", "$2")


class TestCqlRegexSplitOnMatchesNullSemantics:
    """CQL §17 SplitOnMatches: 'If the stringToSplit argument is null, the
    result is null.' The separatorPattern semantics mirror Matches."""

    def test_null_string_returns_none(self) -> None:
        assert cqlRegexSplitOnMatches(None, r"\d") is None

    def test_null_pattern_returns_none(self) -> None:
        assert cqlRegexSplitOnMatches("abc", None) is None

    def test_valid_split(self) -> None:
        assert cqlRegexSplitOnMatches("a1b2c3", r"\d") == ["a", "b", "c", ""]

    def test_redos_pattern_raises_typed_error(self) -> None:
        with pytest.raises(CQLRegexPatternRejected):
            cqlRegexSplitOnMatches("aaa", r"(a+)+")


class TestCqlRegexUdfsThroughDuckDB:
    """End-to-end tests through the DuckDB SQL surface (Matches, ReplaceMatches,
    SplitOnMatches macros)."""

    def test_spec_normative_matches_examples_pass(self) -> None:
        con = _fresh_connection()
        cases = [
            ("1,2three", r"\d,\d\w+", True),
            ("Not all who wander are lost - circa 2017", r".*\d+", True),
            ("Not all who wander are lost", r".*\d+", False),
            ("http://fhir.org/guides/cqf/common/Library/FHIR-ModelInfo|4.0.1", "Library", True),
        ]
        for s, pat, expected in cases:
            actual = con.execute("SELECT Matches(?, ?)", [s, pat]).fetchone()[0]
            assert actual == expected, f"Matches({s!r}, {pat!r}) = {actual!r}, expected {expected!r}"

    def test_null_input_propagates_through_duckdb(self) -> None:
        con = _fresh_connection()
        assert con.execute("SELECT Matches(?, ?)", ["x", None]).fetchone()[0] is None
        assert con.execute("SELECT Matches(?, ?)", [None, "x"]).fetchone()[0] is None

    def test_redos_pattern_raises_through_duckdb(self) -> None:
        """Regression test: previously returned None silently through DuckDB."""
        con = _fresh_connection()
        with pytest.raises(duckdb.Error):
            con.execute("SELECT Matches(?, ?)", ["aaa", r"(a+)+"]).fetchone()
        with pytest.raises(duckdb.Error):
            con.execute("SELECT ReplaceMatches(?, ?, ?)", ["aaa", r"(a+)+", "x"]).fetchone()
        with pytest.raises(duckdb.Error):
            con.execute("SELECT SplitOnMatches(?, ?)", ["aaa", r"(a+)+"]).fetchone()

    def test_invalid_backref_raises_through_duckdb(self) -> None:
        """Regression for CQL-12 EXPLORER QA-001 through DuckDB surface.

        Previously the Python helper caught re.error and returned None,
        which propagated as NULL through DuckDB. Per CQL §17, None/NULL is
        authorized only when an input argument is null.
        """
        con = _fresh_connection()
        with pytest.raises(duckdb.Error):
            con.execute(
                "SELECT ReplaceMatches(?, ?, ?)", ["abc", "a", "$1"]
            ).fetchone()

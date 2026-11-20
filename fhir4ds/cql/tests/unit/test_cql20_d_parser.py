"""Parser-surface unit tests for CQL 2.0 directives + parameter features (chunk CQL20-D)."""

from __future__ import annotations

import pytest

from fhir4ds.cql.errors import ParseError
from fhir4ds.cql.parser import parse_cql


class TestDirectiveParsing:
    def test_bare_directive(self):
        lib = parse_cql("#AllowFluent\nlibrary T\ndefine X: 1")
        assert len(lib.directives) == 1
        d = lib.directives[0]
        assert d.name == "AllowFluent"
        assert d.value is None
        assert d.inclusion_behavior is None

    def test_quoted_string_value(self):
        lib = parse_cql("#DefaultComparisonPrecision: 'minute'\nlibrary T")
        d = lib.directives[0]
        assert d.name == "DefaultComparisonPrecision"
        assert d.value == "minute"
        assert d.inclusion_behavior is None

    def test_quoted_plural_precision_normalized_amux152_5(self):
        """AMUX-152 #5: the directive grammar accepts quoted precision
        strings, and the quoted form is equivalent to the unquoted one —
        a quoted PLURAL must singularize exactly like the token branch
        ('minutes' -> 'minute'), or the translator's precision validation
        rejects the library."""
        lib = parse_cql("#DefaultComparisonPrecision: 'minutes'\nlibrary T")
        d = lib.directives[0]
        assert d.name == "DefaultComparisonPrecision"
        assert d.value == "minute", (
            f"quoted plural must normalize to the singular precision, got {d.value!r}"
        )
        assert d.inclusion_behavior is None

    def test_quoted_plural_precision_translates_amux152_5(self):
        from fhir4ds.cql.translator import translate_cql

        results = translate_cql(
            "#DefaultComparisonPrecision: 'hours'\n"
            "library DP152 version '1.0.0'\n"
            "using FHIR version '4.0.1'\n"
            "context Patient\n"
            "define Probe: 1 + 1\n"
        )
        assert "Probe" in results

    def test_unquoted_precision_value_normalized(self):
        lib = parse_cql("#DefaultComparisonPrecision: minutes\nlibrary T")
        assert lib.directives[0].value == "minute"

    def test_inclusion_behaviors(self):
        for clause in (
            "default included libraries",
            "override included libraries",
            "check included libraries",
        ):
            lib = parse_cql(
                f"#DefaultComparisonPrecision: 'day' {clause}\nlibrary T"
            )
            assert lib.directives[0].inclusion_behavior == clause
            assert lib.directives[0].value == "day"

    def test_directives_must_precede_library(self):
        # A directive AFTER the library declaration is an error (directives
        # are only at the very beginning per the 2.0 grammar).
        with pytest.raises(ParseError):
            parse_cql("library T\n#DefaultComparisonPrecision: minutes\ndefine X: 1")

    def test_non_string_non_precision_value_rejected(self):
        with pytest.raises(ParseError, match="precision value"):
            parse_cql("#DefaultComparisonPrecision: 5\nlibrary T")

    def test_malformed_inclusion_behavior_rejected(self):
        with pytest.raises(ParseError, match="libraries"):
            parse_cql(
                "#DefaultComparisonPrecision: 'day' default included\nlibrary T"
            )

    def test_inclusion_behavior_on_other_directive_rejected(self):
        with pytest.raises(ParseError, match="DefaultComparisonPrecision"):
            parse_cql("#Other: 'x' default included libraries\nlibrary T")

    def test_hash_without_identifier_rejected(self):
        with pytest.raises(ParseError, match="directive identifier"):
            parse_cql("# 5\nlibrary T")

    def test_multiple_directives(self):
        lib = parse_cql(
            "#AllowFluent\n#DefaultComparisonPrecision: 'day'\nlibrary T"
        )
        assert [d.name for d in lib.directives] == [
            "AllowFluent",
            "DefaultComparisonPrecision",
        ]


class TestIncludeBindParsing:
    def test_bind_clause_parses(self):
        lib = parse_cql(
            "library T\n"
            "parameter \"Measurement Period\" Interval<DateTime>\n"
            "include CCE called C bind { AsOf: end of \"Measurement Period\" }\n"
        )
        inc = lib.includes[0]
        assert inc.path == "CCE"
        assert inc.alias == "C"
        assert list(inc.bindings.keys()) == ["AsOf"]

    def test_bind_multiple_entries(self):
        lib = parse_cql(
            "library T\n"
            "parameter A Integer\n"
            "include L bind { X: A + 1, Y: 5 }\n"
        )
        assert set(lib.includes[0].bindings.keys()) == {"X", "Y"}

    def test_bind_without_called(self):
        lib = parse_cql("library T\ninclude L bind { X: 5 }\n")
        assert lib.includes[0].bindings is not None

    def test_no_bind_clause_leaves_none(self):
        lib = parse_cql("library T\ninclude L\n")
        assert lib.includes[0].bindings is None

    def test_empty_bind_rejected(self):
        with pytest.raises(ParseError, match="at least one parameter"):
            parse_cql("library T\ninclude L bind { }\n")

    def test_duplicate_bind_key_rejected(self):
        with pytest.raises(ParseError, match="Duplicate"):
            parse_cql("library T\nparameter A Integer\ninclude L bind { X: A, X: 2 }\n")

    def test_missing_colon_rejected(self):
        with pytest.raises(ParseError):
            parse_cql("library T\ninclude L bind { X 5 }\n")


class TestParameterConstraintTagParsing:
    def test_constraint_extracted(self):
        lib = parse_cql(
            """library T
parameter P Integer default 5
/*
@constraint: error
@message: P must be big enough
*/
define C: P >= 3
"""
        )
        (c,) = lib.parameter_constraints
        assert c.definition_name == "C"
        assert c.severity == "error"
        assert c.message == "P must be big enough"
        assert c.scope is None

    def test_constraint_scope_parameter(self):
        lib = parse_cql(
            """library T
/*
@constraint: warning
@constraintScope: parameter
*/
define C: 1
"""
        )
        (c,) = lib.parameter_constraints
        assert c.severity == "warning"
        assert c.scope == "parameter"

    def test_invalid_severity_rejected(self):
        with pytest.raises(ParseError, match="error' or 'warning"):
            parse_cql(
                "library T\n/*\n@constraint: fatal\n*/\ndefine C: 1\n"
            )

    def test_invalid_scope_rejected(self):
        with pytest.raises(ParseError, match="parameter"):
            parse_cql(
                "library T\n/*\n@constraint: error\n@constraintScope: library\n*/\ndefine C: 1\n"
            )

    def test_message_without_constraint_rejected(self):
        with pytest.raises(ParseError, match="@constraint"):
            parse_cql(
                "library T\n/*\n@message: orphan\n*/\ndefine C: 1\n"
            )

    def _dup(self):
        parse_cql(
            "library T\n/*\n@constraint: error\n@constraint: warning\n*/\ndefine C: 1\n"
        )

    def test_duplicate_constraint_tag_rejected(self):
        with pytest.raises(ParseError, match="Duplicate"):
            self._dup()

    def test_untagged_library_has_no_constraints(self):
        lib = parse_cql("library T\ndefine X: 1")
        assert lib.parameter_constraints == []

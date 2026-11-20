"""CQL 2.0 lexer/parser/declaration relaxations — chunk CQL20-B (parse-level).

Covers (campaign cql20_spec_campaign, AMUX-33):
  * #11 Relaxed library versioning / multi-version constraints (FHIR-57620)
  * #12 Tags without a value (FHIR-37827) — annotation comment tags
  * #14 Conversion grammar: `convert X to <unit>` bare precision keywords
    (FHIR-52783 grammar surface; RI lowers unit targets to ConvertQuantity)
  * #21 Model qualifiers in `using` (FHIR-31019)
  * #22 Model aliases (`using ... called X`, FHIR-48762)

Ground truth: CQL 2.0 (R2 STU 1) grammar
(https://cql.hl7.org/grammar.html, HL7/cql master input/images/cql/cql.g4)
and Developer's Guide
(https://cql.hl7.org/03-developersguide.html — Libraries / Data Models /
Tags sections, post-FHIR-57620 reconciliation text).
"""

from __future__ import annotations

import pytest

from fhir4ds.cql.errors import ParseError
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.annotations import (
    AnnotationTag,
    parse_annotation_tags,
    parse_library_tags,
)
from fhir4ds.cql.parser.ast_nodes import Literal, NamedTypeSpecifier
from fhir4ds.cql.translator import CQLToSQLTranslator


def _using_of(source: str):
    lib = parse_cql(source)
    assert lib.using, "expected at least one using declaration"
    return lib.using[0]


class TestModelQualifiersFhir31019:
    """usingDefinition : 'using' qualifiedIdentifier ('version' ...)? ('called' ...)?"""

    def test_qualified_model_name_parses(self):
        using = _using_of(
            "library T\n"
            "using hl7.fhir.us.core.USCore version '7.0.0'\n"
            "context Patient\n"
        )
        assert using.model == "hl7.fhir.us.core.USCore"
        assert using.version == "7.0.0"

    def test_qualified_model_name_without_version_parses(self):
        using = _using_of(
            "library T\nusing hl7.fhir.us.core.USCore\ncontext Patient\n"
        )
        assert using.model == "hl7.fhir.us.core.USCore"
        assert using.version is None

    def test_plain_model_still_parses(self):
        using = _using_of(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
        )
        assert using.model == "FHIR"
        assert using.version == "4.0.1"

    def test_qualified_model_with_called_parses(self):
        using = _using_of(
            "library T\n"
            "using hl7.fhir.us.core.USCore version '7.0.0' called USC\n"
            "context Patient\n"
        )
        assert using.model == "hl7.fhir.us.core.USCore"
        assert using.version == "7.0.0"
        assert using.alias == "USC"


class TestModelAliasesFhir48762:
    """`using X version 'y' called Z` — the CALLED clause on using declarations."""

    def test_called_alias_parses(self):
        using = _using_of(
            "library T\nusing FHIR version '4.0.1' called FH\ncontext Patient\n"
        )
        assert using.model == "FHIR"
        assert using.alias == "FH"

    def test_alias_defaults_to_none_without_called(self):
        using = _using_of(
            "library T\nusing FHIR version '4.0.1'\ncontext Patient\n"
        )
        assert using.alias is None

    def test_called_requires_identifier(self):
        with pytest.raises(ParseError):
            parse_cql(
                "library T\nusing FHIR version '4.0.1' called\ncontext Patient\n"
            )

    def test_called_alias_library_still_translates(self):
        # Aliased using must not disturb the rest of the library parse.
        lib = parse_cql(
            "library T\n"
            "using FHIR version '4.0.1' called FH\n"
            "context Patient\n"
            "define \"Age\": AgeInYears()\n"
        )
        assert [d.name for d in lib.statements] == ["Age"]


class TestMultipleVersionConstraintsFhir57620:
    """FHIR-57620: a given library SHALL NOT include multiple versions of the
    same library, and multiple versions of the same model SHALL NOT be
    referenced in the same library (Developer's Guide, post-reconciliation).
    """

    def test_same_library_two_versions_rejected(self):
        with pytest.raises(ParseError, match="(?i)multiple versions"):
            parse_cql(
                "library T\n"
                "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
                "include FHIRHelpers version '4.0.0' called FHIRHelpersOld\n"
                "context Patient\n"
            )

    def test_same_library_same_version_twice_accepted(self):
        lib = parse_cql(
            "library T\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "include FHIRHelpers version '4.0.1' called FH\n"
            "context Patient\n"
        )
        assert len(lib.includes) == 2

    def test_same_library_unversioned_plus_versioned_accepted(self):
        # Only explicitly-DIFFERENT version specifiers are "multiple versions".
        lib = parse_cql(
            "library T\n"
            "include FHIRHelpers called FHIRHelpers\n"
            "include FHIRHelpers version '4.0.1' called FH\n"
            "context Patient\n"
        )
        assert len(lib.includes) == 2

    def test_same_model_two_versions_rejected(self):
        with pytest.raises(ParseError, match="(?i)multiple versions"):
            parse_cql(
                "library T\n"
                "using hl7.fhir.us.core.USCore version '7.0.0' called USCore7\n"
                "using hl7.fhir.us.core.USCore version '8.0.0' called USCore8\n"
                "context Patient\n"
            )

    def test_same_model_same_version_twice_accepted(self):
        lib = parse_cql(
            "library T\n"
            "using FHIR version '4.0.1' called FHIR1\n"
            "using FHIR version '4.0.1' called FHIR2\n"
            "context Patient\n"
        )
        assert len(lib.using) == 2

    def test_different_models_accepted(self):
        lib = parse_cql(
            "library T\n"
            "using FHIR version '4.0.1'\n"
            "using hl7.fhir.us.core.USCore version '7.0.0' called USC\n"
            "context Patient\n"
        )
        assert len(lib.using) == 2


class TestIncludeVersionDiscrepancyWarningFhir57620:
    """Versioned includes that resolve to a differently-versioned library
    are an implementation-environment concern (FHIR-57620); our loader
    resolves by identifier and surfaces the discrepancy as a WARNING.
    """

    def test_mismatched_include_version_logs_warning(self, caplog):
        lib_b = parse_cql(
            "library LibB version '2.0.0'\n"
            "context Patient\n"
            "define \"Ok\": true\n"
        )
        lib_a = parse_cql(
            "library LibA version '1.0.0'\n"
            "include LibB version '1.5.0' called B\n"
            "context Patient\n"
            "define \"Ref\": B.\"Ok\"\n"
        )

        translator = CQLToSQLTranslator(library_loader=lambda path: lib_b)
        translator.translate_library_to_population_sql(lib_a)
        assert any(
            "version discrepancy" in record.message.lower()
            and "'1.5.0'" in record.message
            and "'2.0.0'" in record.message
            for record in caplog.records
        )

    def test_matching_include_version_logs_no_warning(self, caplog):
        import logging

        caplog.set_level(logging.WARNING)

        lib_b = parse_cql(
            "library LibB version '1.5.0'\n"
            "context Patient\n"
            "define \"Ok\": true\n"
        )
        lib_a = parse_cql(
            "library LibA version '1.0.0'\n"
            "include LibB version '1.5.0' called B\n"
            "context Patient\n"
            "define \"Ref\": B.\"Ok\"\n"
        )

        translator = CQLToSQLTranslator(library_loader=lambda path: lib_b)
        translator.translate_library_to_population_sql(lib_a)
        assert not any(
            "version discrepancy" in record.message.lower()
            for record in caplog.records
        )


class TestConvertUnitTargetsFhir52783:
    """conversionExpressionTerm : 'convert' expression 'to' (typeSpecifier | unit)

    The `unit` alternative (FHIR-52783 grammar surface) accepts UCUM strings
    AND bare date-time precision keywords (year..millisecond, singular and
    plural). The reference implementation lowers unit targets to
    ConvertQuantity.
    """

    @pytest.mark.parametrize(
        "unit", ["day", "days", "year", "years", "month", "months", "week",
                 "weeks", "hour", "hours", "minute", "minutes", "second",
                 "seconds", "millisecond", "milliseconds"]
    )
    def test_bare_precision_keyword_is_unit_target(self, unit):
        expr = parse_expression(f"convert 5 to {unit}")
        assert isinstance(expr.right, Literal)
        assert expr.right.value == unit

    def test_quoted_unit_target_still_unit(self):
        expr = parse_expression("convert 5 'mg' to 'g'")
        assert isinstance(expr.right, Literal)
        assert expr.right.value == "g"

    def test_qualified_type_target_still_type_specifier(self):
        expr = parse_expression("convert '5' to System.Integer")
        assert isinstance(expr.right, NamedTypeSpecifier)
        assert expr.right.name == "System.Integer"


class TestAnnotationTagsFhir37827:
    """Tags: comment-level annotations `@name` or `@name: value`.

    FHIR-37827: value-less tags are legal ("@inclusion with no value").
    Tag value runs to the next tag or the end of the comment block
    (Developer's Guide, Tags).
    """

    def test_valueless_tag(self):
        tags = parse_annotation_tags(
            "/*\n@inclusion\n@author: Frederic Chopin\n*/"
        )
        assert tags == [
            AnnotationTag(name="inclusion", value=None),
            AnnotationTag(name="author", value="Frederic Chopin"),
        ]

    def test_tag_value_runs_to_next_tag(self):
        tags = parse_annotation_tags(
            "/*\n@description: one two\n@comment: three\n*/"
        )
        assert tags[0].value == "one two"
        assert tags[1].value == "three"

    def test_tag_value_runs_to_end_of_block(self):
        tags = parse_annotation_tags(
            "/*\n@comment: line one\nline two still the value\n*/"
        )
        assert tags == [
            AnnotationTag(name="comment", value="line one\nline two still the value")
        ]

    def test_no_tags(self):
        assert parse_annotation_tags("/* plain comment */") == []

    def test_tags_attached_to_defines(self):
        source = (
            "library T\n"
            "context Patient\n"
            "/*\n"
            "@inclusion\n"
            "@description: Initial population\n"
            "*/\n"
            "define \"IP\": true\n"
            "define \"Other\": false\n"
        )
        tagged = parse_library_tags(source)
        assert set(tagged) == {"IP"}
        assert tagged["IP"] == [
            AnnotationTag(name="inclusion", value=None),
            AnnotationTag(name="description", value="Initial population"),
        ]

    def test_tag_name_must_be_identifier(self):
        # `@` followed by non-identifier text is not a tag.
        tags = parse_annotation_tags("/*\n@! not a tag\n@real: v\n*/")
        assert tags == [AnnotationTag(name="real", value="v")]

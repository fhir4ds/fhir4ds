"""CQL 2.0 declaration-level relaxations (chunk CQL20-B).

Covers: relaxed library/model versioning (FHIR-57620), model qualifiers
(FHIR-31019), model aliases (FHIR-48762), conversion grammar unit qualifiers
(FHIR-52783 surface), and the relaxed string overload of value set membership
(FHIR-53532). Grammar ground truth: HL7/cql master input/images/cql/cql.g4
(2.0.0): ``usingDefinition : 'using' qualifiedIdentifier ('version'
versionSpecifier)? ('called' localIdentifier)?``.

Note: FHIR-37827 "allow tags without a value" has NO surface in the 2.0
grammar (no tag production exists) — it is IG-publishing metadata, not an
engine concern; recorded in CQL20_GAP_MATRIX.md.
"""

from __future__ import annotations

import logging

import pytest

from fhir4ds.cql.errors import ParseError, TranslationError
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import translate_cql


def _lib(body: str, header: str = "using FHIR version '4.0.1'") -> str:
    return f"library B version '1.0'\n{header}\ncontext Patient\n{body}"


class TestMultipleVersionConstraints:
    def test_multiple_model_versions_rejected(self) -> None:
        cql = (
            "library MV version '1.0'\n"
            "using FHIR version '4.0.1'\n"
            "using FHIR version '5.0.0'\n"
            "context Patient\ndefine T: 1\n"
        )
        with pytest.raises(ParseError, match="[Mm]ultiple versions of the same model"):
            parse_cql(cql)

    def test_same_model_version_twice_allowed(self) -> None:
        cql = (
            "library MV version '1.0'\n"
            "using FHIR version '4.0.1'\n"
            "using FHIR version '4.0.1'\n"
            "context Patient\ndefine T: 1\n"
        )
        parse_cql(cql)  # no raise

    def test_unversioned_alongside_versioned_model_allowed(self) -> None:
        # Implementation-environment resolution per the 2.0 Developer's Guide.
        cql = (
            "library MV version '1.0'\n"
            "using FHIR version '4.0.1'\n"
            "using FHIR\n"
            "context Patient\ndefine T: 1\n"
        )
        parse_cql(cql)  # no raise

    def test_multiple_include_versions_rejected(self) -> None:
        cql = (
            "library MI version '1.0'\n"
            "include Common version '1'\n"
            "include Common version '2'\n"
            "context Patient\ndefine T: 1\n"
        )
        with pytest.raises(ParseError, match="[Mm]ultiple versions of the same library"):
            parse_cql(cql)

    def test_include_version_discrepancy_warns_not_errors(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Relaxed versioning (FHIR-57620): the loader resolves by identifier;
        # a version mismatch with the loaded library's declaration is a
        # WARNING, not a translation error.
        lib_a = "library Common version '9.9'\ncontext Unfiltered\ndefine X: 1\n"
        lib_b = (
            "library Host version '1.0'\n"
            "include Common version '1'\n"
            "context Unfiltered\ndefine T: Common.X\n"
        )
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "Common.cql").write_text(lib_a)
            (Path(td) / "Host.cql").write_text(lib_b)
            from fhir4ds.cql.parser import parse_cql as _parse
            from fhir4ds.cql.translator.translator import CQLToSQLTranslator

            def _loader(name: str):
                p = Path(td) / f"{name}.cql"
                return _parse(p.read_text()) if p.exists() else None

            translator = CQLToSQLTranslator(library_loader=_loader)
            with caplog.at_level(logging.WARNING):
                # should NOT raise; loader returns the '9.9' library for a
                # version-'1' include -> discrepancy warning
                translator.translate_library(_parse(lib_b))
        assert any(
            "version discrepancy" in r.message.lower() or "Include version" in r.message
            for r in caplog.records
        )


class TestModelQualifiersAndAliases:
    def test_qualified_model_parses_and_translates(self) -> None:
        cql = (
            "library Q version '1.0'\n"
            "using hl7.fhir.us.core.USCore version '7.0.0'\n"
            "context Patient\ndefine T: 1 + 1\n"
        )
        parse_cql(cql)
        translate_cql(cql)

    def test_model_alias_called(self) -> None:
        cql = (
            "library A version '1.0'\n"
            "using hl7.fhir.us.core.USCore version '7.0.0' called USC\n"
            "context Patient\ndefine T: 2 + 2\n"
        )
        lib = parse_cql(cql)
        using = lib.using[0]
        assert using.model == "hl7.fhir.us.core.USCore"
        assert using.alias == "USC"
        translate_cql(cql)

    def test_plain_using_unchanged(self) -> None:
        lib = parse_cql(_lib("define T: 1"))
        assert lib.using[0].model == "FHIR"
        assert lib.using[0].alias is None


class TestConversionUnitQualifiers:
    @pytest.mark.parametrize(
        "unit", ["year", "month", "week", "day", "hour", "minute", "second", "years"]
    )
    def test_precision_unit_targets_parse(self, unit: str) -> None:
        # FHIR-52783 grammar surface: `convert X to <precision-unit>` parses
        # like the quoted-unit form (lowered to ConvertQuantity semantics).
        cql = _lib(f"define C: convert 5 'd' to {unit}")
        translate_cql(cql)  # grammar acceptance; no ParseError

    def test_quoted_unit_still_works(self) -> None:
        translate_cql(_lib("define C: convert 5 'mg' to 'g'"))


class TestRelaxedStringValuesetMembership:
    def test_string_in_valueset_translates(self) -> None:
        # FHIR-53532: relaxed error checking for the string overload of the
        # value set membership operator — translating (lowered via
        # in_valueset on the string as a code) rather than erroring.
        cql = (
            "library V version '1.0'\n"
            "valueset \"VS\": 'urn:oid:1.2.3'\n"
            "context Patient\ndefine T: 'S' in \"VS\"\n"
        )
        sql = translate_cql(cql)
        assert sql is not None

    def test_string_in_codesystem_still_typed_error(self) -> None:
        # The relaxation is scoped to the VALUE SET overload; CodeSystem
        # string membership remains a typed translation error.
        cql = (
            "library V version '1.0'\n"
            "codesystem \"CS\": 'urn:oid:4.5.6'\n"
            "context Patient\ndefine T: 'S' in \"CS\"\n"
        )
        with pytest.raises(TranslationError):
            translate_cql(cql)

"""Unit tests for operations envelopes, errors, spec parsing (U1)."""

from __future__ import annotations

import json

import pytest

from fhir4ds.operations import (
    DatasetSpec,
    DiagnosticCode,
    LibraryText,
    TestCase,
    dataset_spec_from_dict,
    tests_input_from_dict,
)
from fhir4ds.operations.errors import diagnostic_from_exception
from fhir4ds.operations.library_sources import LibraryResolver, bundled_library_names


class TestDiagnosticCodes:
    def test_all_codes_are_stable_strings(self):
        expected = {
            "parse_error", "translation_error", "evaluation_error",
            "input_error", "dataset_error", "not_found",
            "unsupported_feature", "timeout",
        }
        assert {c.value for c in DiagnosticCode} == expected

    def test_diagnostics_to_dict_shape(self):
        from fhir4ds.operations.envelopes import Diagnostics, ErrorLocation

        d = Diagnostics(
            code=DiagnosticCode.PARSE_ERROR,
            message="boom",
            detail="ParseError",
            location=ErrorLocation(start_line=3, start_column=5, library="Main"),
            data={"expected": "}", "found": "define"},
        )
        out = d.to_dict()
        assert out["code"] == "parse_error"
        assert out["severity"] == "error"
        assert out["location"]["start_line"] == 3
        assert out["location"]["library"] == "Main"
        assert out["data"]["expected"] == "}"

    def test_severity_and_data_optional(self):
        from fhir4ds.operations.envelopes import Diagnostics

        out = Diagnostics(code=DiagnosticCode.INPUT_ERROR, message="x").to_dict()
        assert "location" not in out and "data" not in out and "detail" not in out


class TestErrorMapping:
    def test_parse_error_maps_with_location(self):
        from fhir4ds.cql.errors import ParseError

        exc = ParseError(message="bad", position=(4, 7), expected="}", found="define")
        d = diagnostic_from_exception(exc)
        assert d.code == DiagnosticCode.PARSE_ERROR
        assert d.location is not None and d.location.start_line == 4
        assert d.data == {"expected": "}", "found": "define"}

    def test_semantic_error_maps_to_translation(self):
        from fhir4ds.cql.errors import SemanticError

        exc = SemanticError(message="type mismatch", symbol="X",
                            expected_type="Boolean", actual_type="Integer")
        d = diagnostic_from_exception(exc)
        assert d.code == DiagnosticCode.TRANSLATION_ERROR
        assert d.data["symbol"] == "X"

    def test_unsupported_feature_maps(self):
        from fhir4ds.cql.errors import UnsupportedFeatureError

        exc = UnsupportedFeatureError(message="no ELM", feature_name="ELM",
                                      workaround="use CQL")
        d = diagnostic_from_exception(exc)
        assert d.code == DiagnosticCode.UNSUPPORTED_FEATURE
        assert d.data["feature_name"] == "ELM"

    def test_unknown_exception_falls_to_evaluation_with_type_name(self):
        d = diagnostic_from_exception(RuntimeError("weird"))
        assert d.code == DiagnosticCode.EVALUATION_ERROR
        assert "RuntimeError" in (d.detail or "")


class TestLibraryText:
    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            LibraryText(name="", text="x")
        with pytest.raises(ValueError):
            LibraryText(name="A", text="  ")

    def test_from_dict_strict(self):
        from fhir4ds.operations.envelopes import _library_text_from_dict

        lib = _library_text_from_dict({"name": "A", "text": "library A"})
        assert lib.name == "A"
        with pytest.raises(ValueError):
            _library_text_from_dict({"name": "A", "text": "x", "bogus": 1})


class TestDatasetSpec:
    def test_rejects_multiple_primary_sources(self):
        with pytest.raises(ValueError):
            DatasetSpec(resources=[{"resourceType": "Patient"}], ndjson_paths=["x.ndjson"])

    def test_inline_forms(self):
        spec = DatasetSpec(resources=[{"resourceType": "Patient", "id": "1"}])
        assert not spec.is_empty
        spec2 = DatasetSpec(valueset_resources=[{"url": "u", "codes": []}])
        assert not spec2.is_empty

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            DatasetSpec(ndjson_paths=[str(tmp_path / "nope.ndjson")])

    def test_from_dict_unknown_key(self):
        with pytest.raises(ValueError):
            dataset_spec_from_dict({"resources": [], "bogus": 1})


class TestTestsInput:
    def test_valid_cases(self):
        ti = tests_input_from_dict({
            "schema": 1,
            "cases": [
                {"patient": "p1", "population": "Numerator", "expect": True},
                {"patient": "p2", "define": "Has Diabetes", "expect": False},
            ],
        })
        assert len(ti.cases) == 2

    def test_unknown_keys_rejected(self):
        with pytest.raises(ValueError):
            tests_input_from_dict({"cases": [{"patient": "p", "expect": True,
                                              "population": "N", "extra": 1}]})

    def test_population_and_define_exclusive(self):
        with pytest.raises(ValueError):
            TestCase(patient="p", expect=True, population="N", define="D")
        with pytest.raises(ValueError):
            TestCase(patient="p", expect=True)

    def test_schema_version(self):
        with pytest.raises(ValueError):
            tests_input_from_dict({"schema": 2, "cases": [
                {"patient": "p", "population": "N", "expect": True}]})

    def test_empty_cases_rejected(self):
        with pytest.raises(ValueError):
            tests_input_from_dict({"cases": []})


class TestLibraryResolver:
    def test_bundled_names(self):
        assert set(bundled_library_names()) >= {"FHIRHelpers", "QICoreCommon", "Status"}

    def test_resolves_bundled_fhirhelpers(self):
        resolver = LibraryResolver(inline=[])
        lib = resolver.resolve("FHIRHelpers")
        assert lib is not None
        assert getattr(lib, "identifier", "") == "FHIRHelpers"

    def test_inline_beats_bundled(self):
        inline = LibraryText(
            name="FHIRHelpers",
            text="library FHIRHelpers version '9.9.999'\nusing FHIR version '4.0.1'",
        )
        resolver = LibraryResolver(inline=[inline])
        lib = resolver.resolve("FHIRHelpers")
        assert getattr(lib, "version", None) == "9.9.999"

    def test_unresolved_diagnostic_names_tiers(self):
        resolver = LibraryResolver(inline=[])
        assert resolver.resolve("NotALibrary") is None
        d = resolver.unresolved_diagnostic("NotALibrary")
        assert d.code == DiagnosticCode.NOT_FOUND
        assert "inline" in (d.detail or "") and "bundled" in (d.detail or "")


class TestEnvelopeSerialization:
    def test_verify_envelope_json_roundtrip(self):
        from fhir4ds.operations import VerifyEnvelope

        v = VerifyEnvelope(ok=True, passed=False, library="L",
                           patients_evaluated=3,
                           summary={"IPP": 2},
                           tests={"total": 3, "passed": 2, "failed": 1, "failures": []})
        out = v.to_dict()
        assert out["schema"] == 1 and out["ok"] is True and out["passed"] is False
        json.dumps(out)  # JSON-serializable

"""Evolution iter 3 / Domain 1 (FHIRPath core) / EXPLORER regression coverage.

Found by generative dual-path fuzz (seed 20260919, 600 cases):
1. QA-001: native `+` string-concat fired on model-typed temporal fields
   (birthDate) because the concat branch gated on physical String type
   before the temporal guard.
2. QA-002: native `jsonValuesEqualState` returned definitive false for
   cross-kind JSON pairs (obj/arr vs scalar), violating the repo-wide
   incompatible-types-empty doctrine (FP-03 QA-001).
"""

import json

import duckdb
import pytest

# noqa: E501
RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "gender": "male",
        "birthDate": "2000-02-29",
        "extension": [{"url": "http://x", "valueString": "ex"}],
        "arrField": [{"strList": ["a", "b"]}],
    }
)


def _cpp_connection():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath

    assert register_fhirpath(con) is True
    return con


def _python_fallback_connection(monkeypatch):
    con = duckdb.connect()
    from fhir4ds.fhirpath.duckdb.extension import register_fhirpath

    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    assert register_fhirpath(con) is False
    return con


@pytest.fixture
def cpp():
    return _cpp_connection()


@pytest.fixture
def pyfb(monkeypatch):
    return _python_fallback_connection(monkeypatch)


def _fhirpath(con, resource, expr):
    row = con.execute("SELECT fhirpath(?::JSON, ?)", [resource, expr]).fetchone()
    return row[0]


def test_string_concat_skips_temporal_typed_fields_iter3(cpp, pyfb):
    # Model-typed temporal fields (fhir_type metadata) must NOT string-concat;
    # the Python fallback raises the type error -> row-resilient empty.
    for expr in [
        "extension.valueString + birthDate",
        "birthDate + extension.valueString",
        "gender + birthDate",
        "birthDate + 'x'",
        "'x' + birthDate",
    ]:
        assert _fhirpath(cpp, RESOURCE, expr) == _fhirpath(pyfb, RESOURCE, expr) == []


def test_string_concat_plain_strings_still_concatenates_iter3(cpp, pyfb):
    for expr, expected in [
        ("extension.valueString + extension.url", ["exhttp://x"]),
        ("gender + gender", ["malemale"]),
        ("'a' + 'b'", ["ab"]),
    ]:
        assert _fhirpath(cpp, RESOURCE, expr) == _fhirpath(pyfb, RESOURCE, expr) == expected


def test_temporal_literal_string_concat_empty_iter3(cpp, pyfb):
    # Typed temporal literals must not concat with strings either (both empty).
    for expr in ["@2000 + 'x'", "'x' + @T12:00"]:
        assert _fhirpath(cpp, RESOURCE, expr) == _fhirpath(pyfb, RESOURCE, expr) == []


def test_cross_kind_json_equality_is_empty_iter3(cpp, pyfb):
    # obj-vs-scalar and arr-vs-scalar `=`/`!=` are incompatible-type pairs ->
    # empty per the FP-03 QA-001 doctrine, not definitive booleans.
    for expr in [
        "extension = extension.valueString",
        "extension != extension.valueString",
        "extension.valueString = extension",
        "arrField.strList = 'a'",  # control: multi-item vs literal is FALSE, not empty
    ]:
        cpp_res = _fhirpath(cpp, RESOURCE, expr)
        py_res = _fhirpath(pyfb, RESOURCE, expr)
        assert cpp_res == py_res
        if expr == "arrField.strList = 'a'":
            assert cpp_res == ["false"]
        else:
            assert cpp_res == []


def test_same_kind_json_equality_definitive_iter3(cpp, pyfb):
    # Controls: same-kind comparisons stay definitive.
    for expr, expected in [
        ("extension = extension", ["true"]),
        ("gender = 'male'", ["true"]),
        ("gender != 'female'", ["true"]),
        ("active = true", ["true"]),
        ("extension.url != 1", None),  # str vs num literal -> incompatible -> empty (checked below)
    ]:
        cpp_res = _fhirpath(cpp, RESOURCE, expr)
        assert cpp_res == _fhirpath(pyfb, RESOURCE, expr)
        if expected is not None:
            assert cpp_res == expected

"""QA-D6-001 (v0.0.25) — extractCodes plain-string parity with native C++.

The direct-SQL ``extractCodes`` UDF, when the path resolves to a plain string,
must yield ``(sibling system or '', string)`` on the Python fallback exactly as
the native C++ extension does (native is the shipping default and defines the
contract; dual-engine lockstep doctrine). Pinned native semantics:
  {"code": "c1"}                    -> ('', 'c1')
  {"code": "c1", "system": "urn:s"} -> ('urn:s', 'c1')
  {"code": ["a", "b"]}              -> [] (lists of plain strings stay empty)
"""
import json

import duckdb
import pytest

import fhir4ds
from fhir4ds.cql.duckdb.udf.valueset import extractCodes


def test_plain_string_code_without_system():
    assert extractCodes(json.dumps({"resourceType": "X", "code": "c1"}), "code") == [("", "c1")]


def test_plain_string_code_with_sibling_system():
    res = json.dumps({"resourceType": "X", "code": "c1", "system": "urn:s"})
    assert extractCodes(res, "code") == [("urn:s", "c1")]


def test_plain_string_list_stays_empty():
    assert extractCodes(json.dumps({"resourceType": "X", "code": ["a", "b"]}), "code") == []


def test_normal_shapes_unaffected():
    assert extractCodes(
        json.dumps({"code": {"coding": [{"system": "urn:n", "code": "cc"}]}}), "code"
    ) == [("urn:n", "cc")]
    assert extractCodes(
        json.dumps({"code": {"system": "urn:d", "code": "cd"}}), "code"
    ) == [("urn:d", "cd")]


def test_native_parity_plain_string():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    flags = fhir4ds.register(con)
    if not flags.get("cql_cpp"):
        pytest.skip("native extension not loadable in this environment")
    res = json.dumps({"resourceType": "X", "code": "c1", "system": "urn:s"})
    native = con.execute("SELECT extractCodes(?, 'code')", [res]).fetchone()[0]
    assert native == ["urn:s|c1"]
    assert [f"{s}|{c}" for s, c in extractCodes(res, "code")] == native

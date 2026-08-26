"""Deeply nested JSON result serialization parity (SOF-VD-11 EXPLORER QA-001).

orjson enforces a ~127-level nesting ceiling on dumps(); before the fix the
Python fallback raised TypeError("Recursion limit reached") inside
fhirpath_scalar, which the row-resilient wrapper silently swallowed into an
empty result — diverging from the native C++ evaluator, which serializes the
full tree. _json_serialize now falls back to the iterative serializer.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import _json_serialize, fhirpath_scalar


def _deep_resource(levels: int) -> dict:
    resource = {"resourceType": "Observation", "id": "deep", "status": "final"}
    node = resource
    for level in range(levels):
        node["extension"] = [{"url": f"u{level}", "valueString": f"s{level}"}]
        node = node["extension"][0]
    return resource


def test_json_serialize_deeply_nested_object_does_not_raise() -> None:
    obj = _deep_resource(300)
    serialized = _json_serialize(obj)
    assert '"s299"' in serialized
    # round-trips
    assert json.loads(serialized)["extension"][0]["url"] == "u0"


def test_fhirpath_scalar_deep_extension_matches_native() -> None:
    resource = json.dumps(_deep_resource(300))
    py = fhirpath_scalar(resource, "extension")
    assert py, "fallback must not return empty for deeply nested results"
    assert '"s299"' in py[0]

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        assert register_fhirpath(con) is True
        native = con.execute(
            "SELECT fhirpath_text(?::JSON, 'extension')", [resource]
        ).fetchone()[0]
    finally:
        con.close()
    assert native is not None
    assert json.loads(py[0]) == json.loads(native)

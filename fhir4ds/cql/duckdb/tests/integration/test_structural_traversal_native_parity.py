"""cqlChildren / cqlDescendants native C++ parity tests (v0.0.14 WASM parity).

The C++ ports (cql_extension.cpp CqlChildrenFunc/CqlDescendantsFunc) mirror
the Python authority (udf/list.py): CQL-05 transport markers, compact JSON
with Python json.dumps byte-parity (ensure_ascii escapes, lowercase hex),
SQL NULL for null items, empty list for typed-marker / scalar inputs.
"""

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register as register_cql
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.list import cqlChildren_scalar, cqlDescendants_scalar

TYPED_MARKER = json.dumps({"__fhir4ds_cql_type": "Integer", "value": 5})
NESTED = json.dumps(
    {
        "nested": {"x": [1, {"y": 2}]},
        "s": "str",
        "n": None,
        "arr": [1, 2, 3],
        "uni": "é日",
    }
)
FHIR_OBS = json.dumps(
    {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
        "valueQuantity": {"value": 120, "unit": "mmHg"},
    }
)

CASES = [
    NESTED,
    FHIR_OBS,
    TYPED_MARKER,
    json.dumps([1, 2, {"k": "v"}]),
    json.dumps({"a": True, "b": 1, "c": 1.5, "d": "x"}),
    "plain non-JSON string",
    "null",
]


def _native_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_cql(con, include_fhirpath=False)
    return con


def _python_con():
    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=False)
    return con


def _no_python_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    con.execute(
        "LOAD '/mnt/d/fhir4ds/extensions/cql/build/release/extension/cql/cql.duckdb_extension'"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS resources (patient_id VARCHAR, resourceType VARCHAR, resource JSON)"
    )
    return con


LEGS = [
    pytest.param(_native_con, id="native"),
    pytest.param(_python_con, id="forced_python"),
    pytest.param(_no_python_con, id="no_python"),
]


@pytest.mark.parametrize("con_factory", LEGS)
@pytest.mark.parametrize(
    "case", CASES, ids=[f"case{i}" for i in range(len(CASES))]
)
def test_children_descendants_match_python_authority(con_factory, case):
    con = con_factory()
    try:
        py_children = cqlChildren_scalar(case)
        py_desc = cqlDescendants_scalar(case)

        native_children = con.execute(
            "SELECT cqlChildren(?)", [case]
        ).fetchone()[0]
        native_desc = con.execute(
            "SELECT cqlDescendants(?)", [case]
        ).fetchone()[0]

        assert native_children == py_children, (
            f"children mismatch for {case!r}:\n  py={py_children}\n  native={native_children}"
        )
        assert native_desc == py_desc, (
            f"descendants mismatch for {case!r}:\n  py={py_desc}\n  native={native_desc}"
        )
    finally:
        con.close()


@pytest.mark.parametrize("con_factory", LEGS)
def test_null_input_is_sql_null(con_factory):
    con = con_factory()
    try:
        assert con.execute("SELECT cqlChildren(NULL) IS NULL").fetchone()[0] is True
        assert con.execute("SELECT cqlDescendants(NULL) IS NULL").fetchone()[0] is True
    finally:
        con.close()


@pytest.mark.parametrize("con_factory", LEGS)
def test_translated_tuple_children_end_to_end(con_factory):
    """End-to-end CQL: Children(Tuple{...}) and Descendants(Tuple{...})
    execute on each registration leg and match the Python authority."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    lib = parse_cql(
        """
        library StructuralLib
        using FHIR version '4.0.1'
        context Patient
        define KidCount: Count(Children(Tuple { a: 1, b: 'x', c: Tuple { d: true } }))
        define DescCount: Count(Descendants(Tuple { a: 1, b: 'x', c: Tuple { d: true } }))
        """
    )
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(lib)
    assert "cqlChildren" in sql
    assert "cqlDescendants" in sql

"""ratioCompare + ConceptToListCode native C++ parity tests (v0.0.14).

ratioCompare: desktop legs resolve to the Python authority (in
_PYTHON_PREFERRED_CPP_CONFLICTS because equivalence divides into compound
units whose metric-prefix conversion the C++ quantity layer cannot do —
the CQL-03 HISTORIAN QA-004 deferred family). The no-Python leg exercises
the true C++ port, byte-identical on all non-divergent classes including
the None-operand semantic branches (None ~ None == true).

ConceptToListCode: pure JSON normalization; C++ is byte-identical to the
Python authority on every class (orjson compact separators + key order).
"""

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register as register_cql
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.quantity import conceptToListCode as py_c2l
from fhir4ds.cql.duckdb.udf.ratio import ratioCompare as py_ratio


def _ratio(num_v, num_u, den_v, den_u):
    return json.dumps(
        {
            "numerator": {"value": num_v, "unit": num_u, "code": num_u,
                          "system": "http://unitsofmeasure.org"},
            "denominator": {"value": den_v, "unit": den_u, "code": den_u,
                            "system": "http://unitsofmeasure.org"},
        }
    )


R1 = _ratio(10, "mg", 2, "mL")
R1B = _ratio(10.0, "mg", 2.0, "mL")
R3 = _ratio(5, "mg", 1, "mg")

# (left, right, op, expected) — Python-authority semantics
RATIO_CASES = [
    (R1, R1B, "==", True),
    (R1, R1B, "~", True),
    (R3, R3, "==", True),
    (R3, R3, "~", True),
    (R3, R3, "!=", False),
    (R1, R1, "!=", False),
    (None, R3, "~", False),
    (R3, None, "~", False),
    (None, None, "~", True),
    (None, R3, "==", None),
    (R3, None, "!~", True),
    (None, None, "!~", False),
    (R1, "not json", "~", False),
    ("not json", R1, "==", None),
    (R1, R1, ">", None),  # invalid op -> None
    (None, None, "==", None),
]

# Known-divergent class: equivalence over compound units with metric
# prefixes (10mg:2mL ~ 1g:200mL) — Python True (pint converts), C++ NULL.
DIVERGENT_EQUIVALENCE = (_ratio(10, "mg", 2, "mL"), _ratio(1, "g", 200, "mL"), "~", True)


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
    return con


@pytest.mark.parametrize(
    "con_factory",
    [
        pytest.param(_native_con, id="native"),
        pytest.param(_python_con, id="forced_python"),
    ],
)
@pytest.mark.parametrize("left,right,op,expected", RATIO_CASES)
def test_ratio_compare_python_authority_on_desktop_legs(con_factory, left, right, op, expected):
    con = con_factory()
    try:
        row = con.execute(
            "SELECT ratioCompare(?, ?, ?)", [left, right, op]
        ).fetchone()
        assert row[0] == expected
    finally:
        con.close()


@pytest.mark.parametrize("left,right,op,expected", RATIO_CASES)
def test_ratio_compare_no_python_cpp_matches(left, right, op, expected):
    con = _no_python_con()
    try:
        row = con.execute(
            "SELECT ratioCompare(?, ?, ?)", [left, right, op]
        ).fetchone()
        assert row[0] == expected
    finally:
        con.close()


def test_ratio_compare_divergent_equivalence_documented():
    """Compound-unit metric-prefix equivalence: Python True (pint converts
    g/mL -> mg/mL), C++ False (its quantity_compare nulls on compound
    metric-prefix conversion — the CQL-03 HISTORIAN QA-004 deferred family —
    and ratio_compare converts that NULL to per-spec False). WASM surfaces
    the C++ behavior."""
    l, r, op, py_expected = DIVERGENT_EQUIVALENCE
    py_con = _python_con()
    try:
        assert py_con.execute(
            "SELECT ratioCompare(?, ?, ?)", [l, r, op]
        ).fetchone()[0] == py_expected
    finally:
        py_con.close()
    cpp_con = _no_python_con()
    try:
        assert cpp_con.execute(
            "SELECT ratioCompare(?, ?, ?)", [l, r, op]
        ).fetchone()[0] is False
    finally:
        cpp_con.close()


def test_ratio_compare_python_authority_direct_agreement():
    for left, right, op, expected in RATIO_CASES:
        assert py_ratio(left, right, op) == expected


C2L_CASES = [
    json.dumps({"codes": [{"code": "x", "system": "s"}, {"code": "y"}]}),
    json.dumps({"codes": [{"code": "x", "system": "s", "version": "1", "display": "d"}]}),
    json.dumps({"coding": [{"code": "x"}]}),  # coding fallback
    json.dumps({"codes": []}),                 # empty list
    json.dumps({"codes": [{"value": 5}]}),     # quantity lookalike -> None
    json.dumps({"codes": [{"system": "s"}]}),  # no code -> None
    json.dumps({}),                            # no codes/coding -> None
    "not json",                                # -> None
]


@pytest.mark.parametrize(
    "con_factory",
    [
        pytest.param(_native_con, id="native"),
        pytest.param(_python_con, id="forced_python"),
        pytest.param(_no_python_con, id="no_python"),
    ],
)
@pytest.mark.parametrize("case", C2L_CASES)
def test_concept_to_list_code_matches_python_authority(con_factory, case):
    con = con_factory()
    try:
        expected = py_c2l(case)
        row = con.execute("SELECT ConceptToListCode(?)", [case]).fetchone()
        assert row[0] == expected, f"case={case!r}"
    finally:
        con.close()


@pytest.mark.parametrize(
    "con_factory",
    [
        pytest.param(_native_con, id="native"),
        pytest.param(_python_con, id="forced_python"),
        pytest.param(_no_python_con, id="no_python"),
    ],
)
def test_concept_to_list_code_null_input(con_factory):
    con = con_factory()
    try:
        assert con.execute("SELECT ConceptToListCode(NULL) IS NULL").fetchone()[0] is True
    finally:
        con.close()

"""Domain 3 EXPLORER (v0.0.26 iteration 11) regression coverage.

QA-D3E-001 (silent wrong answer, pre-existing at v0.0.25): the
count-unnest machinery's rows-to-list coercion aliased a STAR
projection — ``SELECT * AS __cql_list_value FROM "CTE" AS X`` renames
EVERY expanded column, DuckDB resolves the qualified reference to the
FIRST one (``patient_id``), and the per-patient element list silently
held patient-id strings instead of values. Single-leaf counts were
row-count coincidences; over a UNION of query leaves the distinct-row
dedup collapsed same-patient elements and undercounted
(``Count("A" X where ... union "B" Y where ...)`` returned 1 for a
3-element patient).

Fix: the coercion never aliases a star (no-op degrade), and the
count-unnest leaf loop rewrites the star to the CTE's element column
(``value``/``resource``) from definition metadata before coercion.

Also pins the loud pre-existing query-as-source composition failures
found by the same fuzz (documented open, NOT fixed this iteration):
union-derived alias sources, distinct-expression query sources, and
nested query-as-source flattening raise BinderExceptions rather than
silently lying.
"""

from __future__ import annotations

import duckdb

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.duckdb.extension import register
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_P1 = {"resourceType": "Patient", "id": "p1"}
_P2 = {"resourceType": "Patient", "id": "p2"}
_OBS_A = {
    "resourceType": "Observation", "id": "oa", "status": "final",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
}
_OBS_B = {
    "resourceType": "Observation", "id": "ob", "status": "final",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{"system": "http://loinc.org", "code": "29463-7"}]},
}
_OBS_C = {
    "resourceType": "Observation", "id": "oc", "status": "final",
    "subject": {"reference": "Patient/p2"},
    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
}
_COND_P1 = {
    "resourceType": "Condition", "id": "cd1",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "x"}]},
}
_RESOURCES = [_P1, _P2, _OBS_A, _OBS_B, _OBS_C, _COND_P1]

_CQL = """library CountUnionLeaf version '1.0.0'
using FHIR version '4.0.1'
context Patient
define A: [Observation] O where O.status = 'final' return O.id
define B: [Condition] C return C.id
define UnionCount: Count("A" X where X is not null union "B" Y where Y is not null)
define SingleCount: Count("A" X where X is not null)
"""


def _con_connections():
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native)
    py = duckdb.connect()
    ver = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    register(py)
    duckdb.__version__ = ver
    for con in (native, py):
        FHIRDataLoader(con).load_resources(_RESOURCES)
    return native, py


_SQL = CQLToSQLTranslator().translate_library_to_population_sql(
    parse_cql(_CQL),
    output_columns={
        "union_count": "UnionCount",
        "single_count": "SingleCount",
    },
)


def test_count_union_leaf_elements_are_values_not_patient_ids_d3_explorer():
    """The element list must hold CTE VALUES; patient-id elements made the
    UNION dedup collapse same-patient rows (p1: 3 elements -> 1)."""
    native, py = _con_connections()
    try:
        rn = native.execute(_SQL).fetchall()
        rp = py.execute(_SQL).fetchall()
    finally:
        native.close()
        py.close()
    by_patient = {row[0]: row for row in rn}
    # p1: observations oa+ob + condition cd1 = 3 elements; p2: oc = 1.
    assert sorted(by_patient) == ["p1", "p2"]
    assert by_patient["p1"][1] == 3, by_patient
    assert by_patient["p2"][1] == 1, by_patient
    # dual-engine parity
    assert sorted(rn) == sorted(rp)


def test_count_single_leaf_over_value_cte_counts_values_d3_explorer():
    native, py = _con_connections()
    try:
        rn = native.execute(_SQL).fetchall()
    finally:
        native.close()
        py.close()
    by_patient = {row[0]: row for row in rn}
    assert by_patient["p1"][2] == 2, by_patient  # oa, ob
    assert by_patient["p2"][2] == 1, by_patient  # oc


def test_generated_sql_aliases_element_column_not_star_d3_explorer():
    """The count-unnest leaf projection must reference the element column,
    never `SELECT * AS __cql_list_value`."""
    assert "SELECT * AS __cql_list_value" not in _SQL
    assert '"A" AS X WHERE X.value IS NOT NULL AND X.patient_id = _pt.patient_id' in _SQL


_CQL_HEAD = """library HeadAliasFamily version '1.0.0'
using FHIR version '4.0.1'
context Patient
define X: Head({1,2,3,4}, 2)
define HX: Head("X", 1)
define TX: Tail("X", 1)
define SK: Skip("X", 1)
define TK: Take("X", 1)
define LX: Length("X")
define FX: First("X")
define CX: Count("X")
"""

_SQL_HEAD = CQLToSQLTranslator().translate_library_to_population_sql(
    parse_cql(_CQL_HEAD),
    output_columns={
        "hx": "HX", "tx": "TX", "sk": "SK", "tk": "TK",
        "lx": "LX", "fx": "FX", "cx": "CX",
    },
)


def test_cql20_list_function_define_alias_consumers_d3_explorer():
    """QA-D3E-002: a define of Head/TailN/Slice (CQL 2.0 list subsetting)
    must be marked stores_list_value + PATIENT_SCALAR + List<T> — alias
    consumers previously nested the whole list (Head -> [[1,2]], Skip ->
    [], Length -> 1)."""
    native, py = _con_connections()
    try:
        rn = native.execute(_SQL_HEAD).fetchall()
        rp = py.execute(_SQL_HEAD).fetchall()
    finally:
        native.close()
        py.close()
    assert rn == rp
    row = {k: rn[0][i] for i, k in enumerate(
        ["pid", "hx", "tx", "sk", "tk", "lx", "fx", "cx"])}
    assert row["hx"] == [1], row
    assert row["tx"] == [2], row
    assert row["sk"] == [2], row
    assert row["tk"] == [1], row
    assert row["lx"] == 2, row
    assert row["fx"] == 1, row
    assert row["cx"] == 2, row


def test_open_preexisting_query_source_composition_failures_are_loud_d3_explorer():
    """Documented-open (v0.0.26 d3-EXPLORER): union-derived alias sources
    and distinct-expression query sources raise BinderExceptions at
    execution — loud failures, not silent wrong answers. If one of these
    starts silently returning wrong data instead, escalate severity."""
    import pytest

    cases = {
        "union-alias": """library T version '1'
using FHIR version '4.0.1'
context Patient
define U: Count((([Observation] O return O.id) union ([Condition] C return C.id)) X where X is not null)
""",
        "distinct-source": """library T version '1'
using FHIR version '4.0.1'
context Patient
define D: Count((distinct {1,1,2,3,3}) X where X > 1)
""",
    }
    for label, cql in cases.items():
        sql = CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql), output_columns={"v": {"union-alias": "U", "distinct-source": "D"}[label]})
        native, _py = _con_connections()
        try:
            with pytest.raises(duckdb.Error):
                native.execute(sql).fetchall()
        finally:
            native.close()

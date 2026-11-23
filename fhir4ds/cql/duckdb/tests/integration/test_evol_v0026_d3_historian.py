"""Domain 3 HISTORIAN (v0.0.26 iteration 10) regression coverage.

Covers:
* QA-D3H-001 (carry-in a): a query used as a query source with an alias
  (``Count([Observation] O return O.value as FHIR.Quantity Q where
  Q is FHIR.Quantity)``) lowered the source to a one-row-per-element
  projection whose WHERE references the projected alias, then the
  rows-to-list coercion re-projected the column as ``__cql_list_value``
  and DROPPED the alias column — BinderException "Referenced column Q
  not found". The coercion now nests the original select as a derived
  table when its WHERE/HAVING/ORDER BY references the projected alias.
* Carry-in (b) pins: the stale wasm-gate / cql.test expectations for
  cqlDurationBetween uncertainty (spec Appendix B: duration
  ``months between @2012-01-02 and @2012`` is [0, 10], difference is
  [0, 11]; official fixture pins ``days between DateTime(2014,1,15) and
  DateTime(2014,2)`` = Interval[17, 44]) — see
  test_wasm_translate_execute_gate.py and extensions/cql/test/sql/cql.test.
"""

from __future__ import annotations

import duckdb

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.duckdb.extension import register
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_PATIENT = {"resourceType": "Patient", "id": "p1"}
_OBS_QTY = {
    "resourceType": "Observation", "id": "o1", "status": "final",
    "subject": {"reference": "Patient/p1"},
    "valueQuantity": {"value": 5.5, "unit": "mg"},
}
_OBS_STR = {
    "resourceType": "Observation", "id": "o2", "status": "final",
    "subject": {"reference": "Patient/p1"},
    "valueString": "text",
}

_CQL = """library AsCastWhere version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QtyIsQty: Count([Observation] O return O.value as FHIR.Quantity Q where Q is FHIR.Quantity)
define QtyNotNull: Count([Observation] O return O.value as FHIR.Quantity Q where Q is not null)
define StrIsString: Count([Observation] O return O.value as FHIR.string S where S is String)
define AsMismatch: Count([Observation] O return 'x' as Integer X where X is Integer)
"""


def _translate() -> dict[str, str]:
    return CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_CQL),
        output_columns={
            "qty_is_qty": "QtyIsQty",
            "qty_not_null": "QtyNotNull",
            "str_is_string": "StrIsString",
            "as_mismatch": "AsMismatch",
        },
    )


def _loaded_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    FHIRDataLoader(con).load_resources([_PATIENT, _OBS_QTY, _OBS_STR])
    return con


class TestQuerySourceAliasWhereSurvivesRowsToListCoercion:
    def test_as_cast_return_alias_where_binds_element_values(self) -> None:
        sql = _translate()
        con = _loaded_connection()
        try:
            rows = con.execute(sql).fetchall()
        finally:
            con.close()
        # qty_is_qty=1 (o1), qty_not_null=1, str_is_string=1 (o2's
        # valueString satisfies the FHIR.string cast), as_mismatch=0.
        assert rows == [("p1", 1, 1, 1, 0)]

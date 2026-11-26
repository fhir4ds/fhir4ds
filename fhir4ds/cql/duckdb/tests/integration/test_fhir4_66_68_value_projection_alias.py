"""FHIR4-66 / FHIR4-68 — references to a VALUE-projection query alias.

CQL 1.5 §Query: a query source may be any expression, and its alias binds to
each ELEMENT of the source's result.  When the source is itself a query whose
``return`` projects a computed value — ``( (... ) C return C.id ) X`` — each row
of the source IS that value, so ``X`` must denote the projected EXPRESSION.

The translator used to register such an alias as a TABLE alias named after the
alias and rely on a column being called ``X`` in the produced select.  Two
independent symptoms followed, both Binder Errors:

FHIR4-66 — filtering the value projection
-----------------------------------------
    define "Ids": ([Condition] C return C.id) X where X = 'c2'

``CTEManager._wrap_definition_cte`` relabels a list define's single column to
``value``, so the name-based reference was left dangling::

    "Ids" AS MATERIALIZED (
        SELECT C.patient_id, fhirpath_text(C.resource, 'id') AS value
        FROM "Condition" AS C WHERE X = 'c2'          -- no column "X"
    )
    Binder Error: Referenced column "X" not found in FROM clause!

FHIR4-68 — a value projection with an INNER where clause
--------------------------------------------------------
    exists (([Condition] C where C.code is not null return C.code.coding.code)
            X where true)

The inner WHERE made the translator wrap the projection in a derived table
(``SELECT * FROM (<projection>) AS X``).  The derived column was unnamed, so
the injected patient correlation addressed the derived alias and could not
resolve::

    EXISTS (SELECT * FROM (SELECT fhirpath_text(C1.resource,'code.coding.code')
            FROM "Condition" AS C1 WHERE ...) AS X
            WHERE TRUE AND X.patient_id = _pt.patient_id)
    Binder Error: Referenced table "X" not found!

The fix binds the alias to the projection EXPRESSION (``ast_expr``) instead of
a transient column name, and detects the value projection BEFORE the
inner-WHERE derived-table branch.  Both engines (Python supplements and the
no-Python C++ surface) share the translator, so both are exercised here, and
DuckDB's default ``scalar_subquery_error_on_multiple_rows`` strictness stays on
so a shape defect cannot be masked by a harness flag.
"""

from __future__ import annotations

import json
import re

import duckdb

from .wasm_runtime_helpers import no_python_connection

_HEADER = """library F66 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

#: ``p1`` carries three Conditions (alpha/beta/gamma coding) and two Encounters
#: (one finished, one cancelled); ``p2`` carries none, so every assertion covers
#: a populated AND an empty patient.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "birthDate": "1990-01-01",
     "gender": "male"},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"},
     "code": {"coding": [{"system": "s", "code": "alpha"}]}},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"},
     "code": {"coding": [{"system": "s", "code": "beta"}]}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"},
     "code": {"coding": [{"system": "s", "code": "gamma"}]}},
    {"resourceType": "Encounter", "id": "e1", "subject": {"reference": "Patient/p1"},
     "status": "finished"},
    {"resourceType": "Encounter", "id": "e2", "subject": {"reference": "Patient/p1"},
     "status": "cancelled"},
]


def _connections():
    """Python-supplement and no-Python engines (both must bind the shape)."""
    from contextlib import contextmanager

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    @contextmanager
    def _py():
        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            yield con
        finally:
            con.close()

    yield from ((_py(), "python"), (no_python_connection(), "no_python"))


def _translate(cql_text: str, con, columns: dict[str, str]) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=columns,
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for r in _RESOURCES:
        patient_ref = (r.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [r["id"], r["resourceType"], json.dumps(r), patient_ref],
        )


def _run(cql_body: str, extra_columns: list[str]):
    """Translate + execute *cql_body* on both engines; return {label: by_patient}."""
    cql = _HEADER + cql_body
    columns = {
        "Initial Population": "Initial Population",
        "Denominator": "Denominator",
        "Numerator": "Numerator",
    }
    columns.update({name: name for name in extra_columns})
    out = {}
    for ctx, label in _connections():
        with ctx as con:
            sql = _translate(cql, con, columns)
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            rows = cursor.fetchall()
            names = [d[0] for d in cursor.description]
            out[label] = {
                row[0]: dict(zip(names[1:], row[1:], strict=True)) for row in rows
            }
            out[label]["__sql__"] = sql
    return out


def _values(result, label: str):
    patients = {k: v for k, v in result.items() if not k.startswith("__")}
    assert set(patients) == {"p1", "p2"}, f"{label}: patients {sorted(patients)}"
    return patients["p1"], patients["p2"]


# ---------------------------------------------------------------------------
# FHIR4-66 — filtering a value projection
# ---------------------------------------------------------------------------


def test_value_projection_where_filters_the_projected_values():
    """``(...) X where X = 'c2'`` keeps only the matching element."""
    out = _run(
        'define "Ids": ([Condition] C return C.id) X where X = \'c2\'\n',
        ["Ids"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert sorted(p1["Ids"]) == ["c2"], (
            f"{label}: the WHERE must filter the projected VALUES, got {p1['Ids']!r}"
        )
        assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"

        # The root cause: the alias was bound to a transient column name that
        # the definition wrap renamed to `value`, leaving `WHERE X = ...`
        # dangling.  The predicate must address the projection EXPRESSION.
        assert "fhirpath_text(C.resource, 'id') = 'c2'" in result["__sql__"], (
            f"{label}: expected the value projection inlined into the WHERE, got "
            f"{[ln for ln in result['__sql__'].splitlines() if 'WHERE' in ln]}"
        )
        assert not re.search(r"\bWHERE\b[^;]*\bX\b\s*=", result["__sql__"]), (
            f"{label}: the WHERE still references the alias rather than its value"
        )


def test_value_projection_where_multi_predicate_and_return_clause():
    """Multiple predicates on the alias, and ``return X`` over the filtered set."""
    out = _run(
        'define "Ids": ([Condition] C return C.id) X '
        "where X != 'c3' return X\n",
        ["Ids"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert sorted(p1["Ids"]) == ["c1", "c2"], f"{label}: got {p1['Ids']!r}"
        assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"


def test_value_projection_over_a_define_source_where_binds():
    """The same shape over a define-backed source (not a retrieve placeholder)."""
    out = _run(
        'define "Conds": [Condition]\n'
        'define "Ids": ("Conds" C return C.id) X where X = \'c2\'\n',
        ["Ids"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert sorted(p1["Ids"]) == ["c2"], f"{label}: got {p1['Ids']!r}"
        assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"
        # `X` must address the projected VALUE; before the fix it addressed the
        # row's resource (`X.resource = 'c2'` -> Conversion Error casting JSON).
        assert "X.resource = 'c2'" not in result["__sql__"], (
            f"{label}: the alias still resolves to a resource ROW"
        )


def test_value_projection_property_access_on_the_projected_value():
    """``X.coding`` navigates the projected value, not a resource row."""
    out = _run(
        'define "Ids": ([Condition] C return C.code) X '
        "where X.coding[0].code = 'beta' return X.coding[0].code\n",
        ["Ids"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert sorted(p1["Ids"]) == ["beta"], f"{label}: got {p1['Ids']!r}"
        assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"


# ---------------------------------------------------------------------------
# FHIR4-68 — exists/aggregates over a value projection
# ---------------------------------------------------------------------------


def test_exists_over_value_projection_binds_and_answers():
    """``exists((...) X where ...)`` binds: the correlation reaches the source."""
    out = _run(
        'define "Has": exists (([Condition] C return C.id) X where true)\n'
        'define "HasBeta": exists (([Condition] C return C.id) X where X = \'c2\')\n'
        'define "HasDelta": exists (([Condition] C return C.id) X where X = \'delta\')\n',
        ["Has", "HasBeta", "HasDelta"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert p1["Has"] is True, f"{label}: p1 has three Conditions"
        assert p2["Has"] is False, f"{label}: p2 has none"
        assert p1["HasBeta"] is True, f"{label}: p1 has c2"
        assert p2["HasBeta"] is False, f"{label}: p2 has none"
        assert p1["HasDelta"] is False, f"{label}: no Condition matches 'delta'"
        assert p2["HasDelta"] is False, f"{label}: p2 has none"
        # FHIR4-68's specific defect: the value projection must not be wrapped in
        # a derived table whose alias the patient correlation then addresses.
        sql = result["__sql__"]
        assert not re.search(
            r"FROM\s*\(\s*SELECT\s+fhirpath_text\([^)]*\)\s+FROM[^)]*\)\s*AS\s+X",
            sql,
            re.IGNORECASE | re.DOTALL,
        ), f"{label}: value projection wrapped in a derived table aliased X"
        assert "X.patient_id" not in sql, (
            f"{label}: patient correlation addresses the query alias, not the "
            f"source's own FROM alias"
        )


def test_exists_over_value_projection_with_inner_where_binds():
    """The exact FHIR4-68 repro: an INNER where clause on the projected query.

    Before the fix the inner WHERE made the translator emit
    ``SELECT * FROM (<projection>) AS X`` whose column was unnamed, so the
    injected ``X.patient_id`` correlation raised
    ``Binder Error: Referenced table "X" not found``.
    """
    out = _run(
        'define "HasCode": exists (([Condition] C where C.code is not null '
        "return C.code.coding.code) X where true)\n"
        'define "HasBeta": exists (([Condition] C where C.code is not null '
        "return C.code.coding.code) X where X = 'beta')\n"
        'define "HasDelta": exists (([Condition] C where C.code is not null '
        "return C.code.coding.code) X where X = 'delta')\n",
        ["HasCode", "HasBeta", "HasDelta"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert p1["HasCode"] is True, f"{label}: p1 projects three codes"
        assert p2["HasCode"] is False, f"{label}: p2 projects none"
        assert p1["HasBeta"] is True, f"{label}: 'beta' is projected for p1"
        assert p1["HasDelta"] is False, f"{label}: 'delta' is projected nowhere"
        assert p2["HasBeta"] is False, f"{label}: p2 projects none"


def test_count_over_value_projection_binds_and_counts():
    """The aggregate form counts the projected elements, per patient."""
    out = _run(
        'define "N": Count((([Condition] C return C.id) X where true))\n'
        'define "NBeta": Count((([Condition] C return C.id) X where X = \'c2\'))\n'
        'define "NDelta": Count((([Condition] C return C.id) X where X = \'delta\'))\n',
        ["N", "NBeta", "NDelta"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert p1["N"] == 3, f"{label}: expected 3 projected ids, got {p1['N']!r}"
        assert p2["N"] == 0, f"{label}: p2 has no Conditions, got {p2['N']!r}"
        assert p1["NBeta"] == 1, f"{label}: got {p1['NBeta']!r}"
        assert p1["NDelta"] == 0, f"{label}: got {p1['NDelta']!r}"
        assert p2["NBeta"] == 0, f"{label}: got {p2['NBeta']!r}"


def test_singleton_from_over_value_projection_binds():
    """``singleton from`` filters through the alias like any other consumer."""
    out = _run(
        'define "S": singleton from (([Condition] C return C.id) X where X = \'c2\')\n',
        ["S"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert p1["S"] == "c2", f"{label}: got {p1['S']!r}"
        assert p2["S"] is None, f"{label}: p2 has no matching rows, got {p2['S']!r}"


def test_row_shaped_nested_query_source_keeps_row_semantics():
    """A ROW-shaped nested source keeps the derived-table/row route.

    The value-projection detection must not capture row sources: their inner
    WHERE still requires the derived table, and their alias addresses the ROW
    (``X.<property>`` -> ``X.resource`` navigation), not a projected value.
    """
    out = _run(
        "define \"Finished\": exists (([Encounter] E where E.status = 'finished') "
        "X where X.status = 'finished')\n"
        "define \"Cancelled\": exists (([Encounter] E where E.status = 'finished') "
        "X where X.status = 'cancelled')\n"
        "define \"AnyFinished\": exists (([Encounter] E where E.status = 'finished') "
        "X where true)\n",
        ["Finished", "Cancelled", "AnyFinished"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert p1["Finished"] is True, f"{label}: p1 has a finished Encounter"
        assert p1["Cancelled"] is False, (
            f"{label}: the inner WHERE removed the cancelled Encounter, so the "
            f"alias must never carry it"
        )
        assert p1["AnyFinished"] is True, f"{label}: p1 has a finished Encounter"
        assert p2["Finished"] is False, f"{label}: p2 has no Encounters"
        assert p2["AnyFinished"] is False, f"{label}: p2 has no Encounters"
        # Row semantics preserved: the alias still navigates a resource row.
        assert "fhirpath_text(X.resource, 'status')" in result["__sql__"], (
            f"{label}: a row-shaped source must keep `X.<property>` -> "
            f"`X.resource` navigation"
        )


def test_value_projection_from_an_inlined_function_still_binds():
    """The same family through a function body (an inlined query source).

    ``define function Ids(cs List<Condition>): cs C return C.id`` used as a
    query source binds ``CD`` to the projected value.  The unfixed tree raised
    ``Binder Error: Referenced table "CD" not found!`` on the filtered variants;
    the binding is now the expression, so it no longer depends on the
    SELECT-list column name surviving downstream rewrites.
    """
    out = _run(
        'define function "Ids"(cs List<Condition>): cs C return C.id\n'
        'define "Has": exists (("Ids"([Condition])) CD where CD is not null)\n'
        'define "N": Count(("Ids"([Condition])) CD where CD is not null)\n'
        'define "HasZ": exists (("Ids"([Condition])) CD where CD = \'zzz\')\n',
        ["Has", "N", "HasZ"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert p1["Has"] is True, f"{label}: p1 has three projected ids"
        assert p1["N"] == 3, f"{label}: expected 3, got {p1['N']!r}"
        assert p1["HasZ"] is False, f"{label}: no id matches 'zzz'"
        assert p2["Has"] is False, f"{label}: p2 has no Conditions"
        assert p2["N"] == 0, f"{label}: p2 has no Conditions, got {p2['N']!r}"


def test_definition_root_value_projection_still_projects_the_list():
    """FHIR4-62's shape must keep working (the fix must not regress it)."""
    out = _run(
        'define "Ids": ([Condition] C return C.id) X\n'
        'define "HowMany": Count(([Condition] C return C.id) X)\n',
        ["Ids", "HowMany"],
    )
    for label, result in out.items():
        p1, p2 = _values(result, label)
        assert sorted(p1["Ids"]) == ["c1", "c2", "c3"], f"{label}: got {p1['Ids']!r}"
        assert p1["HowMany"] == 3, f"{label}: got {p1['HowMany']!r}"
        assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"
        assert p2["HowMany"] == 0, f"{label}: got {p2['HowMany']!r}"
        # FHIR4-62: never re-alias an already-aliased column (`x AS X AS value`).
        assert not re.search(r"\bAS\s+[A-Za-z_]\w*\s+AS\s+value\b", result["__sql__"]), (
            f"{label}: doubled column alias in the definition body"
        )

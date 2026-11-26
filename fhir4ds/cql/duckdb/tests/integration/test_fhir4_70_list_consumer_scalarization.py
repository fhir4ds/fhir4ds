"""FHIR4-70 — remaining list CONSUMERS must not scalarize a multi-row define.

FHIR4-65 fixed `in`/`contains`/`~in`/`~contains` for a define whose body is a
query with a ``return`` clause:

    define "Ids":  ([Condition] C return C.id) X
    define "Nums": ([Condition] C return 1) X

Such a define materializes as ``RowShape.PATIENT_MULTI_VALUE`` — ONE ROW PER
ELEMENT. Every other consumer still reached the generic SCALAR identifier
lookup, ``(SELECT sub.value FROM "Ids" ... LIMIT 1)``, and produced:

    First("Ids")            LIST_EXTRACT(<VARCHAR>, 1)  -> 'c'    (character slice!)
    Last("Ids")             LIST_EXTRACT(<VARCHAR>, -1) -> '2'    (character slice!)
    IndexOf("Ids", x)       CQLIndexOf over a ONE-ELEMENT list -> 0 for the kept
                            row, -1 for every other member
    "Nums" + 1              TRY_CAST(<VARCHAR> AS DOUBLE) + 1 -> 2.0 for a
                            two-element list of 1s

The first three are SILENT WRONG ANSWERS: they read as correct whenever the
element being asked about (or the arithmetic) happens to line up with the
single row ``LIMIT 1`` kept, and both engines answer wrong identically because
they consume the same one row. ``=``/``!=``/``~``/``includes``/``properly
includes``/``included in``/``Flatten({"Ids"})`` were LOUD (DuckDB
``array_length(VARCHAR)`` / ``flatten(VARCHAR[])`` binder errors).

WHOLE LIST, NOT ROW ORDER
-------------------------
CQL does not guarantee row order for a query, so no test below asserts WHICH
element ``First``/``Last``/``IndexOf`` returns. Each asserts a property that
only holds when the consumer sees the whole list:

  * ``First(Ids)``/``Last(Ids)`` is a MEMBER of ``Ids`` and is a full element
    (2 characters), never a 1-character slice of one;
  * every member has an ``IndexOf`` >= 0 while an absent value is -1;
  * ``Flatten({"Ids"})`` counts every element.

Those are exactly the cells a ``LIMIT 1`` consumption cannot satisfy for more
than one lucky element, so they fail before the fix and pass after it on BOTH
engines (python-supplement and no-Python C++).

ARITHMETIC
----------
``"Nums" + 1`` is a TYPED TRANSLATION ERROR, not an elementwise list. CQL 1.5
Appendix B defines NO list arithmetic: ``Add`` (§9.1), ``Subtract`` (§9.2),
``Multiply`` (§9.3), ``Divide`` (§9.4), ``Truncated Divide`` (§9.5),
``Modulo`` (§9.6) and ``Power`` (§9.9) all take scalar operands
(Integer/Long/Decimal/Quantity, plus a temporal left operand with a time-valued
Quantity right for Add/Subtract). There is no ``List<T>`` signature and no
elementwise promotion rule, so the reference engine raises
``InvalidOperatorArgument``; silently computing over one row was the bug.
"""

from __future__ import annotations

import json
import re

import duckdb
import pytest

from fhir4ds.cql.errors import TranslationError

from .wasm_runtime_helpers import no_python_connection

#: The defect's signature: a scalar ``LIMIT 1`` consumption of the define CTE.
_LIMIT_ONE_CONSUMPTION = re.compile(
    r'FROM\s+"Ids"\s+AS\s+sub\b[^)]*\bLIMIT\s+1\b', re.IGNORECASE
)

#: Positive control: the consumer aggregated the define's rows into a list.
_FULL_LIST_CONSUMPTION = re.compile(
    r'list\(_lst_src\.value\)\s+FROM\s+"Ids"\s+AS\s+_lst_src', re.IGNORECASE
)

_PREAMBLE = """library F70 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Ids": ([Condition] C return C.id) X
define "Nums": ([Condition] C return 1) X
"""

_EPILOGUE = """
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

#: consumer name -> (CQL expression, columns to project).
_CONSUMERS = {
    "FirstId": 'First("Ids")',
    "LastId": 'Last("Ids")',
    "FirstInIds": 'First("Ids") in "Ids"',
    "LastInIds": 'Last("Ids") in "Ids"',
    "MethodFirstInIds": '"Ids".first() in "Ids"',
    "MethodLastInIds": '"Ids".last() in "Ids"',
    "IdxC1": 'IndexOf("Ids", \'c1\')',
    "IdxC2": 'IndexOf("Ids", \'c2\')',
    "IdxC3": 'IndexOf("Ids", \'c3\')',
    "IdxZZ": 'IndexOf("Ids", \'zz\')',
    # Equality/equivalence are ORDER-SENSITIVE over lists (CQL 1.5 §Equivalent:
    # list equivalence is ordered), and a query's row order is not a CQL
    # guarantee — so these cells assert only that the operator executes over the
    # real list instead of raising. The order-INDEPENDENT proof that the whole
    # list is consumed is the `includes` family below.
    "IdsEq": '"Ids" = {\'c1\', \'c2\', \'c3\'}',
    "IdsNe": '"Ids" != {\'c1\', \'c2\', \'c3\'}',
    "IdsEquiv": '"Ids" ~ {\'c1\', \'c2\', \'c3\'}',
    "IdsIncludesTwo": '"Ids" includes {\'c3\', \'c1\'}',
    "IdsIncludesAll": '"Ids" includes {\'c3\', \'c1\', \'c2\'}',
    "IdsIncludesZZ": '"Ids" includes {\'zz\'}',
    "IdsPropIncludesTwo": '"Ids" properly includes {\'c3\', \'c1\'}',
    "LitIncludedIn": '{\'c3\', \'c1\'} included in "Ids"',
    "FlattenCount": 'Count(Flatten({"Ids"}))',
    "FlattenIds": 'Flatten({"Ids"})',
    # already-correct consumers (regression guards, FHIR4-65 audit)
    "IdsCount": 'Count("Ids")',
    "IdsSum": 'Sum("Nums")',
    "IdsLength": 'Length("Ids")',
    "IdsExists": 'Exists("Ids")',
    "IdsDistinct": 'Count(Distinct("Ids"))',
}

#: ``c2`` is inserted BEFORE ``c1``/``c3`` so a ``LIMIT 1`` consumption keeps
#: ``c2``: every "non-first element" assertion below then fails unless the
#: whole list is materialized.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "birthDate": "1990-01-01",
     "gender": "male"},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"},
     "verificationStatus": {"coding": [
         {"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
          "code": "active"}]}},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"},
     "verificationStatus": {"coding": [
         {"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
          "code": "confirmed"}]}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"},
     "verificationStatus": {"coding": [
         {"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
          "code": "unconfirmed"}]}},
]


def _connections():
    """Python-supplement and no-Python engines (both must answer the same)."""
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


def _library_text(consumer: str) -> str:
    return _PREAMBLE + f'define "{consumer}": {_CONSUMERS[consumer]}\n' + _EPILOGUE


def _translate(cql_text: str, con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns={"Numerator": "Numerator"},
    )


def _translate_consumer(cql_text: str, column: str, con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns={column: column},
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


def _run_both_engines():
    """Yield ``(label, by_patient)`` for the FULL consumer library.

    All consumers are translated in ONE library (they are all legal now) and
    projected together; a per-consumer failure would otherwise hide the rest.
    """
    combined = _PREAMBLE + "".join(
        f'define "{name}": {expr}\n' for name, expr in _CONSUMERS.items()
    ) + _EPILOGUE
    for ctx, label in _connections():
        with ctx as con:
            from fhir4ds.cql.parser import parse_cql
            from fhir4ds.cql.translator.translator import CQLToSQLTranslator

            library = parse_cql(combined)
            translator = CQLToSQLTranslator(connection=con)
            translator.translate_library(library)
            sql = translator.translate_library_to_population_sql(
                library=library,
                output_columns={name: name for name in _CONSUMERS},
            )
            # Keep DuckDB's default strictness: a shape defect must not be
            # masked by a harness flag (FHIR4-48/53 doctrine).
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            by_patient = {
                row[0]: dict(zip(names[1:], row[1:])) for row in cursor.fetchall()
            }
            yield label, sql, by_patient


def test_first_last_over_multi_row_define_are_list_elements():
    """``First``/``Last`` must select an ELEMENT, never slice a character."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        for column in ("FirstId", "LastId"):
            value = p1[column]
            assert value in ("c1", "c2", "c3"), (
                f"{label}: {column}={value!r} is not a member of Ids — a "
                f"one-character value is LIST_EXTRACT character-slicing the "
                f"scalar `LIMIT 1` lookup"
            )
            assert len(value) == 2, (
                f"{label}: {column}={value!r} looks like a slice of an element, "
                f"not a whole element"
            )
        # The card's own signature: First(Ids) in Ids was FALSE before the fix.
        # Order-independent (row order is not a CQL guarantee), and it is the
        # cell a one-row consumption cannot satisfy.
        assert p1["FirstInIds"] is True, (
            f"{label}: First(Ids) in Ids must be TRUE — First returned an "
            f"element of the list, so it must be a member of it"
        )
        assert p1["LastInIds"] is True, f"{label}: Last(Ids) in Ids must be TRUE"
        # The method spellings (`.first()` / `.last()`) share the defect.
        assert p1["MethodFirstInIds"] is True, (
            f"{label}: Ids.first() in Ids must be TRUE"
        )
        assert p1["MethodLastInIds"] is True, (
            f"{label}: Ids.last() in Ids must be TRUE"
        )
        # p2 has no Conditions: an empty list yields null, not a stray value.
        p2 = by_patient["p2"]
        assert p2["FirstId"] is None, f"{label}: p2 First(Ids) must be null"
        assert p2["LastId"] is None, f"{label}: p2 Last(Ids) must be null"
        assert p2["FirstInIds"] is False, f"{label}: p2's empty list has no member"


def test_indexof_over_multi_row_define_searches_every_element():
    """Every member has an index; only an absent value is -1."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        # A single-row consumption can answer >= 0 for at most ONE member
        # (the row LIMIT 1 kept) and returns -1 for the other two.
        for column, member in (("IdxC1", "c1"), ("IdxC2", "c2"), ("IdxC3", "c3")):
            index = p1[column]
            assert index is not None and index >= 0, (
                f"{label}: IndexOf(Ids, {member!r}) = {index!r}; {member!r} IS an "
                f"element of {sorted(['c1', 'c2', 'c3'])!r} — a -1 here means "
                f"IndexOf only searched one row"
            )
            assert index < 3, f"{label}: IndexOf(Ids, {member!r}) = {index!r} out of range"
        assert p1["IdxZZ"] == -1, f"{label}: 'zz' is not an element of Ids"
        # Indexes must be distinct — three different members cannot share one.
        assert len({p1["IdxC1"], p1["IdxC2"], p1["IdxC3"]}) == 3, (
            f"{label}: member indexes {p1['IdxC1'], p1['IdxC2'], p1['IdxC3']} "
            f"collide — IndexOf is not searching the real list"
        )
        p2 = by_patient["p2"]
        assert p2["IdxC1"] == -1, f"{label}: p2 has no Conditions"


def test_arithmetic_over_multi_row_define_is_a_typed_error():
    """CQL 1.5 Appendix B has NO list arithmetic — a list operand must raise."""
    text = _PREAMBLE + 'define "NumsPlus1": "Nums" + 1\n' + _EPILOGUE
    for ctx, label in _connections():
        with ctx as con:
            with pytest.raises(TranslationError) as excinfo:
                _translate(text, con)
            message = str(excinfo.value)
            assert "'+'" in message, f"{label}: unexpected message {message!r}"
            assert "list" in message.lower(), (
                f"{label}: the error must name the list-operand problem, got {message!r}"
            )


def test_equality_and_inclusion_over_multi_row_define():
    """``=``/``!=``/``~`` and the inclusion family see the whole list."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        # ORDER-INDEPENDENT proof: `includes`/`included in` ask whether every
        # element of the other list is in this one, so a two- or three-element
        # other-list can only answer TRUE when the consumer holds the WHOLE
        # Ids list. A one-row consumption answers FALSE here.
        assert p1["IdsIncludesTwo"] is True, (
            f"{label}: Ids includes {{'c3','c1'}} must be TRUE — both are "
            f"elements of Ids (a one-row list cannot contain both)"
        )
        assert p1["IdsIncludesAll"] is True, (
            f"{label}: Ids includes all three ids must be TRUE"
        )
        assert p1["IdsIncludesZZ"] is False, f"{label}: 'zz' is not in Ids"
        assert p1["IdsPropIncludesTwo"] is True, (
            f"{label}: Ids properly includes {{'c3','c1'}}"
        )
        assert p1["LitIncludedIn"] is True, (
            f"{label}: {{'c3','c1'}} included in Ids must be TRUE"
        )
        # `=`/`!=`/`~` are ORDER-SENSITIVE over lists (CQL 1.5 §Equivalent:
        # list equivalence is ordered) while a query's row order is not a CQL
        # guarantee — so assert only that they EXECUTE over a list (each cell
        # was a DuckDB `array_length(VARCHAR)` binder error before the fix).
        for column in ("IdsEq", "IdsNe", "IdsEquiv"):
            assert isinstance(p1[column], bool), (
                f"{label}: {column}={p1[column]!r} — the comparison must execute "
                f"over the materialized list and yield a Boolean"
            )
        p2 = by_patient["p2"]
        assert p2["IdsIncludesTwo"] is False, f"{label}: p2's empty list includes nothing"
        assert p2["IdsIncludesAll"] is False, f"{label}: p2's empty list includes nothing"


def test_flatten_of_list_selector_containing_multi_row_define():
    """``Flatten({"Ids"})`` must count every element of the define's list."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["FlattenCount"] == 3, (
            f"{label}: Count(Flatten({{'Ids'}})) = {p1['FlattenCount']!r}; the "
            f"selector element must be the define's LIST (3 elements)"
        )
        assert sorted(p1["FlattenIds"]) == ["c1", "c2", "c3"], (
            f"{label}: Flatten({{'Ids'}}) = {p1['FlattenIds']!r}"
        )
        p2 = by_patient["p2"]
        assert not p2["FlattenIds"], f"{label}: p2 has no Conditions"


def test_already_correct_consumers_still_see_the_whole_list():
    """Regression guard: the consumers FHIR4-65 audited as correct stay correct."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["IdsCount"] == 3, f"{label}: Count(Ids)"
        assert p1["IdsSum"] == 3, f"{label}: Sum(Nums) is 3 ones"
        assert p1["IdsLength"] == 3, f"{label}: Length(Ids)"
        assert p1["IdsExists"] is True, f"{label}: Exists(Ids)"
        assert p1["IdsDistinct"] == 3, f"{label}: Count(Distinct(Ids))"
        p2 = by_patient["p2"]
        assert p2["IdsCount"] == 0, f"{label}: p2 Count(Ids)"
        assert p2["IdsExists"] is False, f"{label}: p2 Exists(Ids)"


def test_no_limit_one_scalar_consumption_of_the_multi_row_define():
    """No consumer may consume the define's row CTE as a scalar."""
    for ctx, label in _connections():
        with ctx as con:
            for consumer in ("FirstId", "LastId", "FirstInIds", "LastInIds",
                             "IdxC1", "FlattenCount", "IdsEq", "IdsIncludesTwo"):
                text = _library_text(consumer)
                _translate(text, con)  # must translate at all
                sql = _translate_consumer(text, consumer, con)
                hit = _LIMIT_ONE_CONSUMPTION.search(sql)
                assert hit is None, (
                    f"{label}/{consumer}: consumed the row CTE as a scalar "
                    f"({hit.group(0)[:120]!r}) — a list consumer must "
                    f"materialize the whole per-patient list"
                )
                assert _FULL_LIST_CONSUMPTION.search(sql), (
                    f"{label}/{consumer}: expected the define's rows to be "
                    f"aggregated into a per-patient list"
                )

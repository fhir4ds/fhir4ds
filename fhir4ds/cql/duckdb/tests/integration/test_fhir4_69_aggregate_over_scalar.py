"""FHIR4-69 — an aggregate over a STATICALLY SCALAR operand is the SINGLETON case.

CQL 1.5 §5.5.1 defines the implicit ``T -> List<T>`` promotion: an expression of
a non-list type ``T`` consumed where ``List<T>`` is expected is read as the
one-element list ``{ x }``. Every aggregate signature is ``List<T>``
(Appendix B §Count/§Sum/§Avg/§Min/§Max), so when the operand is **statically
non-list** the promotion is provable and the whole family collapses:

    Count(x)            -> 0 when x is null, 1 otherwise
    Sum/Min/Max/Avg(x)  -> the value itself (null when it is null)

The translator's aggregate dispatch (``AggregateFunctionsMixin
._translate_aggregate_pre``) recognised list-valued ``ast_expr`` symbols,
stored-list defines, element-rows defines and (FHIR4-63) query aliases, but not
a statically SCALAR operand, so the aggregate fell through to
``_translate_count`` / the generic function path and emitted a SQL ROW aggregate
over the patient rows:

    define "X": Count(7)
    -- SELECT _pt.patient_id, COUNT(7) AS value FROM _patients AS _pt
    -- Binder Error: column "patient_id" must appear in the GROUP BY clause

    define "N": 5
    define "S": Sum("N")
    -- SELECT _pt.patient_id, SUM((SELECT sub.value FROM "N" AS sub ...)) ...
    -- Binder Error: same

    define "Nul": (null as Integer)
    define "C": Count("Nul")
    -- SELECT _pt.patient_id, (SELECT COUNT(*) FROM "Nul" AS sub ...) ...
    -- BINDS and answers 1. CQL says 0. This is the silent-wrong-value half of
    -- the defect, and the reason the gate is positive rather than exclusionary.

Every case below projects a NON-boolean column: a Boolean population column
collapses the value to TRUE/FALSE (CQL-04 presence encoding) and would hide the
number being asserted. Both the Python-supplement engine and the no-Python
engine are exercised because the defect is in the TRANSLATOR.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.errors import TranslationError

from .wasm_runtime_helpers import no_python_connection

#: Scalar literals and scalar-typed defines: every cell here is the singleton
#: case of the implicit promotion.
_SCALAR_LIBRARY = """library F69Scalar version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "N": 5
define "D": 0.5
define "S": 'abc'
define "B": true
define "Nul": (null as Integer)
define "NulS": (null as String)

define "CountLiteral": Count(7)
define "CountNull": Count(null)
define "CountStringLiteral": Count('a')
define "CountBooleanLiteral": Count(true)
define "SumLiteral": Sum(7)
define "MinLiteral": Min(7)
define "MaxLiteral": Max(7)
define "AvgLiteral": Avg(7)

define "CountN": Count("N")
define "SumN": Sum("N")
define "MinN": Min("N")
define "MaxN": Max("N")
define "AvgN": Avg("N")

define "CountD": Count("D")
define "SumD": Sum("D")
define "AvgD": Avg("D")

define "CountS": Count("S")
define "CountB": Count("B")
define "MinS": Min("S")

define "CountNullDefine": Count("Nul")
define "CountNullStringDefine": Count("NulS")
define "SumNullDefine": Sum("Nul")
define "MinNullDefine": Min("Nul")
define "MaxNullDefine": Max("Nul")
define "AvgNullDefine": Avg("Nul")

define "Initial Population": exists (Patient)
"""

_SCALAR_COLUMNS = {
    "Initial Population": "Initial Population",
    "CountLiteral": "CountLiteral",
    "CountNull": "CountNull",
    "CountStringLiteral": "CountStringLiteral",
    "CountBooleanLiteral": "CountBooleanLiteral",
    "SumLiteral": "SumLiteral",
    "MinLiteral": "MinLiteral",
    "MaxLiteral": "MaxLiteral",
    "AvgLiteral": "AvgLiteral",
    "CountN": "CountN",
    "SumN": "SumN",
    "MinN": "MinN",
    "MaxN": "MaxN",
    "AvgN": "AvgN",
    "CountD": "CountD",
    "SumD": "SumD",
    "AvgD": "AvgD",
    "CountS": "CountS",
    "CountB": "CountB",
    "MinS": "MinS",
    "CountNullDefine": "CountNullDefine",
    "CountNullStringDefine": "CountNullStringDefine",
    "SumNullDefine": "SumNullDefine",
    "MinNullDefine": "MinNullDefine",
    "MaxNullDefine": "MaxNullDefine",
    "AvgNullDefine": "AvgNullDefine",
}

#: The GUARD RAILS: every one of these was already correct and must not move —
#: list literals, stored-list defines, and a query source.
_LIST_LIBRARY = """library F69Listg version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "L": {4, 9}

define "CountListLiteral": Count({1, 2, 3})
define "SumListLiteral": Sum({4, 9})
define "MaxListLiteral": Max({4, 9})
define "CountStoredList": Count("L")
define "SumStoredList": Sum("L")
define "MinStoredList": Min("L")
define "MaxStoredList": Max("L")
define "AvgStoredList": Avg("L")
define "CountQuery": Count((from {1, 2} N return N))
define "CountDistinct": Count(distinct {1, 1, 2})

define "Initial Population": exists (Patient)
"""

_LIST_COLUMNS = {
    "Initial Population": "Initial Population",
    "CountListLiteral": "CountListLiteral",
    "SumListLiteral": "SumListLiteral",
    "MaxListLiteral": "MaxListLiteral",
    "CountStoredList": "CountStoredList",
    "SumStoredList": "SumStoredList",
    "MinStoredList": "MinStoredList",
    "MaxStoredList": "MaxStoredList",
    "AvgStoredList": "AvgStoredList",
    "CountQuery": "CountQuery",
    "CountDistinct": "CountDistinct",
}

#: A list PARAMETER stays a list: the promotion must never shrink a List<T>.
_PARAMETER_LIBRARY = """library F69Param version '1.0.0'
using FHIR version '4.0.1'
context Patient

define function ListCount(xs List<Integer>): Count(xs)
define function ListSum(xs List<Decimal>): Sum(xs)

define "ViaListParameter": ListCount({1, 2, 3})
define "SumViaListParameter": ListSum({4, 9})

define "Initial Population": exists (Patient)
"""

_PARAMETER_COLUMNS = {
    "Initial Population": "Initial Population",
    "ViaListParameter": "ViaListParameter",
    "SumViaListParameter": "SumViaListParameter",
}

#: Multi-valued dynamic defines: ``Patient.name.given`` is 0..*, so ``Count``
#: must count ELEMENTS (2 here), not answer the singleton 1. The gate must not
#: claim these — they are ``List<Any>`` + ``stores_list_value``.
_MULTI_VALUE_LIBRARY = """library F69Multi version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Given": Patient.name.given
define "Gender": Patient.gender

define "CountGiven": Count("Given")
define "CountGender": Count("Gender")
define "CountGivenPlusOne": Count("Given") + 1

define "Initial Population": exists (Patient)
"""

_MULTI_VALUE_COLUMNS = {
    "Initial Population": "Initial Population",
    "CountGiven": "CountGiven",
    "CountGender": "CountGender",
    "CountGivenPlusOne": "CountGivenPlusOne",
}

_RESOURCES = [
    {
        "resourceType": "Patient",
        "id": "p1",
        "birthDate": "1980-01-01",
        "gender": "female",
        "name": [{"given": ["Ana", "Bea"], "family": "Doe"}],
    },
]

#: A raw SQL ROW aggregate anywhere in a library whose only aggregate operands
#: are statically ONE value. MIN/MAX are excluded: the list path legitimately
#: emits ``list_min``/``list_max``, and the scalar path legitimately emitted
#: ``LEAST``/``GREATEST`` before this fix.
_ROW_AGGREGATE = ("COUNT(", "SUM(", "AVG(")


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


def _translate(cql_text: str, columns: dict[str, str], con) -> str:
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
    for resource in _RESOURCES:
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [
                resource["id"],
                resource["resourceType"],
                json.dumps(resource),
                resource["id"],
            ],
        )


def _row(con, sql: str) -> dict:
    """Execute the population SQL and return the single patient's row.

    ``scalar_subquery_error_on_multiple_rows`` is on: a PATIENT_SCALAR define is
    one row per patient by contract, and this makes a violation loud instead of
    silently taking the first row.
    """
    con.execute("SET scalar_subquery_error_on_multiple_rows=true")
    _load(con)
    cursor = con.execute(sql)
    row = cursor.fetchone()
    assert row is not None, "no patient row"
    return dict(zip([description[0] for description in cursor.description], row))


def _value(row: dict, column: str):
    """Read a projected value cell, refusing a list-wrapped projection.

    Every column this module asserts is a bare scalar: a statically scalar
    operand must reach the output as ONE value (that is the whole point of the
    singleton lowering). A list here would mean the value silently rode a list
    projection, so fail loudly rather than normalizing it away.
    """
    value = row[column]
    assert not isinstance(value, list), (
        f"{column}: expected a bare scalar, got a list {value!r}"
    )
    return value


#: Every statically scalar cell, with the CQL answer. The four ``Count`` cells
#: that used to be BinderExceptions, and the two ``Count`` cells that used to be
#: a silently wrong 1, are the reason this card exists.
_SCALAR_EXPECTED = {
    # literals — `Count(x)` promotes `x` to `{x}`, so 1 (0 for null)
    "CountLiteral": 1,
    "CountNull": 0,
    "CountStringLiteral": 1,
    "CountBooleanLiteral": 1,
    "SumLiteral": 7,
    "MinLiteral": 7,
    "MaxLiteral": 7,
    "AvgLiteral": 7,
    # a scalar define is ONE value per patient
    "CountN": 1,
    "SumN": 5,
    "MinN": 5,
    "MaxN": 5,
    "AvgN": 5,
    "CountD": 1,
    "SumD": 0.5,
    "AvgD": 0.5,
    "CountS": 1,
    "CountB": 1,
    "MinS": "abc",
    # a null scalar: Count is 0, the rest are null
    "CountNullDefine": 0,
    "CountNullStringDefine": 0,
    "SumNullDefine": None,
    "MinNullDefine": None,
    "MaxNullDefine": None,
    "AvgNullDefine": None,
}


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_aggregate_over_statically_scalar_operand_is_the_singleton_case(engine):
    """`Count/Min/Max/Sum/Avg(<scalar>)` must be a singleton, never a row aggregate."""
    for ctx, label in _connections():
        if label != engine:
            continue
        with ctx as con:
            sql = _translate(_SCALAR_LIBRARY, _SCALAR_COLUMNS, con)
            for token in _ROW_AGGREGATE:
                assert token not in sql.upper(), (
                    f"{engine}: a raw SQL row aggregate ({token}) was emitted "
                    "for a statically scalar operand; the implicit "
                    "`T -> List<T>` promotion makes every such aggregate the "
                    f"singleton case. Generated SQL:\n{sql}"
                )
            row = _row(con, sql)
            assert row["Initial Population"] is True, row
            for column, want in _SCALAR_EXPECTED.items():
                got = _value(row, column)
                if isinstance(want, float):
                    assert got == pytest.approx(want), (
                        f"{engine}: {column} expected {want}, got {got}"
                    )
                else:
                    assert got == want, (
                        f"{engine}: {column} expected {want}, got {got}"
                    )


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_list_aggregates_are_unchanged(engine):
    """The GUARD RAILS: a real/list-valued operand still aggregates its ELEMENTS."""
    expected = {
        "CountListLiteral": 3,
        "SumListLiteral": 13,
        "MaxListLiteral": 9,
        "CountStoredList": 2,
        "SumStoredList": 13,
        "MinStoredList": 4,
        "MaxStoredList": 9,
        "AvgStoredList": 6.5,
        "CountQuery": 2,
        "CountDistinct": 2,
    }
    for ctx, label in _connections():
        if label != engine:
            continue
        with ctx as con:
            sql = _translate(_LIST_LIBRARY, _LIST_COLUMNS, con)
            row = _row(con, sql)
            for column, want in expected.items():
                got = _value(row, column)
                if isinstance(want, float):
                    assert got == pytest.approx(want), (
                        f"{engine}: {column} expected {want}, got {got}"
                    )
                else:
                    assert got == want, (
                        f"{engine}: {column} expected {want}, got {got}"
                    )


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_list_parameter_still_counts_elements(engine):
    """A `List<T>` PARAMETER is already a list — the promotion must not shrink it."""
    for ctx, label in _connections():
        if label != engine:
            continue
        with ctx as con:
            sql = _translate(_PARAMETER_LIBRARY, _PARAMETER_COLUMNS, con)
            row = _row(con, sql)
            assert _value(row, "ViaListParameter") == 3, (
                f"{engine}: Count over a List<Integer> parameter must count "
                f"elements; got {row}"
            )
            assert _value(row, "SumViaListParameter") == pytest.approx(13), (
                f"{engine}: Sum over a List<Decimal> parameter must sum "
                f"elements; got {row}"
            )


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_multi_valued_define_is_not_promoted_to_a_scalar(engine):
    """The gate must NOT claim a multi-valued define: `Count` counts elements."""
    for ctx, label in _connections():
        if label != engine:
            continue
        with ctx as con:
            sql = _translate(_MULTI_VALUE_LIBRARY, _MULTI_VALUE_COLUMNS, con)
            row = _row(con, sql)
            assert _value(row, "CountGiven") == 2, (
                f"{engine}: `Patient.name.given` holds TWO values, so Count "
                f"must be 2 (not the singleton 1); got {row}"
            )
            assert _value(row, "CountGender") == 1, (
                f"{engine}: one-element property list must count as 1; got {row}"
            )
            assert _value(row, "CountGivenPlusOne") == 3, (
                f"{engine}: Count is a value inside arithmetic, not a row "
                f"aggregate; got {row}"
            )


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_element_type_rules_apply_to_the_promoted_singleton(engine):
    """Appendix B element rules survive the promotion: Sum(String) still fails.

    The promotion is a TYPE rule, so the aggregate sees `List<String>` and the
    existing static element-type validation must reject it. Without this the
    singleton branch would silently turn an invalid CQL call into an identity.
    """
    cql = """library F69Badg version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "S": 'abc'
define "Bad": Sum("S")
define "BadLiteral": Sum('abc')

define "Initial Population": exists (Patient)
"""
    columns = {
        "Initial Population": "Initial Population",
        "Bad": "Bad",
        "BadLiteral": "BadLiteral",
    }
    for ctx, label in _connections():
        if label != engine:
            continue
        with ctx as con:
            with pytest.raises(TranslationError):
                _translate(cql, columns, con)


#: Composition contexts. The old row-aggregate lowering only ever bound at a
#: definition root; inside a WHERE / lambda / comparison it was either a Binder
#: Error ("WHERE clause cannot contain aggregates!") or bound to the wrong
#: thing. Each cell below puts the aggregate where a row aggregate cannot live.
_COMPOSITION_LIBRARY = """library F69Compos version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "N": 5
define "Nul": (null as Integer)
define "L": {4, 9}

define "Compared": Count("N") > 0
define "InArithmetic": Count(7) + 1
define "InConditional": if Count("N") = 1 then 10 else 20
define "InQueryWhere": Count({1, 2} X where Count(X) > 0 return X)
define "PerElement": Count({1, 2} X return Count(X))
define "DistinctOverScalar": Count(distinct "N")
define "MixedShapes": Count("N") + Count("L")
define "CoalescedNullSum": Coalesce(Sum("Nul"), 99)

define "Initial Population": exists (Patient)
"""

_COMPOSITION_COLUMNS = {
    "Initial Population": "Initial Population",
    "Compared": "Compared",
    "InArithmetic": "InArithmetic",
    "InConditional": "InConditional",
    "InQueryWhere": "InQueryWhere",
    "PerElement": "PerElement",
    "DistinctOverScalar": "DistinctOverScalar",
    "MixedShapes": "MixedShapes",
    "CoalescedNullSum": "CoalescedNullSum",
}


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_singleton_aggregate_in_composition_contexts(engine):
    """The singleton lowering is scope-safe: WHERE, lambda, comparison, `if`."""
    expected = {
        "Compared": True,
        "InArithmetic": 2,
        "InConditional": 10,
        "InQueryWhere": 2,
        "PerElement": 2,
        "DistinctOverScalar": 1,
        "MixedShapes": 3,
        "CoalescedNullSum": 99,
    }
    for ctx, label in _connections():
        if label != engine:
            continue
        with ctx as con:
            sql = _translate(_COMPOSITION_LIBRARY, _COMPOSITION_COLUMNS, con)
            row = _row(con, sql)
            for column, want in expected.items():
                got = _value(row, column)
                assert got == want, (
                    f"{engine}: {column} expected {want}, got {got}"
                )

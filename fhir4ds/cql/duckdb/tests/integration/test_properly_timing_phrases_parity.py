"""CQL `properly between` and `properly within ... of` timing phrases (FHIR4-46).

SPEC GROUND TRUTH
=================
CQL 1.5.3 grammar (https://cql.hl7.org/2019May/grammar.html, and identical in
2.0 at https://cql.hl7.org/grammar.html) accepts ``properly`` on FOUR
productions; this card covers the two that had no translator dispatch:

    expression 'properly'? 'between' expressionTerm 'and' expressionTerm   #betweenExpression
    ('starts' | 'ends' | 'occurs')? 'properly'? 'within' quantity 'of'
        ('start' | 'end')?                                                #withinIntervalOperatorPhrase

Appendix B has no dedicated "Properly Between" / "Properly Within" section, so
the normative reading comes from the operators these phrases lower to. The HL7
reference implementation is the authority for the lowering
(cqframework/clinical_quality_language, ``cql-to-elm`` ``Cql2ElmVisitor``):

* ``visitBetweenExpression`` — for a NON-interval first argument it emits
  ``And(Greater(first, second), Less(first, third))`` for ``properly between``
  and ``And(GreaterOrEqual, LessOrEqual)`` for plain ``between``;
  ``cql-to-elm/src/commonTest/kotlin/.../ProperlyBetweenTest.kt`` pins exactly
  that (its docstring: *"``between`` should emit ``And(GreaterOrEqual,
  LessOrEqual)``. ``properly between`` should emit ``And(Greater, Less)``."*).
  So ``properly between`` is EXCLUSIVE on both bounds — boundary contact is
  FALSE.
* ``visitBetweenExpression`` — for an INTERVAL first argument it emits
  ``IncludedIn(first, Interval[second, third])`` (inclusive bounds) and
  ``ProperIncludedIn`` for ``properly between``. Appendix B §Between agrees on
  the plain form: *"When the first argument to a between is an interval, the
  operator is a synonym for the during (or included in) operator, using the
  first argument and an inclusive interval constructed from the second and
  third arguments."*
* ``visitWithinIntervalOperatorPhrase`` emits
  ``In(A, Interval(B - Q, B + Q))`` where the constructed interval's bounds are
  CLOSED for plain ``within`` and OPEN for ``properly within`` —
  i.e. ``|A - B| < Q`` instead of ``|A - B| <= Q``. Boundary contact is FALSE.
* ELM schema ``ProperIn`` (schemas/elm/expression.xsd) documents the
  ``T, Interval`` overload as *"true if the given point is greater than the
  starting point, and less than the ending point of the interval"*, and
  ``In`` as *"for open interval boundaries, exclusive comparison operators are
  used [...] If the second argument is null the result is false."* An OPEN
  NULL bound is an unknown boundary — this engine already answers that as
  UNKNOWN/null (FHIR4-40/FHIR4-42), so ``A properly within Q of null`` is null.

``properly between`` keeps ``between``'s null-argument guard (any null operand
→ null), mirroring the plain form; the reference implementation's raw 3VL AND
would answer ``false`` for e.g. ``5 properly between null and 3`` while this
engine's ``between`` answers null, and the two forms must stay consistent.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.errors import ParseError
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression
from fhir4ds.cql.translator import translate_cql

from .wasm_runtime_helpers import assert_no_python_result, no_python_connection


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def _translate_defines(defines: dict[str, str]) -> dict[str, str]:
    lines = ["library FHIR4_46 version '1.0.0'", "using FHIR version '4.0.1'"]
    for name, expression in defines.items():
        lines.append(f"define {name}: {expression}")
    translated = translate_cql("\n".join(lines))
    return {name: translated[name].to_sql() for name in defines}


# ---------------------------------------------------------------------------
# Parser: both phrases are grammar-valid and now reach a dispatch site.
# ---------------------------------------------------------------------------


def test_cql_properly_timing_phrases_parse_to_dispatchable_operators() -> None:
    """`properly between` / `properly within` must PARSE (they are grammar-valid).

    Before FHIR4-46 both spellings raised ``ParseError: Unexpected trailing
    tokens ... PROPERLY 'properly'`` because the parser's ``PROPERLY`` branch
    only recognised the includes/included-in/during family and restored its
    position otherwise. Grammar-valid spellings must reach a translator
    dispatch site instead of failing at the grammar boundary (the FHIR4-43
    doctrine is the mirror image: a spelling the grammar does NOT have must be
    rejected, not silently translated).
    """
    point = parse_expression("5 properly between 1 and 10")
    assert isinstance(point, BinaryExpression)
    assert point.operator == "properly between"
    # Same right-hand shape as the plain form: low and high under an `and`.
    assert isinstance(point.right, BinaryExpression)
    assert point.right.operator == "and"

    interval = parse_expression("Interval[2, 9] properly between 1 and 10")
    assert isinstance(interval, BinaryExpression)
    assert interval.operator == "properly between"

    within = parse_expression("@2014-01-01 properly within 3 days of @2014-01-03")
    assert isinstance(within, BinaryExpression)
    assert within.operator == "properly within 3 days of"

    starts = parse_expression(
        "Interval[@2014-01-01, @2014-01-05] starts properly within 3 days of @2014-01-03"
    )
    assert isinstance(starts, BinaryExpression)
    assert starts.operator == "starts properly within 3 days of"

    ends = parse_expression(
        "Interval[@2014-01-05, @2014-01-08] ends properly within 3 days of @2014-01-07"
    )
    assert isinstance(ends, BinaryExpression)
    assert ends.operator == "ends properly within 3 days of"


def test_cql_properly_timing_phrases_still_reject_non_cql_spellings() -> None:
    """FHIR4-43 gains preserved: `properly contains` / `properly in` stay rejected."""
    for expression in ("Interval[1, 10] properly contains 5", "5 properly in Interval[1, 10]"):
        with pytest.raises(ParseError) as excinfo:
            parse_expression(expression)
        message = str(excinfo.value)
        assert "cannot be used with 'properly'" in message, message
        assert "properly includes" in message, message

    # An incomplete `properly within` phrase is still a parse error, never a
    # silently-consumed modifier.
    for expression in (
        "5 properly within 3 days",
        "5 properly within of @2014-01-01",
        "5 properly between 1",
    ):
        with pytest.raises(ParseError):
            parse_expression(expression)


# ---------------------------------------------------------------------------
# Lowering: exclusive bounds for the point form, proper inclusion for intervals
# ---------------------------------------------------------------------------


def test_cql_properly_between_lowers_to_exclusive_comparisons() -> None:
    sql = _translate_defines(
        {
            "PointBetweenDef": "5 properly between 1 and 10",
            "BetweenDef": "5 between 1 and 10",
            "DateBetweenDef": "@2014-01-02 properly between @2014-01-01 and @2014-01-03",
            "IvlBetweenDef": "Interval[2, 9] properly between 1 and 10",
            "IvlBetweenControlDef": "Interval[2, 9] between 1 and 10",
        }
    )

    # Point form: strict `>` / `<` on both bounds (reference: And(Greater, Less)).
    assert "5 > 1" in sql["PointBetweenDef"], sql["PointBetweenDef"]
    assert "5 < 10" in sql["PointBetweenDef"], sql["PointBetweenDef"]
    assert ">=" not in sql["PointBetweenDef"], sql["PointBetweenDef"]
    assert "<=" not in sql["PointBetweenDef"], sql["PointBetweenDef"]

    # Control keeps the inclusive operators (And(GreaterOrEqual, LessOrEqual)).
    assert "5 >= 1" in sql["BetweenDef"], sql["BetweenDef"]
    assert "5 <= 10" in sql["BetweenDef"], sql["BetweenDef"]

    # Temporal operands keep the precision-aware comparison helpers.
    assert "cqlAfter" in sql["DateBetweenDef"], sql["DateBetweenDef"]
    assert "cqlBefore" in sql["DateBetweenDef"], sql["DateBetweenDef"]

    # Interval first argument: proper inclusion in the INCLUSIVE bound interval
    # (Appendix B §Between + reference ProperIncludedIn).
    assert "intervalProperlyIncludedIn" in sql["IvlBetweenDef"], sql["IvlBetweenDef"]
    assert "intervalIncludedIn" not in sql["IvlBetweenDef"], sql["IvlBetweenDef"]
    assert "intervalIncludedIn" in sql["IvlBetweenControlDef"], sql["IvlBetweenControlDef"]


def test_cql_properly_within_lowers_to_exclusive_offsets() -> None:
    sql = _translate_defines(
        {
            "WithinPhrase": "@2014-01-01 properly within 3 days of @2014-01-03",
            "WithinControl": "@2014-01-01 within 3 days of @2014-01-03",
            "StartsPhrase": (
                "Interval[@2014-01-01, @2014-01-05] starts properly within 3 days of @2014-01-03"
            ),
            "EndsPhrase": (
                "Interval[@2014-01-05, @2014-01-08] ends properly within 3 days of @2014-01-07"
            ),
        }
    )

    # Plain `within N of` is |A - B| <= N; the proper form is |A - B| < N, so
    # the constructed interval bounds are EXCLUSIVE (reference:
    # createInterval(lower, !isProper, upper, !isProper)).
    assert "<=" in sql["WithinControl"], sql["WithinControl"]
    assert "<=" not in sql["WithinPhrase"], sql["WithinPhrase"]
    assert "<" in sql["WithinPhrase"], sql["WithinPhrase"]

    # starts/ends extract the boundary first, then apply the strict offsets.
    assert "intervalStart" in sql["StartsPhrase"], sql["StartsPhrase"]
    assert "<=" not in sql["StartsPhrase"], sql["StartsPhrase"]
    assert "intervalEnd" in sql["EndsPhrase"], sql["EndsPhrase"]
    assert "<=" not in sql["EndsPhrase"], sql["EndsPhrase"]


# ---------------------------------------------------------------------------
# Semantics matrix on all three engines
# ---------------------------------------------------------------------------

#: define name -> (expression, expected result row)
_PROPERLY_CASES: dict[str, tuple[str, tuple]] = {
    # --- point `properly between`: EXCLUSIVE on both bounds -------------
    "PBBetweenTrue": ("5 properly between 1 and 10", (True,)),
    "PBBetweenLowContact": ("1 properly between 1 and 10", (False,)),
    "PBBetweenHighContact": ("10 properly between 1 and 10", (False,)),
    "PBBetweenBelow": ("0 properly between 1 and 10", (False,)),
    "PBBetweenAbove": ("11 properly between 1 and 10", (False,)),
    "PBBetweenSinglePoint": ("5 properly between 5 and 5", (False,)),
    # plain form is inclusive (control)
    "BetweenLowContactInclusive": ("1 between 1 and 10", (True,)),
    "BetweenHighContactInclusive": ("10 between 1 and 10", (True,)),
    # other point types
    "PBBetweenDecimal": ("2.5 properly between 1.0 and 3.0", (True,)),
    "PBBetweenDecimalContact": ("1.0 properly between 1.0 and 3.0", (False,)),
    "PBBetweenString": ("'b' properly between 'a' and 'c'", (True,)),
    "PBBetweenStringContact": ("'a' properly between 'a' and 'c'", (False,)),
    "PBBetweenDate": ("@2014-01-02 properly between @2014-01-01 and @2014-01-03", (True,)),
    "PBBetweenDateContact": ("@2014-01-01 properly between @2014-01-01 and @2014-01-03", (False,)),
    # uncertainty: day-precision operand against hour-precision bounds is the
    # Appendix B §Between example shape (`DateTimeBetweenIsNull`).
    "PBBetweenUncertain": (
        "@2012-01-01 properly between @2012-01-01T12 and @2012-01-02T12",
        (None,),
    ),
    # null operands mirror `between`'s null guard
    "PBBetweenNullLow": ("5 properly between (null as Integer) and 10", (None,)),
    "PBBetweenNullHigh": ("5 properly between 1 and (null as Integer)", (None,)),
    "PBBetweenNullLeft": ("(null as Integer) properly between 1 and 10", (None,)),
    # --- interval first argument: proper inclusion ----------------------
    # ProperIncludedIn(i1, i2) = IncludedIn(i1, i2) and i1 <> i2 (ELM schema),
    # so sharing a bound with the constructed [low, high] interval is still
    # TRUE — the strictness is "strictly smaller", not "strictly inside".
    "PBIvlBetweenTrue": ("Interval[2, 9] properly between 1 and 10", (True,)),
    "PBIvlBetweenSharedLowBound": ("Interval[1, 9] properly between 1 and 10", (True,)),
    "PBIvlBetweenSharedHighBound": ("Interval[2, 10] properly between 1 and 10", (True,)),
    "PBIvlBetweenEqual": ("Interval[1, 10] properly between 1 and 10", (False,)),
    "PBIvlBetweenWider": ("Interval[0, 11] properly between 1 and 10", (False,)),
    "PBIvlBetweenUnit": ("Interval[5, 5] properly between 1 and 10", (True,)),
    "IvlBetweenInclusive": ("Interval[1, 10] between 1 and 10", (True,)),
    # --- `properly within ... of`: |A - B| < N --------------------------
    "PWWithinTrue": ("@2014-01-01 properly within 3 days of @2014-01-03", (True,)),
    "PWWithinContact": ("@2014-01-01 properly within 2 days of @2014-01-03", (False,)),
    "PWWithinOutside": ("@2014-01-01 properly within 3 days of @2014-01-05", (False,)),
    "PWWithinSymmetric": ("@2014-01-05 properly within 3 days of @2014-01-03", (True,)),
    "WithinContactInclusive": ("@2014-01-01 within 2 days of @2014-01-03", (True,)),
    "PWWithinSameDay": ("@2014-01-03 properly within 1 day of @2014-01-03", (True,)),
    "PWWithinDateTimeTrue": (
        "@2014-01-01T10:00 properly within 3 hours of @2014-01-01T12:00",
        (True,),
    ),
    "PWWithinDateTimeContact": (
        "@2014-01-01T10:00 properly within 2 hours of @2014-01-01T12:00",
        (False,),
    ),
    "PWWithinNullRight": ("@2014-01-01 properly within 3 days of (null as Date)", (None,)),
    "PWWithinNullLeft": ("(null as Date) properly within 3 days of @2014-01-03", (None,)),
    # starts/ends boundary extraction keeps the strict offsets
    "PWStartsTrue": (
        "Interval[@2014-01-01, @2014-01-05] starts properly within 3 days of @2014-01-03",
        (True,),
    ),
    "PWStartsContact": (
        "Interval[@2014-01-02, @2014-01-05] starts properly within 1 day of @2014-01-03",
        (False,),
    ),
    "PWEndsTrue": (
        "Interval[@2014-01-05, @2014-01-08] ends properly within 3 days of @2014-01-07",
        (True,),
    ),
    "PWEndsContact": (
        "Interval[@2014-01-05, @2014-01-09] ends properly within 2 days of @2014-01-07",
        (False,),
    ),
}


def test_cql_properly_timing_phrase_semantics_match_python_and_cpp_engines() -> None:
    """py-fallback == native-loaded == no-Python, and the values are the spec's."""
    defines = {name: expression for name, (expression, _) in _PROPERLY_CASES.items()}
    translated = _translate_defines(defines)

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, (_expression, expected) in _PROPERLY_CASES.items():
                sql = f"SELECT {translated[name]}"
                py_result = py.execute(sql).fetchone()
                cpp_result = cpp.execute(sql).fetchone()
                assert cpp_result == py_result, f"{name}: cpp={cpp_result} py={py_result}"
                assert_no_python_result(no_py, sql, py_result, label=name)
                assert py_result == expected, f"{name}: {py_result} != {expected}"
    finally:
        py.close()
        cpp.close()


# ---------------------------------------------------------------------------
# Population (WHERE-clause) context: the same strictness, end to end
# ---------------------------------------------------------------------------

_POPULATION_RESOURCES_SQL = """
CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR);
INSERT INTO resources VALUES
 ('p1','Patient','{"resourceType":"Patient","id":"p1"}','p1'),
 ('p2','Patient','{"resourceType":"Patient","id":"p2"}','p2'),
 ('e1','Encounter','{"resourceType":"Encounter","id":"e1","period":{"start":"2020-06-16"}}','p1'),
 ('e2','Encounter','{"resourceType":"Encounter","id":"e2","period":{"start":"2020-06-18"}}','p2'),
 ('o1','Observation','{"resourceType":"Observation","id":"o1","valueQuantity":{"value":5,"unit":"g","code":"g","system":"http://unitsofmeasure.org"}}','p1'),
 ('o2','Observation','{"resourceType":"Observation","id":"o2","valueQuantity":{"value":1,"unit":"g","code":"g","system":"http://unitsofmeasure.org"}}','p2');
"""

_POPULATION_LIBRARY = """
library Fhir4_46Pop version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Enc: [Encounter]
define Obs: [Observation]
define ProperBP: exists (Obs O where O.value as Quantity properly between 1 'g' and 10 'g')
define ProperWithin: exists (Enc E where E.period.start properly within 3 days of @2020-06-15)
define PlainWithin: exists (Enc E where E.period.start within 3 days of @2020-06-15)
"""


def test_cql_properly_timing_phrases_work_in_population_where_clauses() -> None:
    """The strict reading survives the dynamic FHIR / population-SQL path.

    p1 starts 1 day from the anchor (properly within 3 days → true); p2 starts
    exactly 3 days away, which the plain form accepts and the proper form
    rejects. Same discriminator for the quantity: 5 g is properly between
    1 g and 10 g, exactly 1 g is not.
    """
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_POPULATION_LIBRARY),
        output_columns={
            "ProperBP": "ProperBP",
            "ProperWithin": "ProperWithin",
            "PlainWithin": "PlainWithin",
        },
    )
    expected = [
        ("p1", True, True, True),
        ("p2", False, False, True),
    ]

    for connection in (_python_only_connection(), _cpp_connection()):
        try:
            connection.execute(_POPULATION_RESOURCES_SQL)
            rows = connection.execute(
                f"SELECT * FROM ({sql}) ORDER BY patient_id"
            ).fetchall()
        finally:
            connection.close()
        assert rows == expected, rows


# ---------------------------------------------------------------------------
# Former gap, now fixed by FHIR4-50
# ---------------------------------------------------------------------------


def test_cql_within_offset_time_operands_evaluate() -> None:
    """Both `within ... of` forms evaluate on Time operands (was FHIR4-50's gap).

    FHIR4-46 kept this as a strict xfail: the lowering cast both operands
    through TIMESTAMP, so a Time value ('T12:00') raised
    ``ConversionException`` at bind time — for the plain form as well, so the
    ``properly`` modifier did not introduce it. FHIR4-50 gives the family a
    Time-aware path (``dateAddQuantity``/``dateSubtractQuantity`` bounds plus
    the precision-aware ``cqlSameOrAfter``/``cqlSameOrBefore`` family); the
    full matrix lives in ``test_within_time_operands_parity.py``.
    """
    cases = {
        "@T10:00 properly within 3 hours of @T12:00": (True,),
        "@T10:00 within 3 hours of @T12:00": (True,),
    }
    translated = _translate_defines({f"WithinTimeGap{i}": e for i, e in enumerate(cases)})
    con = _python_only_connection()
    try:
        for index, (expression, expected) in enumerate(cases.items()):
            sql = translated[f"WithinTimeGap{index}"]
            assert "AS TIMESTAMP" not in sql, (expression, sql)
            assert con.execute(f"SELECT {sql}").fetchone() == expected, expression
    finally:
        con.close()

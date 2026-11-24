"""CQL function overload resolution — end-to-end, both engines (AMUX-167).

A function call must resolve to its **least-converting** overload
(CQL 1.5 Developer's Guide, "Function Resolution" and "Conversion
Precedence"): an exact type match beats an implicit conversion, two equally
converting overloads are an error, and Table 9-E defines no implicit
``Decimal -> Integer`` conversion at all.

Reproducers are the cql-tests ``CqlOverloadMatching`` cases of PR #142 and
its draft twin #61 (``A(1.0)`` returned the ``Integer`` overload). Before the
fix every non-fluent call was resolved by name through two last-wins maps, so
the result depended on declaration order.

Every case runs on a native-loaded connection and on the forced Python
fallback and must give the same answer on both.
"""

from __future__ import annotations

import itertools
import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.errors import TranslationError
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator

PATIENT = {"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1980-01-01"}
ENCOUNTER = {
    "resourceType": "Encounter",
    "id": "e1",
    "status": "finished",
    "class": {"code": "IMP"},
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2026-01-05T10:00:00", "end": "2026-01-06T10:00:00"},
}
OBSERVATION = {
    "resourceType": "Observation",
    "id": "o1",
    "status": "final",
    "issued": "2026-01-05T11:00:00Z",
    "subject": {"reference": "Patient/p1"},
    "valueQuantity": {"value": 5.0, "unit": "mg"},
}
CONDITION = {
    "resourceType": "Condition",
    "id": "c1",
    "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
    "subject": {"reference": "Patient/p1"},
}
RESOURCES = (PATIENT, ENCOUNTER, OBSERVATION, CONDITION)


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


@pytest.fixture(params=["python-fallback", "native"])
def engine(request):
    con = _python_only_connection() if request.param == "python-fallback" else _cpp_connection()
    yield con
    con.close()


def _evaluate(con: duckdb.DuckDBPyConnection, cql: str, definition: str = "output"):
    """Translate ``cql`` and execute ``definition``; returns the scalar result.

    Raises the translator's error when translation fails.
    """
    con.execute(
        "CREATE OR REPLACE TABLE resources "
        "(patient_id VARCHAR, id VARCHAR, resourceType VARCHAR, resource JSON)"
    )
    con.execute("DELETE FROM resources")
    for resource in RESOURCES:
        con.execute(
            "INSERT INTO resources VALUES (?, ?, ?, ?)",
            ("p1", resource["id"], resource["resourceType"], json.dumps(resource)),
        )
    translator = CQLToSQLTranslator(connection=con)
    sql = translator.translate_library_to_sql(parse_cql(cql), final_definition=definition)
    rows = con.execute(sql).fetchall()
    assert len(rows) == 1, rows
    return rows[0][0]


def _library(body: str, fhir: bool = False) -> str:
    using = "using FHIR version '4.0.1'\ncontext Patient\n" if fhir else ""
    return f"library OverloadMatching version '1.0.0'\n{using}{body}\n"


# AMUX-167 Stage 1 resolves a call by argument type ONLY on the direct call
# path, where the argument types are statically known, and only when the
# answer is unambiguous (an unknown argument type, a tie, or no callable
# candidate keeps today's by-name answer). The expectations below need the
# resolution to also reach INLINED FUNCTION BODIES and fluent/method syntax,
# and to raise on an ambiguous or unresolvable call — that is Stage 2, and it
# changes which body a library inlines, so it needs its own DQM gate.
# ``strict=True``: when Stage 2 lands these flip to XPASS and must be
# un-marked, which keeps the gap visible instead of silently skipped.
STAGE2 = pytest.mark.xfail(
    strict=True,
    reason=(
        "AMUX-167 Stage 2: needs overload resolution inside inlined function "
        "bodies and on fluent/method syntax, plus translate-time errors for "
        "ambiguous or unresolvable calls. Stage 1 is a conservative no-op "
        "there."
    ),
)


# ---------------------------------------------------------------------------
# cql-tests #142 CqlOverloadMatching and its draft twin #61
# ---------------------------------------------------------------------------

INT_OVERLOAD = "define function A(foo Integer): 'IntegerOverload'"
LONG_OVERLOAD = "define function A(foo Long): 'LongOverload'"
DEC_OVERLOAD = "define function A(foo Decimal): 'DecimalOverload'"
QTY_OVERLOAD = "define function A(foo Quantity): 'QuantityOverload'"

# (overloads in cql-tests order, call, expected) — the expectation must not
# depend on declaration order, so every case also runs with the overloads
# declared in reverse.
SIMPLE_OVERLOAD_CASES = {
    "142 ExactIntegerOverThanConversion": ([INT_OVERLOAD, DEC_OVERLOAD], "A(1)", "IntegerOverload"),
    "142 ImplicitIntegerToDecimal": ([DEC_OVERLOAD], "A(1)", "DecimalOverload"),
    "142 ExactLongOverload": ([INT_OVERLOAD, LONG_OVERLOAD], "A(1L)", "LongOverload"),
    "142 ImplicitIntegerToLong": ([LONG_OVERLOAD], "A(1)", "LongOverload"),
    "142 ExactDecimalOverQuantity": ([DEC_OVERLOAD, QTY_OVERLOAD], "A(1.0)", "DecimalOverload"),
    "61 SimpleOverloadMatching": ([DEC_OVERLOAD, INT_OVERLOAD], "A(1.0)", "DecimalOverload"),
    "Integer resolves Decimal before Quantity (simple type before class type)": (
        [QTY_OVERLOAD, DEC_OVERLOAD],
        "A(1)",
        "DecimalOverload",
    ),
    "Long resolves Decimal before Quantity": ([QTY_OVERLOAD, DEC_OVERLOAD], "A(1L)", "DecimalOverload"),
    "Decimal resolves Quantity when no Decimal overload exists": ([INT_OVERLOAD, QTY_OVERLOAD], "A(1.0)", "QuantityOverload"),
    "Long argument resolves the Long overload before Decimal": ([DEC_OVERLOAD, LONG_OVERLOAD], "A(1L)", "LongOverload"),
}


@pytest.mark.parametrize("reverse", [False, True], ids=["declared-order", "reverse-order"])
@pytest.mark.parametrize("name", sorted(SIMPLE_OVERLOAD_CASES))
def test_overload_choice_follows_conversion_precedence_not_declaration_order(engine, name, reverse):
    overloads, call, expected = SIMPLE_OVERLOAD_CASES[name]
    declared = list(reversed(overloads)) if reverse else overloads
    cql = _library("\n".join(declared) + f"\ndefine output: {call}")
    assert _evaluate(engine, cql) == expected


@STAGE2
def test_ambiguous_overload_is_a_translation_error(engine):
    """cql-tests #142 AmbiguousOverload: Integer converts to Long and Decimal equally."""
    cql = _library(f"{LONG_OVERLOAD}\n{DEC_OVERLOAD}\ndefine output: A(1)")
    with pytest.raises(TranslationError, match=r"Ambiguous call to function 'A'\(Integer\).*'A\(Long\)', 'A\(Decimal\)'"):
        _evaluate(engine, cql)


@STAGE2
@pytest.mark.parametrize(
    "overloads, call",
    [
        ([INT_OVERLOAD, LONG_OVERLOAD], "A(1.0)"),  # there is no Decimal -> Integer or -> Long conversion
        ([INT_OVERLOAD, DEC_OVERLOAD], "A('1')"),  # String -> Integer/Decimal is explicit only
        ([INT_OVERLOAD, DEC_OVERLOAD], "A(true)"),  # Boolean -> Integer/Decimal is explicit only
        ([INT_OVERLOAD, LONG_OVERLOAD, DEC_OVERLOAD], "A(@2024-01-01)"),  # Date -> Integer/Long/Decimal: none
    ],
    ids=["Decimal-to-Integer-and-Long", "String", "Boolean", "Date"],
)
def test_no_implicit_conversion_does_not_exist(engine, overloads, call):
    cql = _library("\n".join(overloads) + f"\ndefine output: {call}")
    with pytest.raises(TranslationError, match="no overload is callable with these argument types"):
        _evaluate(engine, cql)


@pytest.mark.parametrize(
    "overload, call, result",
    [
        ([INT_OVERLOAD], "A(1.0)", "IntegerOverload"),
        ([LONG_OVERLOAD], "A(1.0)", "LongOverload"),
        ([INT_OVERLOAD], "A('1')", "IntegerOverload"),
    ],
    ids=["Decimal-to-lone-Integer", "Decimal-to-lone-Long", "String-to-lone-Integer"],
)
def test_a_lone_overload_is_not_type_checked(engine, overload, call, result):
    """Boundary of the fix: a call that only one overload can take is inlined
    unchecked, as it always was.

    Overload resolution chooses among candidates; it is not a call
    type-checker. The translator's static typing is not complete enough to
    reject calls (CMS871 passes a tuple where a resource is declared), so the
    ``Decimal -> Integer`` rule governs which overload a Decimal selects, not
    whether a lone overload accepts one.
    """
    cql = _library("\n".join(overload) + f"\ndefine output: {call}")
    assert _evaluate(engine, cql) == result


MULTI_ARGUMENT_OVERLOADS = (
    "define function A(x Integer, y Decimal): 'int-dec'\n"
    "define function A(x Decimal, y Integer): 'dec-int'\n"
)


def test_multi_argument_overloads_resolve_per_argument(engine):
    """Each argument's position decides: no tie, so the unique best wins."""
    assert _evaluate(engine, _library(MULTI_ARGUMENT_OVERLOADS + "define output: A(1, 2.0)")) == "int-dec"
    assert _evaluate(engine, _library(MULTI_ARGUMENT_OVERLOADS + "define output: A(1.0, 1)")) == "dec-int"


@STAGE2
def test_ambiguous_multi_argument_overloads(engine):
    """An evenly converting tie is a translate-time error (Stage 2)."""
    with pytest.raises(TranslationError, match="Ambiguous call to function 'A'"):
        _evaluate(engine, _library(MULTI_ARGUMENT_OVERLOADS + "define output: A(1, 1)"))


@STAGE2
def test_overloads_inside_function_bodies_resolve_by_argument_type(engine):
    cql = _library(f"{INT_OVERLOAD}\n{DEC_OVERLOAD}\ndefine function B(): A(1.0)\ndefine output: B()")
    assert _evaluate(engine, cql) == "DecimalOverload"
    cql = _library(f"{DEC_OVERLOAD}\n{INT_OVERLOAD}\ndefine function B(): A(1.0)\ndefine output: B()")
    assert _evaluate(engine, cql) == "DecimalOverload"


def test_explicit_cast_resolves_an_ambiguous_call(engine):
    cql = _library(f"{LONG_OVERLOAD}\n{DEC_OVERLOAD}\ndefine output: A(1 as Decimal)")
    assert _evaluate(engine, cql) == "DecimalOverload"
    cql = _library(f"{LONG_OVERLOAD}\n{DEC_OVERLOAD}\ndefine output: A(convert 1 to Long)")
    assert _evaluate(engine, cql) == "LongOverload"


# ---------------------------------------------------------------------------
# Method syntax: the receiver is the first argument
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reverse", [False, True], ids=["int-first", "decimal-first"])
@STAGE2
def test_method_syntax_resolves_by_receiver_type(engine, reverse):
    declared = (
        "define function T(x Integer): 'int'\ndefine function T(x Decimal): 'dec'"
        if not reverse
        else "define function T(x Decimal): 'dec'\ndefine function T(x Integer): 'int'"
    )
    cql = _library(declared + "\ndefine V: 1.5\ndefine W: 2\ndefine output: V.T() + '/' + W.T()")
    assert _evaluate(engine, cql) == "dec/int"


@pytest.mark.parametrize("reverse", [False, True], ids=["int-first", "decimal-first"])
@STAGE2
def test_method_syntax_binds_the_receiver_to_the_first_parameter(engine, reverse):
    """``X.f()`` passes ``X`` as the first argument of a non-fluent ``f`` too.

    The inliner used to look ``f`` up by name and never bind the receiver, so
    a body that used its parameter referenced an unbound name
    (``Referenced column "x" was not found`` — the CMS108/CMS190 workaround).
    """
    body = "define function Twice(x Integer): x * 2\ndefine function Twice(x Decimal): x * 2.5"
    declared = "\n".join(reversed(body.split("\n"))) if reverse else body
    cql = _library(
        declared + "\n"
        # The receiver is a function parameter, so each call site's receiver
        # type is the parameter's declared type.
        "define function whole(x Integer): x.Twice()\n"
        "define function fractional(x Decimal): x.Twice()\n"
        "define doubledWhole: whole(3)\n"
        "define doubledFraction: fractional(1.5)"
    )
    assert _evaluate(engine, cql, definition="doubledWhole") == 6
    assert _evaluate(engine, cql, definition="doubledFraction") == 3.75


@pytest.mark.parametrize(
    "reverse",
    [
        # The overload the receiver belongs to was declared last: today's
        # by-name answer already is the right one.
        pytest.param(False, id="dateTime-last"),
        pytest.param(True, id="dateTime-first", marks=STAGE2),
    ],
)
def test_method_syntax_on_a_fhir_primitive_picks_the_models_overload(engine, reverse):
    """``E.period.start.Conv()``: the receiver is a FHIR ``dateTime``."""
    overloads = [f"define function Conv(value {t}): '{t}'" for t in ("instant", "date", "dateTime")]
    declared = list(reversed(overloads)) if reverse else overloads
    cql = _library("\n".join(declared) + "\ndefine E: First([Encounter])\ndefine output: E.period.start.Conv()", fhir=True)
    assert _evaluate(engine, cql) == "dateTime"


@STAGE2
def test_nested_fluent_call_inside_a_function_body_resolves_by_receiver_type(engine):
    # The inliner resolves nested calls by name too; the receiver type must decide.
    for observation_first in (True, False):
        obs = "define fluent function kind(X List<Observation>): 'obs'"
        proc = "define fluent function kind(X List<Procedure>): 'proc'"
        declared = f"{obs}\n{proc}" if observation_first else f"{proc}\n{obs}"
        cql = _library(
            declared + "\ndefine function K(): First([Observation]).kind()\ndefine output: K()",
            fhir=True,
        )
        assert _evaluate(engine, cql) == "obs", observation_first
        cql = _library(
            declared + "\ndefine function K(Obs List<Observation>): First(Obs).kind()\ndefine output: K([Observation])",
            fhir=True,
        )
        assert _evaluate(engine, cql) == "obs", observation_first


# ---------------------------------------------------------------------------
# FHIR model types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", list(itertools.permutations(["instant", "dateTime", "date"])))
def test_fhir_typed_overloads_match_the_model_type_of_the_argument(engine, declared):
    """FHIRHelpers shape: ``ToDateTime`` is overloaded on the FHIR primitive."""
    overloads = "\n".join(f"define function Conv(value {t}): '{t}'" for t in declared)
    cql = _library(
        overloads + "\ndefine E: First([Encounter])\ndefine output: Conv(E.period.start)",
        fhir=True,
    )
    assert _evaluate(engine, cql) == "dateTime"


@pytest.mark.parametrize(
    "retrieve, expected",
    [("Condition", "base"), ("ConditionProblemsHealthConcerns", "profile")],
)
def test_profile_argument_is_a_subtype_of_its_base_not_the_other_way_round(engine, retrieve, expected):
    cql = _library(
        "define function P(c List<Condition>): 'base'\n"
        "define function P(c List<ConditionProblemsHealthConcerns>): 'profile'\n"
        f"define output: P([{retrieve}])",
        fhir=True,
    )
    assert _evaluate(engine, cql) == expected

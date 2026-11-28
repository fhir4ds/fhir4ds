"""FHIR4-105 — a navigation define reference is the navigation it names; a list is never compared with one value.

Every navigation define on the context resource is stored the same way, as a one-row list
(`from_json(fhirpath(_pt.patient_resource, '<path>'), '["VARCHAR"]')`), whatever the element's
cardinality. A reference reached its consumers as that list:

- ``define Gen: Patient.gender`` is a ``String`` in CQL (``gender`` is 0..1), yet ``"Gen" = 'female'``
  was emitted as ``CQLListEqualEq(<list>, 'female')`` and failed at run time with
  ``No function matches ... array_length(STRING_LITERAL)``; ``Upper("Gen")`` called ``upper(VARCHAR[])``;
  ``"BYear" = @1980-02-29`` cast the list to text and answered FALSE for a patient born that day;
  ``Coalesce("Gen", 'none')`` answered a LIST.
- ``define Given: Patient.name.given`` is a ``List<String>``, so ``"Given" = 'Jane'`` has no overload
  in CQL (no list-to-element conversion). That too was a run-time binder error instead of a typed one.

Now a reference to a navigation that holds at most ONE element is translated as the navigation
itself (so it lowers exactly like the inline spelling), and a list compared with a single value is
rejected at translate time with both operand types named. A list compared with a list is unchanged:
element by element, IN ORDER, for ``=`` and for ``~`` alike (CQL Appendix B §10.4: "for each element
in the lists, in order, the elements are equivalent") — the tests therefore never assert which order
an unordered navigation happens to produce, only that the reversed order is not equivalent.
"""

from __future__ import annotations

import json
import re as _re
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection
from fhir4ds.cql.errors import TranslationError

_P = ("p1", "p2", "p3", "p4")

PATIENTS: dict[str, dict] = {
    "p1": {"resourceType": "Patient", "id": "p1", "gender": "female", "active": True,
           "birthDate": "1980-02-29", "multipleBirthInteger": 2,
           "name": [{"family": "Doe", "given": ["Jane", "Ann"]}]},
    "p2": {"resourceType": "Patient", "id": "p2"},
    "p3": {"resourceType": "Patient", "id": "p3", "gender": "male", "active": False,
           "birthDate": "1990-12-31", "name": [{"family": "Roe", "given": ["Zoe"]}]},
    # female but NOT active, and a real 0 (so ``+ 1`` cannot be mistaken for a null answer)
    "p4": {"resourceType": "Patient", "id": "p4", "gender": "female", "active": False,
           "multipleBirthInteger": 0},
}

_SOURCES = """define "Gen": Patient.gender
define "Flag": Patient.active
define "BYear": Patient.birthDate
define "Births": Patient.multipleBirthInteger
define "Given": Patient.name.given
define "Gen2": "Gen"
"""

_VALUE_DEFINES = """define "GenEquals": "Gen" = 'female'
define "GenNotEquals": "Gen" != 'female'
define "GenEquivalent": "Gen" ~ 'FEMALE'
define "GenUpper": Upper("Gen")
define "FlagEquals": "Flag" = true
define "FlagNotEquals": "Flag" != true
define "FlagAnd": "Flag" and true
define "FlagNot": not "Flag"
define "BirthEquals": "BYear" = @1980-02-29
define "BirthsPlusOne": "Births" + 1
define "GenInList": "Gen" in { 'female', 'other' }
define "GenBetween": "Gen" between 'f' and 'g'
define "GenCoalesce": Coalesce("Gen", 'none')
define "AliasEquals": "Gen2" = 'female'
define "InlineGenEquals": Patient.gender = 'female'
define "InlineGenUpper": Upper(Patient.gender)
"""

#: the list consumers of these defines are not this card's to change and must keep their answers
_UNCHANGED_LIST_CONSUMERS = """define "GenCount": Count("Gen")
define "GivenExists": exists "Given"
"""

_FEMALE = {"p1": True, "p2": False, "p3": False, "p4": True}
_NOT_FEMALE = {"p1": False, "p2": False, "p3": True, "p4": False}
_GEN_TEXT = {"p1": "female", "p2": None, "p3": "male", "p4": "female"}

EXPECTED: dict[str, dict[str, object]] = {
    "GenEquals": _FEMALE,
    "GenNotEquals": _NOT_FEMALE,
    "GenEquivalent": _FEMALE,
    "GenUpper": {patient: value.upper() if value else None for patient, value in _GEN_TEXT.items()},
    "FlagEquals": {"p1": True, "p2": False, "p3": False, "p4": False},
    "FlagNotEquals": {"p1": False, "p2": False, "p3": True, "p4": True},
    "FlagAnd": {"p1": True, "p2": False, "p3": False, "p4": False},
    "FlagNot": {"p1": False, "p2": False, "p3": True, "p4": True},
    "BirthEquals": {"p1": True, "p2": False, "p3": False, "p4": False},
    "BirthsPlusOne": {"p1": 3.0, "p2": None, "p3": None, "p4": 1.0},
    "GenInList": _FEMALE,
    # null propagates through `between`; Coalesce takes its second argument when the first is null
    "GenBetween": {"p1": True, "p2": None, "p3": False, "p4": True},
    "GenCoalesce": {patient: value or "none" for patient, value in _GEN_TEXT.items()},
    "AliasEquals": _FEMALE,
    "InlineGenEquals": _FEMALE,
    "InlineGenUpper": {patient: value.upper() if value else None for patient, value in _GEN_TEXT.items()},
    # unchanged: a list consumer still reads the define's stored list
    "GenCount": {"p1": 1, "p2": 0, "p3": 1, "p4": 1},
    "GivenExists": {"p1": True, "p2": False, "p3": True, "p4": False},
}

_LIST_DEFINES = """define "EmptyEqualsEmpty": "Given" = {}
define "EmptyEquivalentEmpty": "Given" ~ {}
define "OneMember": "Given" ~ { 'Zoe' }
define "DiffersFromOther": "Given" != { 'Zoe' }
define "GivenCount": Count("Given")
define "SameElementsInSomeOrder": ("Given" ~ { 'Jane', 'Ann' }) or ("Given" ~ { 'Ann', 'Jane' })
define "EqualInSomeOrder": ("Given" = { 'Jane', 'Ann' }) or ("Given" = { 'Ann', 'Jane' })
define "ReversedOrderIsNotEquivalent": ("Given" ~ { 'Jane', 'Ann' }) and ("Given" ~ { 'Ann', 'Jane' })
define "ReversedOrderIsNotEqual": ("Given" = { 'Jane', 'Ann' }) and ("Given" = { 'Ann', 'Jane' })
"""

_LIST_EXPECTED: dict[str, dict[str, object]] = {
    # p2 and p4 have no name at all, so their list is empty — and an empty list equals an empty list
    "EmptyEqualsEmpty": {"p1": False, "p2": True, "p3": False, "p4": True},
    "EmptyEquivalentEmpty": {"p1": False, "p2": True, "p3": False, "p4": True},
    "OneMember": {"p1": False, "p2": False, "p3": True, "p4": False},
    "DiffersFromOther": {"p1": True, "p2": True, "p3": False, "p4": True},
    "GivenCount": {"p1": 2, "p2": 0, "p3": 1, "p4": 0},
    "SameElementsInSomeOrder": {"p1": True, "p2": False, "p3": False, "p4": False},
    "EqualInSomeOrder": {"p1": True, "p2": False, "p3": False, "p4": False},
    # CQL 1.5 §10.4 Equivalent (List): "for each element in the lists, in order" — `~` is not a set comparison
    "ReversedOrderIsNotEquivalent": {"p1": False, "p2": False, "p3": False, "p4": False},
    "ReversedOrderIsNotEqual": {"p1": False, "p2": False, "p3": False, "p4": False},
}

#: (expression over the List<String> define "Given", the CQL type the message must name for the other operand)
_TYPE_ERRORS = (
    ('"Given" = \'Jane\'', "String"),
    ('"Given" != \'Jane\'', "String"),
    ('"Given" ~ \'Jane\'', "String"),
    ('"Given" !~ \'Jane\'', "String"),
    ('\'Jane\' = "Given"', "String"),
    ('"Given" = true', "Boolean"),
    ('"Given" = @2020-01-01', "Date"),
    ('"Given" = 5 \'mg\'', "Quantity"),
    ('"Given" = null as String', "String"),
    ('"Given" = Patient.gender', "String"),
)


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines() -> Iterator[tuple[str, object]]:
    """The Python-supplement engine and the C++-only engine: the lowering must hold on both."""
    for label, build in (("python", _python_connection), ("c++", no_python_connection)):
        with build() as con:
            con.execute(
                "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                "resource JSON, patient_ref VARCHAR)"
            )
            for patient_id, resource in PATIENTS.items():
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [patient_id, "Patient", json.dumps(resource), patient_id],
                )
            yield label, con


def _library(body: str):
    from fhir4ds.cql.parser import parse_cql

    return parse_cql(
        "library NavigationDefineCompare version '1.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
        + body
    )


def _columns(body: str) -> dict[str, str]:
    names = [line.split('"')[1] for line in body.splitlines() if line.startswith("define ")]
    return {name: name for name in names}


def _population(con, body: str) -> tuple[dict[str, dict[str, object]], str]:
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = _library(_SOURCES + body)
    columns = _columns(body)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(library=library, output_columns=columns)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    answers: dict[str, dict[str, object]] = {column: {} for column in columns}
    for row in cursor.fetchall():
        for column in columns:
            value = row[names.index(column)]
            # a count arrives as BIGINT; a Boolean is not a number even though Python says otherwise
            if isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            answers[column][str(row[0])] = value
    return answers, sql


def _cte(sql: str, name: str) -> str:
    """The text of one definition's own CTE, from its name up to the next definition."""
    start = sql.index(f'"{name}" AS ')
    following = _re.search(r"\n\),\s*\"[A-Za-z0-9_]+\" AS ", sql[start:])
    if following is None:
        raise AssertionError(f"no definition follows {name!r}; its CTE cannot be delimited")
    return " ".join(sql[start : start + following.start() + 3].split())


@pytest.mark.parametrize("column", sorted(EXPECTED))
def test_a_single_valued_navigation_define_answers_as_one_value(column: str) -> None:
    for label, con in _engines():
        answers, _ = _population(con, _VALUE_DEFINES + _UNCHANGED_LIST_CONSUMERS)
        got = answers[column]
        assert set(got) == set(_P), f"[{label}] {column}: patients {sorted(got)}"
        for patient_id in _P:
            assert got[patient_id] == EXPECTED[column][patient_id], (
                f"[{label}] {column} for {patient_id}: {got[patient_id]!r}, expected {EXPECTED[column][patient_id]!r}"
            )


@pytest.mark.parametrize("column", sorted(_LIST_EXPECTED))
def test_a_list_navigation_define_is_compared_with_a_list_in_order(column: str) -> None:
    for label, con in _engines():
        answers, _ = _population(con, _LIST_DEFINES)
        got = answers[column]
        assert set(got) == set(_P), f"[{label}] {column}: patients {sorted(got)}"
        for patient_id in _P:
            assert got[patient_id] == _LIST_EXPECTED[column][patient_id], (
                f"[{label}] {column} for {patient_id}: {got[patient_id]!r}, "
                f"expected {_LIST_EXPECTED[column][patient_id]!r}"
            )


@pytest.mark.parametrize(("expression", "peer_type"), _TYPE_ERRORS)
def test_a_list_compared_with_a_single_value_is_a_typed_translation_error(
    expression: str, peer_type: str
) -> None:
    with _python_connection() as con:
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        library = _library('define "Given": Patient.name.given\n' + f'define "R": {expression}\n')
        translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
        with pytest.raises(TranslationError) as caught:
            translator.translate_library(library)
            translator.translate_library_to_population_sql(library=library, output_columns={"R": "R"})
        message = str(caught.value)
        # The TYPE is asserted above; the message must name both operand types and no other reading is relied on.
        assert "List<String>" in message, message
        assert peer_type in message, message


def test_a_reference_lowers_like_the_navigation_it_names() -> None:
    """The same predicate as the inline spelling, and no list handed to a scalar consumer."""
    for label, con in _engines():
        _, sql = _population(con, _VALUE_DEFINES)
        by_name = _cte(sql, "GenEquals").replace('"GenEquals"', '"X"', 1)
        inline = _cte(sql, "InlineGenEquals").replace('"InlineGenEquals"', '"X"', 1)
        assert by_name == inline, f"[{label}] the define spelling and the inline spelling differ"
        assert "fhirpath_text(_pt.patient_resource, 'gender') = 'female'" in inline, (
            f"[{label}] the comparison is not the navigation's own lowering"
        )
        for not_expected in (
            'CQLListEqualEq((SELECT sub.value FROM "Gen"',
            'UPPER((SELECT sub.value FROM "Gen"',
            'cqlDateTimeEqual(CAST((SELECT sub.value FROM "BYear"',
        ):
            assert not_expected not in sql, f"[{label}] a list reached a single-value consumer: {not_expected}"


#: A list-typed navigation define in a function that takes ONE String. These already raised a
#: typed error before FHIR4-105; they are pinned because the ruling for this card asks for the
#: TYPE of the error, and a binder error at run time would be the wrong one.
_STRING_FUNCTIONS = (
    ('Upper("Given")', "Upper"),
    ('Lower("Given")', "Lower"),
    ('Substring("Given", 0, 1)', "Substring"),
    ('"Given" & \'x\'', "&"),
)


@pytest.mark.parametrize(("expression", "operator"), _STRING_FUNCTIONS)
def test_a_list_navigation_define_in_a_string_function_is_a_typed_translation_error(
    expression: str, operator: str
) -> None:
    with _python_connection() as con:
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        library = _library('define "Given": Patient.name.given\n' + f'define "R": {expression}\n')
        translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
        with pytest.raises(TranslationError) as caught:
            translator.translate_library(library)
        message = str(caught.value)
        assert "List<String>" in message, message
        assert operator in message, message


#: An included library with one Boolean define, as the measure libraries write them.
_INCLUDED_LIBRARY = """library Base version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Is Active": Patient.active = true
"""

#: The measure idiom this must NOT touch: a define that only aliases an INCLUDED define
#: (`define "Initial Population": AHA."Is Adults ..."`, `"SDE Race": SDE."SDE Race"`).
_ALIASED_INCLUDE = """library AliasedInclude version '1.0'
using FHIR version '4.0.1'
context Patient
include Base version '1.0.0' called B

define "Initial Population": B."Is Active"
define "Denominator": "Initial Population" and B."Is Active"
"""


def _included_loader(alias: str, version=None):
    from fhir4ds.cql.parser import parse_cql

    return parse_cql(_INCLUDED_LIBRARY) if alias == "Base" else None


def _last_cte(sql: str, name: str) -> str:
    """The text of one definition's CTE, delimited by bracket matching (so the LAST one works too:
    its body itself begins with ``SELECT _pt.patient_id``)."""
    start = sql.index(f'"{name}" AS ')
    depth = 0
    for position in range(sql.index("(", start), len(sql)):
        if sql[position] == "(":
            depth += 1
        elif sql[position] == ")":
            depth -= 1
            if depth == 0:
                return " ".join(sql[start : position + 1].split())
    raise AssertionError(f"unbalanced CTE for {name!r}")


def test_a_define_that_only_aliases_an_included_define_is_left_as_it_is() -> None:
    """An alias of an included define is not a FHIR navigation, so it is not inlined.

    The first version of this fix treated every define whose body is a property access as a
    navigation. Measures alias included defines on every page, so it rewrote the SQL of two of
    them (CMS135, CMS144): the reference to the local define disappeared from its consumer and
    the included define's CTE changed shape. Same answers, but not what this card is for.
    """
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    columns = {"Initial Population": "Initial Population", "Denominator": "Denominator"}
    for label, con in _engines():
        library = parse_cql(_ALIASED_INCLUDE)
        translator = CQLToSQLTranslator(connection=con, library_loader=_included_loader)
        translator.translate_library(library)
        sql = translator.translate_library_to_population_sql(library=library, output_columns=columns)
        cursor = con.execute(sql)
        names = [column[0] for column in cursor.description]
        rows = {str(row[0]): tuple(row[names.index(c)] for c in columns) for row in cursor.fetchall()}
        # Only p1 is active; a Boolean define reads False at the population surface for the rest.
        assert rows == {"p1": (True, True), "p2": (False, False), "p3": (False, False), "p4": (False, False)}, (
            f"[{label}] {rows}"
        )
        denominator = _last_cte(sql, "Denominator")
        assert denominator.count('FROM "Initial Population" AS sub') == 1, (
            f"[{label}] the local define was inlined into its consumer:\n{denominator}"
        )
        assert denominator.count('FROM "B.Is Active" AS sub') == 1, f"[{label}] {denominator}"

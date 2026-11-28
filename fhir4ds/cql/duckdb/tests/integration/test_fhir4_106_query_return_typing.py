"""FHIR4-106 — a query define is typed by its RETURN, never by its source.

`define "Q": ([Observation] O return O.id)` was typed `List<Observation>`: the query-typing
path computed the return type, could not resolve it, and FELL THROUGH to the "no return clause"
branch, which reports the SOURCE's type. The source describes a query's INPUT; the define's
value is its OUTPUT, so the reported type was a lie about every element.

The lie was observable. `Combine(Q, ',')` — legal CQL over a list of ids — was rejected at
translate time:

    TranslationError: CQL string operator 'Combine' requires List<String> source;
    got List<Observation>

TWO SEPARATE CAUSES, both fixed, and both pinned here:

1. the fall-through itself. A query WITH a return clause must never report the source type; an
   element type it cannot know is `List<Any>` (or the bare singular form for a singular source).
2. the element type was genuinely unknowable for `id` because the loaded schema metadata only
   describes resource-SPECIFIC elements — `Observation.status` resolves, `Observation.id` does
   not, although `id` is a base `Resource` element. `id`/`implicitRules`/`language` are the base
   elements with a useful CQL type (all String subtypes); the complex ones (meta, text,
   contained, extension) are deliberately NOT guessed.

AND ONE CONSEQUENCE that had to be fixed with them, because without it the fix made things
worse: `Combine` over a multi-row define lowers through the generic definition lookup, which is
`(SELECT sub.value FROM "Ids" … LIMIT 1)` — ONE row wearing a list's clothes. With the typing
fixed, `Combine` reached execution and answered the FIRST id (`'o1'`) instead of joining them
(`'o1|o2|o3'`): a loud translate error turned into a SILENT wrong answer. `Combine` now goes
through the same FHIR4-65 gate `in`/`contains` use.

The honest absolute: a return type that is genuinely unknowable — `O.value` is a choice with a
set of possible types — stays `List<Any>` and `Combine` over it still fails loudly. That is the
intended behaviour, and it is pinned so "make typing work" cannot become "guess a type".
"""

from __future__ import annotations

import json

import pytest

_IDS = ("o1", "o2", "o3")
_STATUSES = ("final", "amended", "preliminary")

_PREAMBLE = """library F106 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Ids": ([Observation] O return O.id)
define "Statuses": ([Observation] O return O.status)
define "Unknowable": ([Observation] O return O.value)
define "Stored": {'a', 'b', 'c'}
"""

_EPILOGUE = """
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

_CONSUMERS = {
    "CountIds": 'Count("Ids")',
    "CombineIds": 'Combine("Ids", \'|\')',
    "CombineStatuses": 'Combine("Statuses", \'|\')',
    "CombineStored": 'Combine("Stored", \'|\')',
    "FirstId": 'First("Ids")',
}


def _connections():
    from contextlib import contextmanager

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    @contextmanager
    def _py():
        import duckdb

        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            yield con
        finally:
            con.close()

    from .wasm_runtime_helpers import no_python_connection

    yield from ((_py(), "python"), (no_python_connection(), "no_python"))


def _load(con, n_obs: int = 3) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    con.execute(
        "INSERT INTO resources VALUES ('p1','Patient',?::JSON,'p1')",
        [json.dumps({"resourceType": "Patient", "id": "p1"})],
    )
    for oid in _IDS[:n_obs]:
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [
                oid,
                "Observation",
                json.dumps(
                    {
                        "resourceType": "Observation",
                        "id": oid,
                        "status": _STATUSES[_IDS.index(oid)],
                        "subject": {"reference": "Patient/p1"},
                    }
                ),
                "p1",
            ],
        )


def _translate(con, extra_columns=()):
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    cql_text = (
        _PREAMBLE
        + "".join(f'define "{k}": {v}\n' for k, v in _CONSUMERS.items())
        + _EPILOGUE
    )
    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    wanted = ("Initial Population", "Denominator", "Numerator", *_CONSUMERS, *extra_columns)
    sql = translator.translate_library_to_population_sql(
        library=library, output_columns={name: name for name in wanted}
    )
    return translator, sql


def _run(n_obs: int = 3) -> list[tuple[str, dict]]:
    out = []
    for ctx, label in _connections():
        with ctx as con:
            _load(con, n_obs)
            _translator, sql = _translate(con)
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            out.append((label, dict(zip(names, cursor.fetchone()))))
    return out


class TestAQueryDefineIsTypedByItsReturn:
    def test_combine_over_a_returned_id_list_joins_every_element(self):
        """RED before the fix: TranslationError 'requires List<String> source'."""
        for label, row in _run(3):
            got = (row["CombineIds"] or "").split("|")
            # Order over an unordered source is arbitrary (FHIR4-109 bought consistency
            # between consumers, not a canonical order) — compare as a multiset.
            assert sorted(got) == sorted(_IDS), (
                f"{label}: Combine over a returned id list gave {row['CombineIds']!r}; "
                "every element must be combined, not just the first"
            )

    def test_the_list_is_not_truncated_to_one_element(self):
        """The consequence that made the typing fix necessary: a one-row wrap answers 'o1'."""
        for label, row in _run(3):
            assert row["CountIds"] == 3, f"{label}: Count = {row['CountIds']}"
            assert row["FirstId"] in _IDS, f"{label}: First = {row['FirstId']!r}"

    def test_a_second_string_property_also_types(self):
        for label, row in _run(3):
            got = (row["CombineStatuses"] or "").split("|")
            assert sorted(got) == sorted(_STATUSES), (
                f"{label}: Combine over returned statuses gave {row['CombineStatuses']!r} — "
                "a second String property must type AND keep every element"
            )

    def test_a_single_element_still_works(self):
        for label, row in _run(1):
            assert row["CombineIds"] == "o1", f"{label}: {row['CombineIds']!r}"


class TestAnUnknowableReturnTypeStaysHonest:
    def test_a_choice_return_is_list_any_not_the_source_type(self):
        """`O.value` is a choice with several possible types. The honest answer is List<Any> —
        what must NOT happen is silently reporting List<Observation> and pretending to know."""
        for ctx, label in _connections():
            with ctx as con:
                _load(con)
                translator, _sql = _translate(con)
                meta = translator.context.definition_meta.get("Unknowable")
            assert getattr(meta, "cql_type", None) == "List<Any>", (
                f"{label}: an unknowable element type must be List<Any>, got "
                f"{getattr(meta, 'cql_type', None)!r}"
            )

    def test_an_unknowable_list_is_not_rejected_for_a_WRONG_type(self):
        """The old bug rejected `Combine` with "got List<Observation>" — a lie. An unknown
        element type is permissive here by convention (Any may be String at runtime), so
        translation must SUCCEED; what must not happen is a rejection that names the source's
        type as if it were the element type."""
        for ctx, label in _connections():
            with ctx as con:
                _load(con)
                from fhir4ds.cql.parser import parse_cql
                from fhir4ds.cql.translator.translator import CQLToSQLTranslator

                cql_text = (
                    _PREAMBLE + 'define "AnyCombine": Combine("Unknowable", \'|\')\n' + _EPILOGUE
                )
                library = parse_cql(cql_text)
                translator = CQLToSQLTranslator(connection=con)
                translator.translate_library(library)
                translator.translate_library_to_population_sql(
                    library=library,
                    output_columns={
                        "Initial Population": "Initial Population",
                        "AnyCombine": "AnyCombine",
                    },
                )


class TestTheStoredListPathIsUnaffected:
    def test_a_stored_list_still_combines_every_element(self):
        for label, row in _run(3):
            assert row["CombineStored"] == "a|b|c", f"{label}: {row['CombineStored']!r}"

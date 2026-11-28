"""FHIR4-109 — a define is ONE VALUE: two consumers of it must not disagree.

The observed failure was never a corrupted list. Every list produced was a COMPLETE PERMUTATION
of the source; measurements put it at 0/300 non-permutations and 0/300 wrong lengths. What moved
was the ORDER, and that is enough to corrupt any POSITIONAL consumer, because the translator
materialises a multi-row define's list **per consumer**:

    "A" AS MATERIALIZED (SELECT _pt.patient_id,
        LIST_EXTRACT(COALESCE((SELECT list(_lst_src.value) FROM "Ids" _lst_src
                               WHERE _lst_src.patient_id = _pt.patient_id), []), 1) ...)
    "B" AS MATERIALIZED (... its OWN copy of the same aggregate ...)

Three ingredients are all required, and each is pinned or excluded here:

1. a CTE whose row order is UNDEFINED — the `"Condition"` retrieve CTE is `SELECT DISTINCT ...`
   (`cte_builder.py:341`). `list()` over it may return any order and DuckDB's order for a
   hash-deduped source is thread-schedule dependent. DuckDB violates no contract; this is ours.
2. two or more separate aggregate evaluation sites (that is what per-consumer materialisation
   creates).
3. threads > 1 — 0/300 at `threads=1`, and it already faults at 2.

Because 3 makes it nondeterministic, every assertion below runs the SAME translated SQL many
times and requires every run to agree. A single execution proves nothing: the observed per-run
rate ranges from ~13% to ~66% depending on host load, so a test that runs once would be a coin
flip that passes.

The invariant under test (CQL: a definition denotes one value):

    define "A": "Ids"[0]
    define "B": "Ids"[0]      -- the same expression, a second consumer

`A` must equal `B` in every run. That is the sharpest form of the defect and it needs only two
consumers — the earlier "needs three references" reading was an artefact of an assertion that
could only see `None`, never a duplicate.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

_IDS = ("c1", "c2", "c3")

#: Runs per assertion. At the worst observed rate (~13% per run) 60 clean runs still leave a
#: ~0.03% chance of a miss; fewer would not.
_RUNS = 60

_CONSUMERS = {
    "A": '"Ids"[0]',
    "B": '"Ids"[0]',
    "I0": '"Ids"[0]',
    "I1": '"Ids"[1]',
    "I2": '"Ids"[2]',
}

_PREAMBLE = """library F109 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Ids": ([Condition] C return C.id) X
"""

_EPILOGUE = """
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

_RESOURCES = [
    {"resourceType": "Patient", "id": "p1"},
    *[
        {"resourceType": "Condition", "id": cid, "subject": {"reference": "Patient/p1"}}
        for cid in _IDS
    ],
]


def _connections():
    """Python-supplement and no-Python engines: the defect is in the SQL, so both show it."""
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


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        patient_ref = (resource.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


def _translate(con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    cql_text = _PREAMBLE + "".join(
        f'define "{name}": {expr}\n' for name, expr in _CONSUMERS.items()
    ) + _EPILOGUE
    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns={name: name for name in _CONSUMERS}
    )


def _rows() -> list[dict]:
    """Execute the SAME sql many times; each execution is one independent evaluation."""
    out = []
    for ctx, _label in _connections():
        with ctx as con:
            _load(con)
            translated = _translate(con)
            for _ in range(_RUNS):
                cursor = con.execute(translated)
                names = [d[0] for d in cursor.description]
                out.append((_label, dict(zip(names, cursor.fetchone()))))
    return out


class TestADefineIsOneValue:
    def test_two_consumers_of_the_same_define_agree(self):
        """RED before the fix: each consumer runs its own aggregate over an unordered CTE."""
        rows = _rows()
        disagreements = [
            (label, row["A"], row["B"]) for label, row in rows if row["A"] != row["B"]
        ]
        assert not disagreements, (
            f'"A" and "B" are the same expression over the same define but disagreed in '
            f"{len(disagreements)} of {len(rows)} evaluations: {disagreements[:4]} — "
            "a definition must denote ONE value (CQL), so this is the translator "
            "re-materialising the define's list per consumer"
        )


class TestPositionalConsumersSeeTheSameList:
    def test_indexing_every_position_yields_every_element(self):
        """Indexing 0..n-1 of an n-element list must yield the n distinct elements."""
        bad = []
        for label, row in _rows():
            got = Counter((row["I0"], row["I1"], row["I2"]))
            if got != Counter(_IDS):
                bad.append((label, dict(got)))
        assert not bad, (
            f"indexing 0..2 of a 3-element define did not yield the 3 distinct elements in "
            f"{len(bad)} evaluations: {bad[:4]}"
        )


class TestTheAggregateIsEvaluatedOnce:
    def test_the_shared_list_is_materialised_once_not_per_consumer(self):
        """The MECHANISM, pinned on the SQL: a value-assertion alone cannot see 13 extra
        aggregate evaluations, and they are the defect (and 13x the work)."""
        for ctx, label in _connections():
            with ctx as con:
                _load(con)
                sql = _translate(con)
            assert sql.count("list(_lst_src.value)") == 1, (
                f"{label}: the define's list is materialised "
                f"{sql.count('list(_lst_src.value)')} times; it must be materialised ONCE and "
                "shared by every consumer"
            )

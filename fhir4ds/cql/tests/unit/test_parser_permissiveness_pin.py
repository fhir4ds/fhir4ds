"""The CQL parser is deliberately MORE permissive than the grammar (FHIR4-93).

DECISION (Joel, 2026-11-27): document and pin, do not tighten.

The grammar makes `aggregateClause` and `returnClause` ALTERNATIVES and puts
`sortClause` after them:

    query : sourceClause letClause? queryInclusionClause* whereClause?
            (aggregateClause | returnClause)? sortClause? ;

This parser accepts a few spellings that rule forbids. Tightening would be
spec-correct, but it is a ONE-WAY break: any CQL file in the wild leaning on the
permissive spelling stops translating, and nothing in our corpora needs the
strictness. An accepting translator is the lesser sin, so the behaviour is
recorded here as INTENTIONAL rather than left as an accident.

If someone later decides to tighten it, these tests will fail — that is the
point. Update the decision in `fhir4ds/cql/AGENTS.md`, the grammar citation
below, and this file together; do not delete the tests to make the suite green.

The grammar-legal spelling works TODAY and is pinned alongside, so a tightening
would not leave callers without an alternative.
"""

from __future__ import annotations

import pytest

from fhir4ds.cql.parser import parse_cql

_HEAD = """library P93 version '1.0.0'
using FHIR version '4.0.1'
context Patient
"""


def _parses(body: str) -> bool:
    try:
        parse_cql(_HEAD + body)
    except Exception:  # noqa: BLE001 - the question is "does it parse at all"
        return False
    return True


class TestGrammarLegalSpellings:
    """These are what the spec allows; they must keep working (the escape hatch
    if the permissive forms are ever tightened)."""

    def test_aggregate_then_sort(self):
        assert _parses("define X: ({1,2,3}) N aggregate A starting 0: A + N sort by A")

    def test_return_then_sort(self):
        assert _parses("define X: ({1,2,3}) N return N sort by N")


class TestKnownPermissiveSpellings:
    """INTENTIONAL deviations, pinned so a tightening is a decision, not a drift."""

    def test_return_then_aggregate_is_accepted(self):
        # the grammar makes aggregateClause and returnClause alternatives
        assert _parses(
            "define X: ({1,2,3}) N return N aggregate A starting 0: A + N"
        ), "if this now fails, FHIR4-93's decision was reversed — update AGENTS.md and this pin"

    def test_sort_before_where_is_accepted(self):
        # the grammar puts sortClause last
        assert _parses(
            "define X: ({1,2,3}) N sort by N where N > 1"
        ), "if this now fails, FHIR4-93's decision was reversed — update AGENTS.md and this pin"

    def test_aggregate_without_any_sort_still_parses(self):
        # the control: nothing about the permissive forms is needed to fold
        assert _parses("define X: ({1,2,3}) N aggregate A starting 0: A + N")


class TestPermissivenessDoesNotExtendToGibberish:
    """Being lenient about CLAUSE ORDER is not being lenient about syntax."""

    @pytest.mark.parametrize("body", [
        "define X: ({1,2,3}) N aggregate A starting 0 A + N",   # missing colon
        "define X: ({1,2,3}) N aggregate starting 0: A + N",    # missing alias
        "define X: ({1,2,3}) aggregate A starting 0: A + N",    # missing source alias
    ])
    def test_malformed_folds_still_raise(self, body):
        assert not _parses(body)

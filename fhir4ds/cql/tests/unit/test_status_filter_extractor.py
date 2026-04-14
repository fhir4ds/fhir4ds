"""Tests for status_filter_extractor — dynamic extraction from parsed CQL ASTs."""

import pytest
from ...parser.ast_nodes import (
    BinaryExpression,
    FunctionDefinition,
    Identifier,
    ListExpression,
    Literal,
    ParameterDef,
    Property,
    UnaryExpression,
)
from ...translator.status_filter_extractor import (
    extract_status_filter,
    extract_all_status_filters,
)


def _make_query_with_where(where_expr):
    """Helper to create a minimal Query-like object with a where clause."""
    class FakeWhereClause:
        def __init__(self, expression):
            self.expression = expression

    class FakeQuery:
        def __init__(self, where):
            self.where = FakeWhereClause(where)

    return FakeQuery(where_expr)


def _make_func(name, where_expr):
    """Create a fluent FunctionDefinition with a Query body containing where_expr."""
    return FunctionDefinition(
        name=name,
        fluent=True,
        parameters=[ParameterDef(name="X")],
        expression=_make_query_with_where(where_expr),
    )


class TestSimpleEquality:
    """Pattern 1: E.status = 'finished'"""

    def test_simple_equality(self):
        where = BinaryExpression(
            operator='=',
            left=Property(source=Identifier(name='E'), path='status'),
            right=Literal(value='finished', type='String'),
        )
        func = _make_func("isEncounterPerformed", where)
        result = extract_status_filter(func)
        assert result == {"status_field": "status", "allowed": ["finished"]}


class TestInList:
    """Pattern 2: O.status in { 'final', 'amended', 'corrected' }"""

    def test_in_list(self):
        where = BinaryExpression(
            operator='in',
            left=Property(source=Identifier(name='O'), path='status'),
            right=ListExpression(elements=[
                Literal(value='final', type='String'),
                Literal(value='amended', type='String'),
                Literal(value='corrected', type='String'),
            ]),
        )
        func = _make_func("isAssessmentPerformed", where)
        result = extract_status_filter(func)
        assert result == {
            "status_field": "status",
            "allowed": ["final", "amended", "corrected"],
        }


class TestAndCompound:
    """Pattern 3: D.status in {...} and D.intent in {...}"""

    def test_status_and_intent(self):
        where = BinaryExpression(
            operator='and',
            left=BinaryExpression(
                operator='in',
                left=Property(source=Identifier(name='D'), path='status'),
                right=ListExpression(elements=[
                    Literal(value='active', type='String'),
                    Literal(value='completed', type='String'),
                ]),
            ),
            right=BinaryExpression(
                operator='in',
                left=Property(source=Identifier(name='D'), path='intent'),
                right=ListExpression(elements=[
                    Literal(value='order', type='String'),
                    Literal(value='original-order', type='String'),
                ]),
            ),
        )
        func = _make_func("isDeviceOrderPersonalUseDevices", where)
        result = extract_status_filter(func)
        assert result["status_field"] == "status"
        assert result["allowed"] == ["active", "completed"]
        assert result["intent_field"] == "intent"
        assert result["intent_allowed"] == ["order", "original-order"]


class TestImplies:
    """Pattern 4: C.verificationStatus is not null implies (... or ...)"""

    def test_implies_with_codes(self):
        where = BinaryExpression(
            operator='implies',
            left=UnaryExpression(
                operator='is not null',
                operand=Property(source=Identifier(name='C'), path='verificationStatus'),
            ),
            right=BinaryExpression(
                operator='or',
                left=BinaryExpression(
                    operator='~',
                    left=Property(source=Identifier(name='C'), path='verificationStatus'),
                    right=Identifier(name='confirmed'),
                ),
                right=BinaryExpression(
                    operator='~',
                    left=Property(source=Identifier(name='C'), path='verificationStatus'),
                    right=Identifier(name='unconfirmed'),
                ),
            ),
        )
        codes = {
            "confirmed": {"code": "confirmed"},
            "unconfirmed": {"code": "unconfirmed"},
        }
        func = _make_func("verified", where)
        result = extract_status_filter(func, codes=codes)
        assert result["status_field"] == "verificationStatus"
        assert result["null_passes"] is True
        assert "confirmed" in result["allowed"]
        assert "unconfirmed" in result["allowed"]


class TestEquivalence:
    """Pattern: I.status ~ 'completed'"""

    def test_equivalence_literal(self):
        where = BinaryExpression(
            operator='~',
            left=Property(source=Identifier(name='I'), path='status'),
            right=Literal(value='completed', type='String'),
        )
        func = _make_func("isImmunizationAdministered", where)
        result = extract_status_filter(func)
        assert result == {"status_field": "status", "allowed": ["completed"]}


class TestNonFluentReturnsNone:
    """Non-fluent functions should return None."""

    def test_non_fluent(self):
        func = FunctionDefinition(
            name="notFluent",
            fluent=False,
            expression=_make_query_with_where(
                BinaryExpression(
                    operator='=',
                    left=Property(source=Identifier(name='E'), path='status'),
                    right=Literal(value='finished', type='String'),
                )
            ),
        )
        assert extract_status_filter(func) is None


class TestIntegrationWithStatusCql:
    """Integration test: parse actual Status.cql and extract all filters."""

    def test_extracts_all_status_filters(self):
        from ...parser.parser import CQLParser
        from ...parser.lexer import Lexer
        import os

        status_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "benchmarking", "ecqm-content-qicore-2025", "input", "cql", "Status.cql",
        )
        if not os.path.exists(status_path):
            pytest.skip("Status.cql not found")

        with open(status_path) as f:
            source = f.read()
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = CQLParser(tokens)
        lib = parser.parse_library()

        # Build codes dict from the library's code definitions
        codes = {}
        for code_def in lib.codes:
            codes[code_def.name] = {"code": code_def.code}

        filters = extract_all_status_filters(lib, codes)

        # Should extract most of the 23 fluent functions
        # (some like isDiagnosticStudyPerformed have category exists() which we skip)
        assert len(filters) >= 18, f"Expected >= 18 filters, got {len(filters)}: {list(filters.keys())}"

        # Verify specific well-known filters
        assert filters["isEncounterPerformed"]["status_field"] == "status"
        assert filters["isEncounterPerformed"]["allowed"] == ["finished"]

        assert filters["isAssessmentPerformed"]["allowed"] == ["final", "amended", "corrected"]

        assert "verified" in filters
        assert filters["verified"]["null_passes"] is True

        assert filters["isInterventionOrder"]["intent_field"] == "intent"

        assert filters["isMedicationActive"]["allowed"] == ["active"]
        assert filters["isMedicationActive"]["intent_field"] == "intent"

        # Verify smoking status
        assert filters["isObservationSmokingStatus"]["allowed"] == ["final"]

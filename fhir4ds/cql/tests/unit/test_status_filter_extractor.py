"""Tests for status_filter_extractor — dynamic extraction from parsed CQL ASTs."""

import pytest
from pathlib import Path
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


def _cql_fixture_path(filename: str):
    root = Path(__file__).resolve().parents[4]
    candidates = [
        root / "tests" / "data" / "ecqm-content-qicore-2025" / "input" / "cql" / filename,
        root / "fhir4ds" / "cql" / "resources" / "cql" / filename,
        root / "tests" / "data" / "dqm-content-qicore-2026" / "input" / "cql" / filename,
        root / "tests" / "data" / "cql" / "dqm-content-cms-2025" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    pytest.skip(f"{filename} not found")


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

        source = _cql_fixture_path("Status.cql").read_text()
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

        # extract_all_status_filters now returns name -> LIST of configs (one per
        # overload); Status.cql declares each function once, so unwrap the single
        # config for the shape assertions below.
        single = {name: cfgs[0] for name, cfgs in filters.items()}

        # Verify specific well-known filters
        assert single["isEncounterPerformed"]["status_field"] == "status"
        assert single["isEncounterPerformed"]["allowed"] == ["finished"]

        assert single["isAssessmentPerformed"]["allowed"] == ["final", "amended", "corrected"]

        assert "verified" in single
        assert single["verified"]["null_passes"] is True

        assert single["isInterventionOrder"]["intent_field"] == "intent"

        assert single["isMedicationActive"]["allowed"] == ["active"]
        assert single["isMedicationActive"]["intent_field"] == "intent"

        # Verify smoking status
        assert single["isObservationSmokingStatus"]["allowed"] == ["final"]


class TestExternalReviewB10OverloadAndPartial:
    """Regression tests for the external-review CRIT-02 findings.

    (a) Overload collision: `extract_all_status_filters` keyed configs by
        function NAME alone, so the last-registered overload won. In
        FHIRCommon.cql, `verified`/`confirmed`/`unconfirmed`/`refuted` are
        declared for BOTH Condition and AllergyIntolerance with DIFFERENT
        value sets — a Condition operand silently filtered with
        AllergyIntolerance codes.
    (b) Partial-AND drop: `_extract_and_compound` returned a left-only
        config when the right side of an AND was not a recognized status
        filter, silently dropping the un-extracted predicate when the
        dispatcher replaced the call with a status-only WHERE.
    """

    def test_overloads_keyed_with_param_type(self):
        from ...parser.parser import parse_cql
        path = _cql_fixture_path("FHIRCommon.cql")
        lib = parse_cql(path.read_text())
        filters = extract_all_status_filters(lib, None)
        # both verified overloads survive, each with its own value set
        v = filters["verified"]
        by_type = {c["param_type"]: c for c in v}
        assert by_type["Condition"]["allowed"][:2] == ["confirmed", "unconfirmed"]
        assert by_type["AllergyIntolerance"]["allowed"][:2] == [
            "allergy-confirmed", "allergy-unconfirmed",
        ]
        c = filters["confirmed"]
        assert {cfg["param_type"]: tuple(cfg["allowed"]) for cfg in c} == {
            "Condition": ("confirmed",),
            "AllergyIntolerance": ("allergy-confirmed",),
        }

    def test_matching_status_filter_picks_overload(self):
        # Resolution by the resolved function definition's parameter type.
        from ...parser.parser import parse_cql
        from ...translator.status_filter_extractor import _func_def_param_type
        path = _cql_fixture_path("FHIRCommon.cql")
        lib = parse_cql(path.read_text())
        filters = extract_all_status_filters(lib, None)
        conds = [s for s in lib.statements
                 if getattr(s, "fluent", False) and s.name == "verified"
                 and _func_def_param_type(s) == "Condition"]
        allergies = [s for s in lib.statements
                     if getattr(s, "fluent", False) and s.name == "verified"
                     and _func_def_param_type(s) == "AllergyIntolerance"]
        assert conds and allergies
        v = filters["verified"]
        cond_cfg = next(c for c in v if c["param_type"] == "Condition")
        allergy_cfg = next(c for c in v if c["param_type"] == "AllergyIntolerance")
        assert "allergy" not in " ".join(cond_cfg["allowed"]).lower()
        assert all("allergy" in a for a in allergy_cfg["allowed"])

    def test_partial_and_extraction_declines(self):
        # `status in {...} and <unrecognized predicate>` must NOT produce a
        # partial config (the right predicate would be silently dropped).
        from ...parser.parser import parse_expression
        where = parse_expression(
            "(X.status in {'final', 'amended'}) and (X.category is not null)"
        )
        cfg = None
        from ...translator import status_filter_extractor as sfe
        if isinstance(where, BinaryExpression) and where.operator == "and":
            cfg = sfe._extract_and_compound(where, None)
        assert cfg is None


class TestExternalReviewB11DefinitionDependencies:
    """HIGH-01 (external review): the definition dependency walker in
    inference.py missed CaseExpression children (comparand, case_items'
    when/then) and treated a QUALIFIED `Lib."X"` reference inside
    `define "X"` as a self-dependency, producing false
    "Cyclic dependency detected" errors for local defines that shadow an
    included-library definition name."""

    def _inst(self):
        import inspect
        import fhir4ds.cql.translator.inference as inf
        cls = next(o for n, o in vars(inf).items()
                   if inspect.isclass(o) and hasattr(o, "_extract_definition_dependencies"))
        return cls.__new__(cls)

    def test_case_item_then_and_comparand_deps_found(self):
        from ...parser.parser import parse_expression
        inst = self._inst()
        e = parse_expression(
            "case X when 'm' then \"Dep\" else \"Dep2\" end"
        )
        deps = inst._extract_definition_dependencies(e, {"Dep", "Dep2", "X"}, {})
        assert deps == {"Dep", "Dep2", "X"}

        e2 = parse_expression('case "Dep3" when null then 1 else 2 end')
        assert inst._extract_definition_dependencies(e2, {"Dep3"}, {}) == {"Dep3"}

    def test_qualified_ref_is_not_a_self_dependency(self):
        from ...parser.ast_nodes import QualifiedIdentifier
        inst = self._inst()
        qi = QualifiedIdentifier(parts=["Inc", "P1"])
        # define "P1": Inc."P1" + 1  — qualified ref targets the INCLUDED
        # library's CTE ("Inc.P1"), not the local P1.
        assert inst._extract_definition_dependencies(
            qi, {"P1"}, {}, _current_name="P1"
        ) == set()
        # Referenced from a DIFFERENT local define, it is a real (foreign-CTE)
        # dependency edge as before.
        assert inst._extract_definition_dependencies(
            qi, {"P1", "Other"}, {}, _current_name="Other"
        ) == {"P1"}


class TestExternalReviewB12CrossLibraryCodes:
    """HIGH-03 (external review): two included libraries declaring the same
    CODE name with different values — the bare-name terminology copy made the
    LAST-processed include win globally, so qualified `A."shared"` resolved to
    library B's code value (and cross-library equivalence folded TRUE)."""

    LIB_A = """
library LibA
using FHIR version '4.0.1'
codesystem "CS": 'http://example.org/x'
code "shared": 'AAA' from "CS"
"""

    LIB_B = """
library LibB
using FHIR version '4.0.1'
codesystem "CS": 'http://example.org/x'
code "shared": 'BBB' from "CS"
"""

    def _translate(self, body_defines):
        import duckdb
        from ...parser.parser import parse_cql
        from ...duckdb import register as reg
        from ...translator.translator import CQLToSQLTranslator
        from pathlib import Path
        cql = f"""
library Probe
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
include LibA called A
include LibB called B
context Patient
{body_defines}
"""
        lib = parse_cql(cql)
        con = duckdb.connect()
        reg(con)
        base = Path(__file__).resolve().parents[4] / "fhir4ds" / "cql" / "resources" / "cql"

        def loader(alias, version=None):
            if alias == "LibA":
                return parse_cql(self.LIB_A)
            if alias == "LibB":
                return parse_cql(self.LIB_B)
            f = base / f"{alias}.cql"
            return parse_cql(f.read_text()) if f.exists() else None

        t = CQLToSQLTranslator(con, library_loader=loader)
        return str(t.translate_library_to_sql(lib))

    def test_qualified_code_refs_resolve_per_library(self):
        sql = self._translate('define CodeA: A."shared"\ndefine CodeB: B."shared"')
        assert "SELECT 'AAA'" in sql, sql[:200]  # A."shared" is LibA's code
        assert "SELECT 'BBB'" in sql, sql[:200]  # B."shared" is LibB's code

    def test_cross_library_equivalence_not_clobbered(self):
        sql = self._translate('define Eq: A."shared" ~ B."shared"\ndefine EqSelf: A."shared" ~ A."shared"')
        # Different code values -> equivalence FALSE; same-library ref -> TRUE.
        assert "SELECT FALSE" in sql, sql[:200]
        assert "SELECT TRUE" in sql, sql[:200]

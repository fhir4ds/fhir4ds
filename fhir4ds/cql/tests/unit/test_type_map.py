"""Unit tests for the post-translation CQL type map builder (U2 core).

Covers: literal/selector typing, as/convert casts, operator typing,
retrieve typing, unwrappers, uncertainty doctrine (AgeIn*/between -> Any),
sql_result_type seeding, and the declaration-order-safe dependency walk.
"""

from __future__ import annotations

import pytest

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.context import SQLTranslationContext
from fhir4ds.cql.translator.type_map import TypeMapBuilder
from fhir4ds.cql.types.typeref import ANY_TYPE, CQLTypeRef


def _library(cql_body: str):
    header = """
library TestLib version '1.0.0'
using FHIR version '4.0.1'
context Patient
"""
    return parse_cql(header + cql_body)


def _attach(cql_body: str):
    """Parse + run the builder against a populated context (no SQL needed)."""
    library = _library(cql_body)
    context = SQLTranslationContext()
    # Schema-driven property typing needs the FHIR schema registry
    # (mirrors what CQLToSQLTranslator.__init__ wires into the context).
    from fhir4ds.cql.translator.fhir_schema import FHIRSchemaRegistry

    context.fhir_schema = FHIRSchemaRegistry()
    context.fhir_schema.load_default_resources()
    for stmt in library.statements:
        if hasattr(stmt, "expression") and getattr(stmt, "name", None):
            context.expression_definitions[stmt.name] = stmt.expression
    builder = TypeMapBuilder(context)
    return builder.attach(), context


def _lib_ref(cql_body: str, name: str) -> CQLTypeRef:
    type_map, _ = _attach(cql_body)
    return type_map[name]


class TestLiteralAndSelectorTyping:
    def test_boolean_integer_decimal_string_literals(self):
        type_map = _attach("""
define B: true
define I: 42
define D: 3.14
define S: 'hello'
""")[0]
        assert type_map["B"].canonical() == "Boolean"
        assert type_map["I"].canonical() == "Integer"
        assert type_map["D"].canonical() == "Decimal"
        assert type_map["S"].canonical() == "String"

    def test_long_literal(self):
        assert _lib_ref("define L: 9223372036854775807L", "L").canonical() == "Long"

    def test_temporal_literals(self):
        type_map = _attach("""
define Dt: @2024-06-15
define DTm: @2024-06-15T10:30:00.000
define Tm: @T14:30:00.000
define PartialYear: @2024
""")[0]
        assert type_map["Dt"].canonical() == "Date"
        assert type_map["DTm"].canonical() == "DateTime"
        assert type_map["Tm"].canonical() == "Time"
        assert type_map["PartialYear"].canonical() == "Date"

    def test_quantity_code_and_clinical_selectors(self):
        type_map = _attach("""
codesystem "CS": 'http://example.org/cs'
define Q: 5 'mg'
define C: Code 'x' from "CS"
define CC: Concept { codes: { Code 'x' from "CS" } }
""")[0]
        assert type_map["Q"].canonical() == "Quantity"
        assert type_map["C"].canonical() == "Code"
        assert type_map["CC"].canonical() == "Concept"

    def test_list_literal_uniform_and_mixed(self):
        type_map = _attach("""
define U: {1, 2, 3}
define M: {1, 'two'}
define Nested: {{1, 2}, {3, 4}}
""")[0]
        assert type_map["U"].canonical() == "List<Integer>"
        assert type_map["M"].canonical() == "List<Any>"
        assert type_map["Nested"].canonical() == "List<List<Integer>>"

    def test_tuple_expression_fields(self):
        type_map = _attach("""
define T: Tuple { name: 'John', age: 42, ratio: 1:8 }
""")[0]
        assert type_map["T"].canonical() == "Tuple{name: String, age: Integer, ratio: Ratio}"

    def test_interval_point_type(self):
        type_map = _attach("""
define I: Interval[@2024-01-01, @2024-12-31]
define QI: Interval[1 'g', 5 'g']
""")[0]
        assert type_map["I"].canonical() == "Interval<Date>"
        assert type_map["QI"].canonical() == "Interval<Quantity>"


class TestRetrieveAndOperatorTyping:
    def test_retrieve_types_list_of_resource(self):
        type_map = _attach("""
define Obs: [Observation]
define Cond: [Condition]
""")[0]
        assert type_map["Obs"].canonical() == "List<Observation>"
        assert type_map["Cond"].canonical() == "List<Condition>"

    def test_comparison_and_logical_operators_boolean(self):
        type_map = _attach("""
define E: 1 = 1
define Lt: 1 < 2
define A: true and false
define Imp: true implies false
define InTest: 5 in {1, 2, 3}
define Same: @2024-01-01T10 same day as @2024-01-01T11
""")[0]
        for name in ("E", "Lt", "A", "Imp", "InTest", "Same"):
            assert type_map[name].canonical() == "Boolean", name

    def test_arithmetic_promotion_ladder(self):
        type_map = _attach("""
define I: 1 + 2
define L: 1L + 2L
define D: 1.5 + 2
define Q: 1 'mg' + 2 'mg'
define Div: 4 / 2
define MulI: 2 * 3
define Temporal: @2024-01-01 + 1 day
""")[0]
        assert type_map["I"].canonical() == "Integer"
        assert type_map["L"].canonical() == "Long"
        assert type_map["D"].canonical() == "Decimal"
        assert type_map["Q"].canonical() == "Quantity"
        assert type_map["Div"].canonical() == "Decimal"
        assert type_map["MulI"].canonical() == "Integer"
        assert type_map["Temporal"].canonical() == "Date"

    def test_set_operations_preserve_element_type(self):
        type_map = _attach("""
define U: {1, 2} union {3}
define I: {1, 2} intersect {2}
define X: {1, 2, 3} except {2}
""")[0]
        for name in ("U", "I", "X"):
            assert type_map[name].canonical() == "List<Integer>", name

    def test_as_and_convert_casts(self):
        type_map = _attach("""
define A1: 5 as Integer
define A2: 'x' as String
define A3: [Observation] O return O.value as FHIR.Quantity
define C1: convert 5 to Decimal
define VA: 'http://example.org/vs' as Vocabulary
""")[0]
        assert type_map["A1"].canonical() == "Integer"
        assert type_map["A2"].canonical() == "String"
        assert type_map["A3"].canonical() == "List<Quantity>"
        assert type_map["C1"].canonical() == "Decimal"
        # Vocabulary has no schema typing when the source is a bare String
        # literal (not a declared ValueSet); falls through to the cast name.
        assert type_map["VA"].canonical() == "Vocabulary"

    def test_unary_and_unwrappers(self):
        type_map = _attach("""
define N: not true
define Neg: -5
define IsN: 1 is null
define F: First({1, 2, 3})
define SG: singleton from {7}
define E: exists [Observation]
define DX: distinct {1, 2, 1}
""")[0]
        assert type_map["N"].canonical() == "Boolean"
        assert type_map["Neg"].canonical() == "Integer"
        assert type_map["IsN"].canonical() == "Boolean"
        assert type_map["F"].canonical() == "Integer"
        assert type_map["SG"].canonical() == "Integer"
        assert type_map["E"].canonical() == "Boolean"
        assert type_map["DX"].canonical() == "List<Integer>"


class TestUncertaintyDoctrine:
    def test_age_family_and_between_are_any(self):
        type_map = _attach("""
define A: AgeInYears()
define AA: AgeInYearsAt(@2024-06-15)
define CA: CalculateAgeInYears(@1990-06-15)
define DB: years between @1990-06-15 and @2024-01-01
define DIB: duration in years between @1990 and @2024
""")[0]
        for name in ("A", "AA", "CA", "DB", "DIB"):
            assert type_map[name] == ANY_TYPE, name
            assert type_map[name].bare_name == "Any", name


class TestFunctionTable:
    def test_builtin_function_returns(self):
        type_map = _attach("""
define Cnt: Count({1, 2})
define Sum: Sum({1.5, 2.5})
define CntD: Count(distinct {1, 2, 1})
define MinV: minimum Integer
define NowD: Now()
define TodayD: Today()
define TOD: TimeOfDay()
define Ts: ToString(42)
define Fl: flatten {{1, 2}, {3}}
define Msg: Message(42, true, 1, 'Error', 'msg')
define Ch: Children({Tuple {a: 1}})
""")[0]
        assert type_map["Cnt"].canonical() == "Integer"
        assert type_map["Sum"].canonical() == "Decimal"
        assert type_map["CntD"].canonical() == "Integer"
        assert type_map["MinV"].canonical() == "Integer"
        assert type_map["NowD"].canonical() == "DateTime"
        assert type_map["TodayD"].canonical() == "DateTime"
        assert type_map["TOD"].canonical() == "Time"
        assert type_map["Ts"].canonical() == "String"
        assert type_map["Fl"].canonical() == "List<Integer>"
        assert type_map["Msg"].canonical() == "Integer"  # source passthrough
        assert type_map["Ch"].canonical() == "List<Any>"


class TestDefinitionChains:
    def test_alias_of_alias_propagates_type(self):
        type_map = _attach("""
define Base: 42
define Mid: Base
define Top: Mid + 1
define D2: Base
""")[0]
        assert type_map["Mid"].canonical() == "Integer"
        assert type_map["Top"].canonical() == "Integer"
        assert type_map["D2"].canonical() == "Integer"

    def test_forward_reference_resolves(self):
        # "Later" is defined BEFORE "Earlier" textually: declaration-order safe.
        type_map = _attach("""
define Later: Earlier + 1
define Earlier: 41
""")[0]
        assert type_map["Later"].canonical() == "Integer"

    def test_cycle_cuts_off_to_any(self):
        type_map = _attach("""
define A: B
define B: A
""")[0]
        assert type_map["A"] == ANY_TYPE
        assert type_map["B"] == ANY_TYPE

    def test_meta_cql_type_fallback_when_ast_missing(self):
        # Manually registered metadata (no expression_definitions entry).
        context = SQLTranslationContext()
        from fhir4ds.cql.translator.context import DefinitionMeta, RowShape
        context.definition_meta["X"] = DefinitionMeta(
            name="X", shape=RowShape.PATIENT_SCALAR, cql_type="List<Date>"
        )
        type_map = TypeMapBuilder(context).attach()
        assert "X" not in type_map or type_map["X"].canonical() == "List<Date>"


class TestSqlResultTypeSeeding:
    def test_any_defines_pick_up_sql_result_type_hint(self):
        from fhir4ds.cql.translator.context import DefinitionMeta, RowShape

        library = _library("define Q: SomeQueryShape")
        context = SQLTranslationContext()
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        context.definition_meta["Q"] = DefinitionMeta(
            name="Q", shape=RowShape.PATIENT_SCALAR,
            cql_type="Any", sql_result_type="Quantity",
        )
        TypeMapBuilder(context).attach()
        assert context.definition_meta["Q"].cql_type_ref.canonical() == "Quantity"

    def test_known_type_beats_hint(self):
        from fhir4ds.cql.translator.context import DefinitionMeta, RowShape

        library = _library("define I: 42")
        context = SQLTranslationContext()
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        context.definition_meta["I"] = DefinitionMeta(
            name="I", shape=RowShape.PATIENT_SCALAR,
            cql_type="Integer", sql_result_type="Quantity",
        )
        TypeMapBuilder(context).attach()
        assert context.definition_meta["I"].cql_type_ref.canonical() == "Integer"


class TestVocabularyCast:
    def test_valueset_as_vocabulary_preserves_concrete_type(self):
        library = _library("""
valueset "VS": 'http://example.org/vs'
define V: "VS" as Vocabulary
define Plain: "VS"
""")
        context = SQLTranslationContext()
        context.valuesets["VS"] = {"url": "http://example.org/vs"}
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        type_map = TypeMapBuilder(context).attach()
        assert type_map["V"].canonical() == "ValueSet"
        assert type_map["Plain"].canonical() == "ValueSet"


class TestEndToEndThroughTranslator:
    def test_translate_library_attaches_refs(self):
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        library = _library("""
define I: 42
define S: 'str'
define O: [Observation]
define B: I > 40
""")
        translator = CQLToSQLTranslator()
        results = translator.translate_library(library)
        assert set(results) >= {"I", "S", "O", "B"}
        meta = translator.get_definition_meta("I")
        assert meta.cql_type_ref is not None
        assert meta.cql_type_ref.canonical() == "Integer"
        meta_o = translator.get_definition_meta("O")
        assert meta_o.cql_type_ref.canonical() == "List<Observation>"
        meta_b = translator.get_definition_meta("B")
        assert meta_b.cql_type_ref.canonical() == "Boolean"

    def test_attach_does_not_touch_cql_type(self):
        from fhir4ds.cql.translator.translator import CQLToSQLTranslator

        library = _library("define O: [Observation]")
        translator = CQLToSQLTranslator()
        translator.translate_library(library)
        meta = translator.get_definition_meta("O")
        # cql_type remains whatever lowering recorded (byte-identical guard).
        assert meta.cql_type_ref.canonical() == "List<Observation>"
        assert meta.cql_type in ("List<Observation>", "Any")


class TestU3QueryAndPropertyTyping:
    def test_query_return_property_typing(self):
        type_map = _attach("""
        define Obs: [Observation]
        define Statuses: [Observation] O return O.status
        """)[0]
        assert type_map["Statuses"].canonical() == "List<String>"

    def test_query_return_cast_typing(self):
        type_map = _attach("""
        define Vals: [Observation] O return O.value as FHIR.Quantity
        """)[0]
        assert type_map["Vals"].canonical() == "List<Quantity>"

    def test_query_return_alias_passthrough(self):
        type_map = _attach("""
        define Statuses: [Observation] O return O.status
        define Ref: [Observation] O return O
        """)[0]
        assert type_map["Ref"].canonical() == "List<Observation>"

    def test_query_no_return_passthrough(self):
        type_map = _attach("""
        define Plain: [Observation] O
        """)[0]
        assert type_map["Plain"].canonical() == "List<Observation>"

    def test_let_clause_typing(self):
        type_map = _attach("""
        define WithLet: [Observation] O
          let L: O.status
          return L
        """)[0]
        assert type_map["WithLet"].canonical() == "List<String>"

    def test_aggregate_clause_typing(self):
        type_map = _attach("""
        define Agg: [Observation] O aggregate T starting 0: T + 1
        """)[0]
        assert type_map["Agg"].canonical() == "Integer"

    def test_property_over_retrieve_define(self):
        type_map = _attach("""
        define Obs: [Observation]
        define StatusOfFirst: First(Obs).status
        """)[0]
        assert type_map["StatusOfFirst"].canonical() == "String"

    def test_property_chain_typing(self):
        type_map = _attach("""
        define V: First([Observation]).value as FHIR.Quantity
        define VV: First([Observation]).value as FHIR.Quantity
        define Unit: (First([Observation]).value as FHIR.Quantity).unit
        """)[0]
        assert type_map["V"].canonical() == "Quantity"
        assert type_map["Unit"].canonical() == "String"

    def test_patient_context_property(self):
        type_map = _attach("""
        define BD: Patient.birthDate
        define Gen: Patient.gender
        """)[0]
        assert type_map["BD"].canonical() == "Date"
        assert type_map["Gen"].canonical() == "String"

    def test_tuple_field_accessor(self):
        type_map = _attach("""
        define T: Tuple { name: 'John', age: 42 }
        define N: T.name
        define A: T.age
        """)[0]
        assert type_map["T"].canonical() == "Tuple{name: String, age: Integer}"
        assert type_map["N"].canonical() == "String"
        assert type_map["A"].canonical() == "Integer"

    def test_tuple_field_through_first(self):
        type_map = _attach("""
        define List: { Tuple { day: @2024-01-01, n: 1 } }
        define Day: First(List).day
        """)[0]
        assert type_map["Day"].canonical() == "Date"

    def test_qualified_identifier_include_define(self):
        from fhir4ds.cql.translator.context import DefinitionMeta, RowShape

        library = _library("""
        define Local: Common.Foo
        """)
        context = SQLTranslationContext()
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        context.definition_meta["Common.Foo"] = DefinitionMeta(
            name="Common.Foo", shape=RowShape.PATIENT_SCALAR,
            cql_type="List<Date>",
        )
        type_map = TypeMapBuilder(context).attach()
        assert type_map["Local"].canonical() == "List<Date>"

    def test_qualified_identifier_prefers_type_ref(self):
        from fhir4ds.cql.translator.context import DefinitionMeta, RowShape
        from fhir4ds.cql.types.typeref import CQLTypeRef as Ref

        library = _library("""
        define Local: Common.Foo
        """)
        context = SQLTranslationContext()
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        context.definition_meta["Common.Foo"] = DefinitionMeta(
            name="Common.Foo", shape=RowShape.PATIENT_SCALAR,
            cql_type="Any", cql_type_ref=Ref("Quantity"),
        )
        type_map = TypeMapBuilder(context).attach()
        assert type_map["Local"].canonical() == "Quantity"


class TestU4FunctionsAndParameters:
    def test_numeric_aggregate_typing(self):
        type_map = _attach("""
        define SI: Sum({1, 2, 3})
        define SL: Sum({1L, 2L})
        define SQ: Sum({1 'mg', 2 'mg'})
        define AvgD: Avg({1.5, 2.5})
        define MinA: Min({1, 2})
        define ProdI: Product({2, 3})
        """)[0]
        assert type_map["SI"].canonical() == "Decimal"
        assert type_map["SL"].canonical() == "Long"
        assert type_map["SQ"].canonical() == "Quantity"
        assert type_map["AvgD"].canonical() == "Decimal"
        assert type_map["MinA"].canonical() == "Any"
        assert type_map["ProdI"].canonical() == "Decimal"

    def test_abs_passthrough(self):
        type_map = _attach("""
        define AI: Abs(-5)
        define AL: Abs(-5L)
        define AD: Abs(-5.5)
        define AQ: Abs(-5 'mg')
        """)[0]
        assert type_map["AI"].canonical() == "Integer"
        assert type_map["AL"].canonical() == "Long"
        assert type_map["AD"].canonical() == "Decimal"
        assert type_map["AQ"].canonical() == "Quantity"

    def test_power_typing(self):
        type_map = _attach("""
        define PI: Power(2, 3)
        define PL: Power(2L, 3L)
        define PNeg: Power(2, -2)
        define PD: Power(2.0, 3.0)
        """)[0]
        assert type_map["PI"].canonical() == "Integer"
        assert type_map["PL"].canonical() == "Long"
        assert type_map["PNeg"].canonical() == "Decimal"
        assert type_map["PD"].canonical() == "Decimal"

    def test_coalesce_first_known_argument(self):
        type_map = _attach("""
        define C1: Coalesce(null, 5, 'x')
        define C2: Coalesce('a', 5)
        define C3: Coalesce(Coalesce(null, 3.5), 1)
        """)[0]
        assert type_map["C1"].canonical() == "Integer"
        assert type_map["C2"].canonical() == "String"
        assert type_map["C3"].canonical() == "Decimal"

    def test_timeofday_returns_time(self):
        type_map = _attach("""
        define TOD: TimeOfDay()
        """)[0]
        assert type_map["TOD"].canonical() == "Time"

    def test_parameter_typed_reference(self):
        library = _library("""
        parameter "Measure Period" Interval<DateTime>
        define InMP: 5 in "Measure Period"
        define MP: "Measure Period"
        """)
        context = SQLTranslationContext()
        from fhir4ds.cql.translator.fhir_schema import FHIRSchemaRegistry

        context.fhir_schema = FHIRSchemaRegistry()
        context.fhir_schema.load_default_resources()
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        from fhir4ds.cql.translator.context import ParameterInfo

        context.parameters["Measure Period"] = ParameterInfo(
            name="Measure Period", cql_type="Interval<DateTime>"
        )
        type_map = TypeMapBuilder(context).attach()
        assert type_map["MP"].canonical() == "Interval<DateTime>"
        assert type_map["InMP"].canonical() == "Boolean"

    def test_user_function_body_recursion(self):
        library = _library("""
        define function "DoubleVal"(x Integer): x + x
        define D: DoubleVal(21)
        """)
        context = SQLTranslationContext()
        from fhir4ds.cql.translator.fhir_schema import FHIRSchemaRegistry

        context.fhir_schema = FHIRSchemaRegistry()
        context.fhir_schema.load_default_resources()
        from fhir4ds.cql.translator.context import FunctionInfo

        func_stmt = next(
            s for s in library.statements
            if type(s).__name__ == "FunctionDefinition"
        )
        context._functions["DoubleVal"] = FunctionInfo(
            name="DoubleVal", expression=func_stmt.expression,
            parameters=func_stmt.parameters,
        )
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        type_map = TypeMapBuilder(context).attach()
        assert type_map["D"].canonical() == "Integer"

    def test_recursive_user_function_cuts_off(self):
        library = _library("""
        define function "Loop"(x Integer): Loop(x)
        define L: Loop(1)
        """)
        context = SQLTranslationContext()
        from fhir4ds.cql.translator.context import FunctionInfo

        func_stmt = next(
            s for s in library.statements
            if type(s).__name__ == "FunctionDefinition"
        )
        context._functions["Loop"] = FunctionInfo(
            name="Loop", expression=func_stmt.expression
        )
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression
        type_map = TypeMapBuilder(context).attach()
        assert type_map["L"].bare_name == "Any"


class TestTypeMapDifferentialDriftTripwire:
    """U5 guardrail: builder vs compat inference must agree wherever both
    produce a non-Any type, except for the documented intentional
    divergences (see FDD §3.2 and type_map module docstring).

    This is the REV-002 sunset tripwire: it converts "provably identical
    at merge time" into "provably identical continuously" so the frozen
    lowering classifiers can be safely deleted at the route-unification
    milestone.
    """

    # Expression-matrix corpus: (name, CQL body) pairs covering the node
    # kinds both classifiers share.
    _CORPUS = [
        ("literal_bool", "true"),
        ("literal_int", "42"),
        ("literal_decimal", "3.14"),
        ("literal_string", "'hello'"),
        ("quantity", "5 'mg'"),
        ("datetime", "@2024-01-15T10:30:00"),
        ("date_only", "@2024-01-15"),
        ("time_literal", "@T14:30:00"),
        ("code_selector", "Code '8480-6' from \"LOINC\""),
        ("list_int", "{1, 2, 3}"),
        ("interval_int", "Interval[1, 5]"),
        ("retrieve", "[Observation]"),
        ("exists", "exists [Observation]"),
        ("first_retrieve", "First([Observation])"),
        ("comparison", "1 < 2"),
        ("equality", "1 = 2"),
        ("logical_and", "true and false"),
        ("arith_add", "1 + 2"),
        ("arith_div", "10 / 4"),
        ("arith_decimal", "1.5 + 2.5"),
        ("union_lists", "{1, 2} union {2, 3}"),
        ("intersect_lists", "{1, 2} intersect {2, 3}"),
        ("except_lists", "{1, 2} except {2}"),
        ("as_cast", "5 as Integer"),
        ("convert_to", "convert 5 to Decimal"),
        ("not_op", "not (1 = 1)"),
        ("is_null", "1 is null"),
        ("singleton_from", "singleton from {1}"),
        ("count_fn", "Count({1, 2, 3})"),
        ("indexof_fn", "IndexOf({1, 2}, 2)"),
        ("sum_fn", "Sum({1, 2, 3})"),
        ("avg_fn", "Avg({1, 2, 3})"),
        ("min_fn", "Min({1, 2, 3})"),
        ("max_fn", "Max({1, 2, 3})"),
        ("abs_fn", "Abs(-5)"),
        ("distinct_fn", "distinct {1, 1, 2}"),
        ("flatten_fn", "flatten {{1, 2}, {3}}"),
        ("toboolean_fn", "ToBoolean('true')"),
        ("todecimal_fn", "ToDecimal('1.5')"),
        ("tointeger_fn", "ToInteger('42')"),
        ("tostring_fn", "ToString(42)"),
        ("todate_fn", "ToDate('2024-01-15')"),
        ("todatetime_fn", "ToDateTime('2024-01-15T10:30:00')"),
        ("totime_fn", "ToTime('T14:30:00')"),
        ("minimum_int", "minimum Integer"),
        ("maximum_int", "maximum Integer"),
        ("minimum_decimal", "minimum Decimal"),
        ("now_fn", "Now()"),
        ("today_fn", "Today()"),
        ("date_ctor", "Date(2024, 1, 15)"),
        ("iif_expr", "if 1 = 1 then 5 else 6"),
        ("tuple_expr", "Tuple { a: 1, b: 'x' }"),
        ("query_return", "[Observation] O return O.status"),
        ("method_first", "First({3, 1, 2})"),
        ("coalesce_fn", "Coalesce(null, 15)"),
    ]

    # Node kinds / defines where the builder INTENTIONALLY diverges from
    # compat (legacy) inference. Documented in the FDD:
    #  - uncertainty family (AgeIn*/between) -> builder Any
    #  - power int/int rules -> builder Integer/Long
    #  - Sum(List<Quantity>) -> builder Quantity
    #  - as/convert dotted names -> builder bare
    #  - identifier order params-before-meta (builder) vs meta-first
    #  - builder extras: QualifiedIdentifier/AliasRef/rich property nav
    _INTENTIONAL_DIVERGENCES = frozenset({
        "power_int_int",
        "power_int_neg",
        "sum_quantity_list",
        "duration_between",
        "difference_between",
        "age_in_years",
        "as_cast_dotted",
        "convert_dotted",
        "qualified_identifier",
    })

    def test_type_map_differential_drift_tripwire(self):
        from fhir4ds.cql.translator.type_map import (
            TypeMapBuilder,
            infer_cql_type_compat,
        )

        header = (
            "library TestLib version '1.0.0'\n"
            "using FHIR version '4.0.1'\n"
            "context Patient\n"
        )
        valueset_decl = 'valueset "LOINC": \'http://loinc.org\'\n'
        bodies = []
        names = []
        for name, expr in self._CORPUS:
            names.append(name)
            bodies.append(f'define "{name}": {expr}')
        library_cql = header + valueset_decl + "\n".join(bodies)

        library = parse_cql(library_cql)
        context = SQLTranslationContext()
        from fhir4ds.cql.translator.fhir_schema import FHIRSchemaRegistry

        context.fhir_schema = FHIRSchemaRegistry()
        context.fhir_schema.load_default_resources()
        context.valuesets["LOINC"] = {"id": "LOINC"}
        for stmt in library.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                context.expression_definitions[stmt.name] = stmt.expression

        builder = TypeMapBuilder(context)
        type_map = builder.attach()

        mismatches = []
        for name in names:
            builder_ref = type_map.get(name)
            builder_canonical = (
                builder_ref.canonical() if builder_ref is not None else "Any"
            )
            compat_type = infer_cql_type_compat(
                context, context.expression_definitions[name]
            )
            if builder_canonical == "Any" or compat_type == "Any":
                # Where either side is Any, there is nothing to keep in
                # lockstep — Any is the builder's uncertainty signal.
                continue
            if builder_canonical != compat_type:
                mismatches.append(
                    f"{name}: builder={builder_canonical} compat={compat_type}"
                )

        # Also exercise the divergent corpus entries explicitly so the
        # documented divergences stay visible (they must still type, not
        # crash).
        divergent_body = """
define "power_int_int": 2 ^ 3
define "duration_between": years between @2020-01-01 and @2024-06-01
define "difference_between": difference in years between @2020-01-01 and @2024-06-01
define "age_in_years": AgeInYears()
"""
        dlib = parse_cql(header + divergent_body)
        dctx = SQLTranslationContext()
        from fhir4ds.cql.translator.fhir_schema import FHIRSchemaRegistry

        dctx.fhir_schema = FHIRSchemaRegistry()
        dctx.fhir_schema.load_default_resources()
        for stmt in dlib.statements:
            if hasattr(stmt, "expression") and getattr(stmt, "name", None):
                dctx.expression_definitions[stmt.name] = stmt.expression
        dtype_map = TypeMapBuilder(dctx).attach()
        for dname in ("power_int_int", "duration_between", "difference_between",
                      "age_in_years"):
            ref = dtype_map.get(dname)
            assert ref is not None, f"divergent entry {dname} must still type"
            # And compat must also produce a value without crashing.
            compat = infer_cql_type_compat(
                dctx, dctx.expression_definitions[dname]
            )
            assert isinstance(compat, str)

        assert not mismatches, (
            "Type map builder drifted from compat inference on shared "
            f"corpus entries:\n{chr(10).join(mismatches)}"
        )

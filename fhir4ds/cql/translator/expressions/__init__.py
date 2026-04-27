"""
Expression translation for CQL to SQL.

This module provides the ExpressionTranslator class that translates
CQL expressions to SQL using the DuckDB FHIRPath UDFs.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, List, Optional, Union

logger = logging.getLogger(__name__)

from ...parser.ast_nodes import (
    AggregateExpression,
    AliasRef,
    AllExpression,
    NamedTypeSpecifier,
    AnyExpression,
    BinaryExpression,
    CaseExpression,
    CaseItem,
    ConditionalExpression,
    DateComponent,
    DateTimeLiteral,
    DifferenceBetween,
    DurationBetween,
    ExistsExpression,
    FirstExpression,
    FunctionRef,
    Identifier,
    IndexerExpression,
    InstanceExpression,
    Interval,
    LastExpression,
    ListExpression,
    Literal,
    MethodInvocation,
    Property,
    QualifiedIdentifier,
    Quantity,
    Query,
    QuerySource,
    SingletonExpression,
    SkipExpression,
    TakeExpression,
    TimeLiteral,
    TupleElement,
    TupleExpression,
    UnaryExpression,
)
from ...translator.context import ExprUsage, RowShape, DefinitionMeta
from ...translator.function_inliner import ParameterPlaceholder
from ...translator.placeholder import RetrievePlaceholder
from ...translator.types import (
    PRECEDENCE,
    SQLAlias,
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLExpression,
    SQLExtract,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLIntervalLiteral,
    SQLJoin,
    SQLLambda,
    SQLLiteral,
    SQLNamedArg,
    SQLNull,
    SQLParameterRef,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLSelect,
    SQLSubquery,
    SQLUnaryOp,
    SQLUnion,
    SQLIntersect,
    SQLExcept,
)

from ...translator.component_codes import get_code_to_column_mapping
from ...translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_where_return_expr,
    FHIRPathBuilder,
)

from ...translator.expressions._utils import (
    BINARY_OPERATOR_MAP,
    UNARY_OPERATOR_MAP,
    _is_list_returning_sql,
    _contains_sql_subquery,
    _ensure_scalar_body,
    _get_qicore_extension_fhirpath,
    _resolve_library_code_constant,
)
from ...translator.expressions._temporal import TemporalMixin
from ...translator.expressions._query import QueryMixin
from ...translator.expressions._core import CoreMixin
from ...translator.expressions._property import PropertyMixin
from ...translator.expressions._functions import FunctionsMixin
from ...translator.expressions._operators import OperatorsMixin
from ...translator.expressions._lists import ListsMixin

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

COMPONENT_CODE_TO_COLUMN = get_code_to_column_mapping()

class ExpressionTranslator(
    TemporalMixin, QueryMixin, OperatorsMixin,
    FunctionsMixin, PropertyMixin, CoreMixin, ListsMixin,
):
    """
    Translates CQL expressions to SQL.

    Handles translation of CQL AST nodes to SQL expression objects
    using DuckDB FHIRPath UDFs for FHIR resource navigation.

    Key patterns:
    - Property access: Patient.name -> fhirpath_text($patient_resource, 'name')
    - Choice types: Use COALESCE for effective[x], value[x], onset[x]
    - Boolean context: Use fhirpath_bool() when result goes to WHERE clause
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the expression translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context
        self._function_registry = self._build_function_registry()

    def _build_function_registry(self):
        """Build the FunctionTranslationRegistry with all built-in CQL functions."""
        from ...translator.function_registry import FunctionTranslationRegistry
        registry = FunctionTranslationRegistry()

        # === Simple renames: CQL name → DuckDB name, args passed through ===
        _RENAMES = {
            "length": "LENGTH",
            "upper": "UPPER",
            "lower": "LOWER",
            "replace": "REPLACE",
            "split": "STR_SPLIT",
            "abs": "ABS",
            "ceiling": "CEIL",
            "floor": "FLOOR",
            "sqrt": "SQRT",
            "exp": "mathExp",
            "nullif": "NULLIF",
            "median": "MEDIAN",
            "mode": "MODE",
            "variance": "VARIANCE",
            "stddev": "STDDEV",
            "populationvariance": "VAR_POP",
            "populationstddev": "STDDEV_POP",
            "stddevpop": "STDDEV_POP",
            "distinct": "list_distinct",
        }
        for cql, sql in _RENAMES.items():
            registry.register_rename(cql, sql)

        # Precision needs special handling to preserve trailing zeros in Decimal
        # literals (CQL §22.24).  When the argument is a Decimal literal with
        # raw_str, pass the raw string so the UDF counts actual fractional digits.
        # The pre_translate intercepts Decimal literals; the rename provides the
        # fallback for all other types (DateTime, Time, etc.).
        registry.register_pre_translate("precision", self._translate_precision_pre)
        registry.register_rename("precision", "CQLPrecision")

        # === SQL keywords that must not have parentheses ===
        from ...translator.types import SQLRaw
        registry.register("today", lambda args, ctx: SQLRaw(raw_sql="CAST(CURRENT_DATE AS VARCHAR)"), arity=0)
        registry.register("now", lambda args, ctx: SQLRaw(raw_sql="REPLACE(CAST(CURRENT_TIMESTAMP AS VARCHAR), ' ', 'T')"), arity=0)
        registry.register("timeofday", lambda args, ctx: SQLRaw(raw_sql="CURRENT_TIME"), arity=0)

        # === Parameterized translations: need arg manipulation ===

        # Type conversions
        registry.register("toboolean", lambda args, ctx: self._translate_type_conversion("toboolean", args))
        registry.register("tostring", lambda args, ctx: self._translate_type_conversion("tostring", args))
        registry.register("tointeger", lambda args, ctx: self._translate_type_conversion("tointeger", args))
        registry.register("todecimal", lambda args, ctx: self._translate_type_conversion("todecimal", args))
        registry.register("todate", lambda args, ctx: self._translate_type_conversion("todate", args))
        registry.register("todatetime", lambda args, ctx: self._translate_type_conversion("todatetime", args))
        registry.register("totime", lambda args, ctx: self._translate_type_conversion("totime", args))

        # String functions
        registry.register("substring", lambda args, ctx: self._translate_substring(args))
        registry.register("startswith", lambda args, ctx: self._translate_startswith(args))
        registry.register("endswith", lambda args, ctx: self._translate_endswith(args))
        registry.register("contains", lambda args, ctx: self._translate_contains_func(args))
        registry.register("positionof", lambda args, ctx: self._translate_positionof(args))
        registry.register("lastpositionof", lambda args, ctx: self._translate_lastpositionof(args))

        # Math functions
        registry.register("log", lambda args, ctx: self._translate_log(args))
        registry.register("ln", lambda args, ctx: self._translate_ln(args))
        registry.register("power", lambda args, ctx: self._translate_power(args))

        # Scalar min/max (2-arg: LEAST/GREATEST — only after aggregate pre-check)
        registry.register("min", lambda args, ctx: self._translate_scalar_min(args))
        registry.register("max", lambda args, ctx: self._translate_scalar_max(args))

        # Statistical aggregates (non-query path: simple name map)
        registry.register("sum", lambda args, ctx: self._translate_simple_aggregate("SUM", args))
        registry.register("avg", lambda args, ctx: self._translate_simple_aggregate("AVG", args))

        # Coalesce, Count, Exists
        registry.register("coalesce", lambda args, ctx: self._translate_coalesce(args))
        registry.register("count", lambda args, ctx: self._translate_count(args))
        registry.register("exists", lambda args, ctx: self._translate_exists_func(args))
        registry.register("not exists", lambda args, ctx: self._translate_not_exists_func(args))

        # List functions
        registry.register("first", lambda args, ctx: self._translate_first(args))
        registry.register("last", lambda args, ctx: self._translate_last(args))
        registry.register("singletonfrom", lambda args, ctx: self._translate_singletonfrom(args))

        # Misc
        registry.register("message", lambda args, ctx: self._translate_message(args))
        registry.register("quantity", lambda args, ctx: self._translate_quantity_constructor(args))
        # CQL IndexOf → CQLIndexOf macro (avoids C++ FHIRPath extension conflict)
        registry.register_rename("indexof", "CQLIndexOf")

        # Maximum/Minimum need raw CQL AST to extract type name
        registry.register_pre_translate("maximum", self._translate_maximum_pre)
        registry.register_pre_translate("minimum", self._translate_minimum_pre)

        # Date/time constructors
        registry.register("datetime", lambda args, ctx: self._translate_datetime_constructor(args))
        registry.register("date", lambda args, ctx: self._translate_date_constructor(args))
        registry.register("time", lambda args, ctx: self._translate_time_constructor(args))

        # Duration functions
        for dur_name in ("yearsbetween", "monthsbetween", "weeksbetween", "daysbetween",
                         "hoursbetween", "minutesbetween", "secondsbetween", "millisecondsbetween"):
            _n = dur_name
            registry.register(_n, lambda args, ctx, n=_n: self._translate_duration_between_func(n, args))
        for diff_name in ("differenceinyears", "differenceinmonths", "differenceindays",
                          "differenceinhours", "differenceinminutes", "differenceinseconds"):
            _n = diff_name
            registry.register(_n, lambda args, ctx, n=_n: self._translate_difference_between_func(n, args))

        # Age functions (no reference date) — arity=None covers 0 or 1 args
        for func_name in ("age", "ageinyears", "ageinmonths", "ageindays",
                          "ageinhours", "ageinminutes", "ageinseconds"):
            _name = func_name
            registry.register(
                _name,
                lambda args, ctx, n=_name: self._translate_age_function(n, args),
            )
        # AgeAt (with reference date)
        for func_name in ("ageinyearsat", "ageinmonthsat", "ageindaysat"):
            _name = func_name
            registry.register(
                _name,
                lambda args, ctx, n=_name: self._translate_age_at_function(n, args),
            )

        # === Pre-translate strategies: need raw CQL AST (aggregates on queries) ===
        for agg_name in ("anytrue", "alltrue", "anyfalse", "allfalse",
                         "min", "max", "sum", "avg", "count",
                         "median", "mode", "stddev", "variance",
                         "populationstddev", "populationvariance",
                         "stddevpop"):
            registry.register_pre_translate(
                agg_name,
                self._translate_aggregate_pre,
            )

        return registry

    def _is_forward_ref_boolean(self, name: str, _visited: set | None = None) -> bool:
        """Check if a forward-referenced definition produces a boolean result.

        Uses the pre-populated CQL ASTs to inspect the expression type.
        Boolean definitions produce CTEs with only ``patient_id`` (no value
        or resource column), so references must use EXISTS rather than
        ``SELECT value``.
        """
        if _visited is None:
            _visited = set()
        if name in _visited:
            return False
        _visited.add(name)
        cql_asts = getattr(self.context, '_definition_cql_asts', {})
        cql_ast = cql_asts.get(name)
        if cql_ast is None:
            return False
        from ...parser.ast_nodes import (
            ExistsExpression, BinaryExpression, UnaryExpression,
            Identifier as CQLIdentifier,
        )
        if isinstance(cql_ast, ExistsExpression):
            return True
        if isinstance(cql_ast, UnaryExpression):
            op = getattr(cql_ast, 'operator', '').lower()
            if op in ('not', 'is null', 'is not null', 'is true', 'is false'):
                return True
        if isinstance(cql_ast, BinaryExpression):
            op = getattr(cql_ast, 'operator', '').lower()
            if op in ('=', '!=', '<>', '<', '>', '<=', '>=',
                      'and', 'or', 'xor', 'implies',
                      'on or before', 'on or after', 'before', 'after',
                      'starts', 'ends', 'during', 'overlaps', 'in',
                      '~', '!~', 'equivalent', 'not equivalent',
                      'same or before', 'same or after',
                      'includes', 'included in',
                      'properly includes', 'properly included in',
                      'meets', 'meets before', 'meets after',
                      'contains'):
                return True
            # Precision-qualified same operators: "same or before month of",
            # "same month or before", "same day as", etc.
            if op.startswith('same '):
                return True
        # Identifier reference: follow the chain
        if isinstance(cql_ast, CQLIdentifier):
            return self._is_forward_ref_boolean(cql_ast.name, _visited)
        return False

    def _get_definition_value_column(self, name: str, _visited: set | None = None) -> str:
        """Determine correct value column for a definition CTE reference.

        Uses definition_meta if available, otherwise checks CQL ASTs
        for forward references (definitions not yet translated).
        """
        if _visited is None:
            _visited = set()
        if name in _visited:
            return "resource"
        _visited.add(name)
        meta = self.context.definition_meta.get(name)
        if meta:
            if meta.has_resource:
                return "resource"
            return meta.value_column
        # Forward reference: check CQL AST for return clause
        cql_asts = getattr(self.context, '_definition_cql_asts', {})
        cql_ast = cql_asts.get(name)
        if cql_ast is not None:
            from ...parser.ast_nodes import (
                Query as CQLQuery, FunctionRef, Retrieve, Identifier as CQLIdentifier,
                BinaryExpression as CQLBinaryExpr,
            )
            # Direct Query with return clause
            if isinstance(cql_ast, CQLQuery) and cql_ast.return_clause is not None:
                return "value"
            # FunctionRef (First/Last) wrapping a Query with return clause
            if isinstance(cql_ast, FunctionRef):
                fn = getattr(cql_ast, 'name', '')
                if fn in ('First', 'Last'):
                    args = getattr(cql_ast, 'arguments', []) or []
                    if args and isinstance(args[0], CQLQuery):
                        outer_q = args[0]
                        # Direct return clause on the query
                        if outer_q.return_clause is not None:
                            return "value"
                        # Return clause on the inner query (source of outer)
                        inner_src = outer_q.source
                        if isinstance(inner_src, list) and len(inner_src) == 1:
                            inner_src = inner_src[0]
                        if hasattr(inner_src, 'expression') and isinstance(inner_src.expression, CQLQuery):
                            if inner_src.expression.return_clause is not None:
                                return "value"
                # Scalar constructor functions produce value column
                if fn.lower() in ('datetime', 'date', 'time', 'now', 'today',
                                  'tointeger', 'todecimal', 'tostring', 'toboolean',
                                  'todate', 'todatetime', 'totime', 'toquantity'):
                    return "value"
            # Identifier reference to another definition — follow the chain
            # to inherit the target's column (e.g., "Denominator" = "IP")
            if isinstance(cql_ast, CQLIdentifier):
                return self._get_definition_value_column(cql_ast.name, _visited)
            # Union/intersect/except of definitions — inherit RESOURCE_ROWS
            if isinstance(cql_ast, CQLBinaryExpr):
                op = getattr(cql_ast, 'operator', '').lower()
                if op in ('union', 'intersect', 'except'):
                    return "resource"
            # Non-retrieve expressions (scalars, booleans) use value column
            if not isinstance(cql_ast, (Retrieve, CQLQuery)):
                return "value"
        # Also check expression_definitions for forward references
        if hasattr(self.context, 'expression_definitions') and name in self.context.expression_definitions:
            ast_def = self.context.expression_definitions[name]
            expr_ast = ast_def.expression if hasattr(ast_def, 'expression') else None
            if expr_ast is not None:
                from ...parser.ast_nodes import Retrieve as _Retrieve, Query as _Query
                if not isinstance(expr_ast, (_Retrieve, _Query)):
                    return "value"
        return "resource"

    def _trace_source_column(self, name: str, _visited: set | None = None) -> str:
        """Trace through Query sources to determine if a definition produces resources.

        For definitions that are Queries without return clauses, the output
        column is inherited from the source. This traces the chain.
        """
        if _visited is None:
            _visited = set()
        if name in _visited:
            return "value"
        _visited.add(name)

        from ...parser.ast_nodes import (
            Query as CQLQuery, Retrieve, Identifier as CQLIdentifier,
            QuerySource, Property, QualifiedIdentifier, BinaryExpression,
        )

        # Check CQL AST
        cql_asts = getattr(self.context, '_definition_cql_asts', {})
        cql_ast = cql_asts.get(name)
        if cql_ast is None:
            expr_defs = getattr(self.context, 'expression_definitions', {})
            ast_def = expr_defs.get(name)
            if ast_def is not None:
                cql_ast = ast_def.expression if hasattr(ast_def, 'expression') else ast_def

        if cql_ast is None:
            return "value"

        # Retrieve always produces resource
        if isinstance(cql_ast, Retrieve):
            return "resource"

        # Identifier → follow the chain
        if isinstance(cql_ast, CQLIdentifier):
            ref_meta = self.context.definition_meta.get(cql_ast.name)
            if ref_meta and ref_meta.has_resource:
                return "resource"
            return self._trace_source_column(cql_ast.name, _visited)

        # Union/intersect/except → resource if either side is resource
        if isinstance(cql_ast, BinaryExpression):
            op = getattr(cql_ast, 'operator', '').lower()
            if op in ('union', 'intersect', 'except'):
                return "resource"

        # Query without return clause → trace source
        if isinstance(cql_ast, CQLQuery) and cql_ast.return_clause is None:
            src = cql_ast.source
            if isinstance(src, list):
                src = src[0] if src else None
            if isinstance(src, QuerySource):
                src = src.expression
            if src is None:
                return "value"
            # Source is an Identifier referencing another definition
            if isinstance(src, CQLIdentifier):
                ref_meta = self.context.definition_meta.get(src.name)
                if ref_meta and ref_meta.has_resource:
                    return "resource"
                return self._trace_source_column(src.name, _visited)
            # Source is a Retrieve
            if isinstance(src, Retrieve):
                return "resource"
            # Source is a qualified reference (e.g., CQMCommon."Inpatient Encounter")
            if isinstance(src, Property) and isinstance(src.source, CQLIdentifier):
                prefixed = f"{src.source.name}.{src.path}"
                ref_meta = self.context.definition_meta.get(prefixed)
                if ref_meta and ref_meta.has_resource:
                    return "resource"
                return self._trace_source_column(prefixed, _visited)
            if isinstance(src, QualifiedIdentifier) and src.parts:
                prefixed = ".".join(src.parts)
                ref_meta = self.context.definition_meta.get(prefixed)
                if ref_meta and ref_meta.has_resource:
                    return "resource"
                return self._trace_source_column(prefixed, _visited)

        # Query WITH return clause that returns a source alias → trace that source
        if isinstance(cql_ast, CQLQuery) and cql_ast.return_clause is not None:
            ret_expr = cql_ast.return_clause.expression
            if isinstance(ret_expr, CQLIdentifier):
                # Return clause is an alias reference (e.g., "return Encounter48Hours")
                # Find which source this alias refers to and trace it
                sources = cql_ast.source
                if not isinstance(sources, list):
                    sources = [sources]
                for src_item in sources:
                    if isinstance(src_item, QuerySource) and src_item.alias == ret_expr.name:
                        src_expr = src_item.expression
                        if isinstance(src_expr, Retrieve):
                            return "resource"
                        if isinstance(src_expr, CQLIdentifier):
                            ref_meta = self.context.definition_meta.get(src_expr.name)
                            if ref_meta and ref_meta.has_resource:
                                return "resource"
                            return self._trace_source_column(src_expr.name, _visited)
                        if isinstance(src_expr, Property) and isinstance(src_expr.source, CQLIdentifier):
                            prefixed = f"{src_expr.source.name}.{src_expr.path}"
                            ref_meta = self.context.definition_meta.get(prefixed)
                            if ref_meta and ref_meta.has_resource:
                                return "resource"
                            return self._trace_source_column(prefixed, _visited)

        return "value"

    def translate(
        self,
        expr: Any,
        usage: ExprUsage = ExprUsage.LIST,
        *,
        boolean_context: bool = False,
        list_context: bool = False,
    ) -> SQLExpression:
        """
        Translate a CQL expression to SQL.

        Args:
            expr: The CQL AST expression to translate.
            usage: How the expression result will be used.
                - LIST: Return a collection (default CQL semantics)
                - SCALAR: Return a single value (for property access, comparisons)
                - BOOLEAN: Truth test (for WHERE, AND, OR, NOT)
                - EXISTS: Existence check (for exists() function)
            boolean_context: (Deprecated) If True, treat as BOOLEAN usage.
            list_context: (Deprecated) If True, treat as LIST usage.

        Returns:
            SQL expression appropriate for the given usage context.
        """
        # For backward compatibility, convert old boolean_context/list_context to usage
        # This allows gradual migration of callers
        # Note: This will be removed after all callers are updated
        if boolean_context:
            usage = ExprUsage.BOOLEAN
        elif list_context:
            usage = ExprUsage.LIST

        if expr is None:
            return SQLNull()

        # Dispatch based on expression type
        expr_type = type(expr).__name__

        handler = getattr(self, f"_translate_{self._camel_to_snake(expr_type)}", None)
        if handler:
            # Check if handler accepts 'usage' or 'boolean_context' parameter.
            # Use __code__.co_varnames instead of inspect.signature to avoid
            # expensive introspection that can trigger RecursionError at deep stacks.
            func_obj = getattr(handler, "__func__", handler)
            code = getattr(func_obj, "__code__", None)
            if code is not None:
                co_vars = code.co_varnames[:code.co_argcount]
            else:
                co_vars = ()

            if 'usage' in co_vars:
                # Handler accepts usage directly
                result = handler(expr, usage)
            elif 'boolean_context' in co_vars:
                # Legacy handler - convert usage to boolean_context
                _boolean_context = usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS)
                result = handler(expr, _boolean_context)
            else:
                # Handler doesn't take context parameter
                result = handler(expr)

            # Wrap bare SQLSelect in SQLSubquery for safe use as an expression.
            # SQLSelect renders without parens; SQLSubquery adds them.
            # The CTE builder in translator.py unwraps SQLSubquery→SQLSelect
            # when it needs the bare SELECT as a CTE body.
            if isinstance(result, SQLSelect):
                result = SQLSubquery(query=result)

            return result

        # Fallback for unknown types
        raise ValueError(f"Unknown expression type: {expr_type}")



__all__ = [
    "ExpressionTranslator",
    "BINARY_OPERATOR_MAP",
    "UNARY_OPERATOR_MAP",
]

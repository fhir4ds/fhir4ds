"""Function reference translation: built-in CQL functions and aggregation."""
from __future__ import annotations

import json
import logging
import re as _re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from ...parser.ast_nodes import (
    AggregateExpression,
    AliasRef,
    AllExpression,
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
    NamedTypeSpecifier,
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
from ...translator.expressions._utils import (
    BINARY_OPERATOR_MAP,
    UNARY_OPERATOR_MAP,
    _is_list_returning_sql,
    _contains_sql_subquery,
    _ensure_scalar_body,
    _get_qicore_extension_fhirpath,
    _resolve_library_code_constant,
)
from ...translator.expressions._operators import _is_patient_id_correlation

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

logger = logging.getLogger(__name__)

from ...translator.component_codes import get_code_to_column_mapping
from ...translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_where_return_expr,
    FHIRPathBuilder,
)

class FunctionsMixin:
    """Mixin providing function reference, exists, and age translations."""

    def _wrap_list_aggregate(
        self, agg_func: str, source_sql: SQLExpression
    ) -> Optional[SQLExpression]:
        """Wrap a LIST-translated SQL expression with an aggregate function.

        Returns an SQLSubquery containing ``SELECT agg_func(col) FROM (source)``,
        or ``None`` if the source shape cannot be wrapped.
        """
        inner_query = source_sql
        if isinstance(inner_query, SQLSubquery):
            inner_query = inner_query.query
        if isinstance(inner_query, SQLSelect):
            # Alias the first column so we can reference it in the aggregate
            if inner_query.columns:
                first_col = inner_query.columns[0]
                if not isinstance(first_col, SQLAlias):
                    inner_query.columns[0] = SQLAlias(expr=first_col, alias="_val")
                    col_ref = SQLIdentifier(name="_val")
                else:
                    col_ref = SQLIdentifier(name=first_col.alias)
            else:
                col_ref = SQLIdentifier(name="_val")

            # Inject patient correlation when the inner query sources from a
            # CTE (which contains all patients' rows) and we are inside a
            # patient-scoped context.
            _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
            _src_alias = None
            _fc = inner_query.from_clause
            if isinstance(_fc, SQLAlias):
                _src_alias = _fc.alias
            if _src_alias:
                _corr = SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=[_src_alias, "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                )
                _existing_where = inner_query.where
                _new_where = (
                    SQLBinaryOp(operator="AND", left=_existing_where, right=_corr)
                    if _existing_where else _corr
                )
                inner_query = SQLSelect(
                    columns=inner_query.columns,
                    from_clause=inner_query.from_clause,
                    where=_new_where,
                    joins=inner_query.joins,
                    group_by=inner_query.group_by,
                    having=inner_query.having,
                    order_by=inner_query.order_by,
                    limit=inner_query.limit,
                    distinct=inner_query.distinct,
                )

            result = SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(name=agg_func, args=[col_ref])],
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=inner_query),
                    alias="_agg",
                ),
            ))

            # In audit mode, for MIN/MAX, attach _audit_target using arg_min/arg_max
            # to identify the winning resource.
            if (getattr(self.context, 'audit_mode', False)
                    and agg_func in ('MIN', 'MAX')
                    and _src_alias):
                target_subq = self._build_minmax_audit_target(
                    inner_query, _src_alias, agg_func, col_ref,
                )
                if target_subq is not None:
                    result._audit_target = target_subq

            return result
        else:
            # Source translated to a list expression (e.g., list_transform)
            # rather than a row-producing SELECT.  Use DuckDB list aggregate
            # functions to avoid SQL aggregate leaks.
            if not _is_list_returning_sql(source_sql):
                if agg_func in ("bool_or", "bool_and"):
                    return source_sql
                # Not a list and not a SELECT — cannot aggregate safely.
                # Return None so the caller can fall back.
                return None
            _list_agg_map = {
                "SUM": "list_sum", "MIN": "list_min", "MAX": "list_max",
                "AVG": "list_avg", "COUNT": "list_count",
                "bool_or": "list_bool_or", "bool_and": "list_bool_and",
            }
            list_func = _list_agg_map.get(agg_func)
            if list_func:
                return SQLFunctionCall(name=list_func, args=[source_sql])
            # Fallback for less common aggregates: unnest into subquery
            return SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(name=agg_func, args=[SQLIdentifier(name="_val")])],
                from_clause=SQLAlias(
                    expr=SQLFunctionCall(name="unnest", args=[source_sql]),
                    alias="_val",
                ),
            ))

    def _build_minmax_audit_target(
        self,
        inner_query: "SQLSelect",
        src_alias: str,
        agg_func: str,
        col_ref: "SQLIdentifier",
    ) -> "Optional[SQLExpression]":
        """Build an audit target subquery for MIN/MAX using arg_min/arg_max.

        Returns a SQLSubquery that uses ``arg_min(_rid, _val)`` (for MIN) or
        ``arg_max(_rid, _val)`` (for MAX) to identify the winning resource.
        Returns None if the inner query's FROM clause doesn't reference a
        RESOURCE_ROWS CTE with a ``resource`` column.
        """
        # Detect CTE name from the inner query's FROM clause
        from_clause = inner_query.from_clause
        if isinstance(from_clause, SQLAlias):
            from_inner = from_clause.expr
        else:
            from_inner = from_clause
        cte_name = None
        if isinstance(from_inner, SQLIdentifier):
            cte_name = from_inner.name
        elif isinstance(from_inner, SQLRaw):
            cte_name = from_inner.raw_sql.strip().strip('"')
        if not cte_name:
            return None

        # Check definition_meta for resource column
        meta = self.context.definition_meta.get(cte_name)
        if not meta or not getattr(meta, 'has_resource', False):
            return None

        # Build a twin inner query with _rid column for resource ID
        from ._operators import _build_resource_id_expr
        res_col = SQLQualifiedIdentifier(parts=[src_alias, "resource"])
        rid_expr = _build_resource_id_expr(res_col)
        twin_cols = list(inner_query.columns or []) + [
            SQLAlias(expr=rid_expr, alias="_rid"),
        ]
        twin_inner = SQLSelect(
            columns=twin_cols,
            from_clause=inner_query.from_clause,
            where=inner_query.where,
            joins=inner_query.joins,
            group_by=inner_query.group_by,
            having=inner_query.having,
            order_by=inner_query.order_by,
            limit=inner_query.limit,
            distinct=inner_query.distinct,
        )

        # Use arg_min for MIN, arg_max for MAX
        arg_func = "arg_min" if agg_func == "MIN" else "arg_max"
        rid_ref = SQLIdentifier(name="_rid")
        return SQLSubquery(query=SQLSelect(
            columns=[SQLFunctionCall(name=arg_func, args=[rid_ref, col_ref])],
            from_clause=SQLAlias(
                expr=SQLSubquery(query=twin_inner),
                alias="_agg",
            ),
        ))

    @staticmethod
    def _extract_innermost_query(node: Any) -> Optional[Any]:
        """Walk through wrapper Query nodes to find the one with a real WHERE.

        CQL ``(from X where Y).prop`` parses as
        ``Property(source=Query(source=QuerySource(expr=Query(source=..., where=...))))``.
        This method traverses the wrapper layers and returns the innermost
        Query that actually carries a ``where`` clause or a named alias.
        """
        from ...parser.ast_nodes import Query as CQLQuery, QuerySource
        cur = node
        while isinstance(cur, CQLQuery):
            # If this query has a WHERE or named alias, it's the real one.
            if getattr(cur, 'where', None) is not None:
                return cur
            if cur.source and getattr(cur.source, 'alias', None):
                return cur
            # Otherwise, descend into the source's expression.
            if cur.source and isinstance(cur.source, QuerySource):
                inner = cur.source.expression
                if isinstance(inner, CQLQuery):
                    cur = inner
                    continue
            break
        return cur if isinstance(cur, CQLQuery) else None

    def _build_property_aggregate(
        self,
        agg_func: str,
        inner_sql: SQLExpression,
        prop_path: str,
    ) -> Optional[SQLExpression]:
        """Build ``SELECT agg(json_extract_string(resource, '$.prop')) FROM (inner)``."""
        inner_query = inner_sql
        if isinstance(inner_query, SQLSubquery):
            inner_query = inner_query.query
        if not isinstance(inner_query, SQLSelect):
            return None

        # Determine the source alias used in the inner query's FROM clause.
        _src_alias = None
        _fc = inner_query.from_clause
        if isinstance(_fc, SQLAlias):
            _src_alias = _fc.alias

        # Build the property extraction column.
        res_ref = (
            SQLQualifiedIdentifier(parts=[_src_alias, "resource"])
            if _src_alias
            else SQLIdentifier(name="resource")
        )
        prop_col = SQLFunctionCall(
            name="json_extract_string",
            args=[res_ref, SQLLiteral(value=f"$.{prop_path}")],
        )
        prop_select = SQLSelect(
            columns=[SQLAlias(expr=prop_col, alias="_val")],
            from_clause=inner_query.from_clause,
            where=inner_query.where,
            joins=inner_query.joins,
            group_by=inner_query.group_by,
            having=inner_query.having,
            order_by=inner_query.order_by,
            limit=inner_query.limit,
            distinct=inner_query.distinct,
        )

        # Inject patient correlation.
        _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
        if _src_alias:
            _corr = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=[_src_alias, "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
            )
            existing_where = prop_select.where
            new_where = (
                SQLBinaryOp(operator="AND", left=existing_where, right=_corr)
                if existing_where else _corr
            )
            prop_select = SQLSelect(
                columns=prop_select.columns,
                from_clause=prop_select.from_clause,
                where=new_where,
                joins=prop_select.joins,
                group_by=prop_select.group_by,
                having=prop_select.having,
                order_by=prop_select.order_by,
                limit=prop_select.limit,
                distinct=prop_select.distinct,
            )

        col_ref = SQLIdentifier(name="_val")
        return SQLSubquery(query=SQLSelect(
            columns=[SQLFunctionCall(name=agg_func, args=[col_ref])],
            from_clause=SQLAlias(
                expr=SQLSubquery(query=prop_select),
                alias="_agg",
            ),
        ))

    def _translate_function_ref(self, func: FunctionRef, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL function call to SQL via the function registry."""
        from ...translator.function_registry import (
            SimpleRename, ParameterizedTranslation, PreTranslateStrategy,
        )
        name = func.name
        arity = len(func.arguments) if func.arguments else 0

        # Special handling for First/Last with Query args — must check BEFORE
        # translating args so we can use window functions for deterministic ordering
        if name.lower() in ("first", "last") and func.arguments:
            from ...parser.ast_nodes import Query
            arg = func.arguments[0]
            if isinstance(arg, Query):
                direction = "ASC" if name.lower() == "first" else "DESC"
                return self._translate_first_last_with_window(arg, direction=direction)

        # Step 1: Check for pre-translate strategies (aggregates on Queries, maximum/minimum)
        pre_strategy = self._function_registry.get_pre_translate(name, arity)
        if pre_strategy is not None:
            result = pre_strategy.translator(func, self)
            if result is not None:
                return result
            # Fall through if pre-translate returns None (not applicable)

        # Step 2: Translate arguments
        args = [self.translate(arg, usage=ExprUsage.SCALAR) for arg in func.arguments]

        # Step 3: Check registry for simple renames and parameterized translations
        strategy = self._function_registry.get(name, arity)
        if isinstance(strategy, SimpleRename):
            return SQLFunctionCall(name=strategy.sql_name, args=args)
        if isinstance(strategy, ParameterizedTranslation):
            return strategy.translator(args, self.context)

        # Step 4: Non-fluent library-qualified functions with fluent AST builders
        _NONFLUENT_TO_FLUENT = {"ToPrevalenceInterval": "prevalenceInterval"}
        bare_name = name.rsplit(".", 1)[-1] if "." in name else name
        fluent_name = _NONFLUENT_TO_FLUENT.get(bare_name)
        if fluent_name and func.arguments:
            fluent_translator = self.context.fluent_translator
            if fluent_translator:
                resource_arg = self.translate(func.arguments[0])
                extra_args = [self.translate(a) for a in func.arguments[1:]]
                arg_resource_type = self._infer_resource_type(func.arguments[0])
                try:
                    return fluent_translator.translate_fluent_call(
                        resource_expr=resource_arg,
                        function_name=fluent_name,
                        args=extra_args,
                        context=self.context,
                        resource_type=arg_resource_type,
                    )
                except NotImplementedError:
                    pass

        # Step 5: Try function inliner for library-defined functions
        inliner = self.context.function_inliner
        if inliner:
            expanded_cql = inliner.expand_function(name, None, func.arguments)
            if expanded_cql is not None:
                return self.translate(expanded_cql)

        # Step 6: Collapse/Expand (need access to both raw CQL and translated args)
        if name.lower() == "collapse" and args:
            return self._translate_collapse(args)
        if name.lower() == "expand" and func.arguments:
            result = self._translate_expand(func)
            if result is not None:
                return result

        # Step 6.5: FHIRCommon ext(element, url) → fhirpath_text(element, "extension.where(url='URL')")
        if bare_name == "ext" and len(args) == 2:
            url_arg = args[1]
            url_val = getattr(url_arg, 'value', None) if hasattr(url_arg, 'value') else None
            if url_val and isinstance(url_val, str):
                fhirpath_expr = f"extension.where(url='{url_val}')"
                return SQLFunctionCall(
                    name="fhirpath_text",
                    args=[args[0], SQLLiteral(fhirpath_expr)],
                )

        # Step 7: Fallback — pass through as function call
        logger.debug("Unknown function '%s' — passing through to SQL", name)
        return SQLFunctionCall(name=name, args=args)

    # ── Aggregate pre-translate strategy ──────────────────────────────────
    def _translate_aggregate_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate strategy for CQL aggregate functions on Query sources.

        Returns a SQL expression if the aggregate applies to a Query/FunctionRef/
        Property-on-Query, or None to fall through to standard arg translation.
        """
        _CQL_AGG_TO_SQL = {
            "anytrue": "bool_or",
            "alltrue": "bool_and",
            "min": "MIN",
            "max": "MAX",
            "sum": "SUM",
            "avg": "AVG",
            "count": "COUNT",
            "median": "MEDIAN",
            "mode": "MODE",
            "stddev": "STDDEV_SAMP",
            "variance": "VAR_SAMP",
            "populationstddev": "STDDEV_POP",
            "populationvariance": "VAR_POP",
        }
        name = func.name
        if not func.arguments:
            return None
        agg_func = _CQL_AGG_TO_SQL.get(name.lower())
        if agg_func is None:
            return None

        from ...parser.ast_nodes import Query as CQLQuery, ListExpression, Retrieve
        arg = func.arguments[0]

        # Retrieve sources (e.g. Count([Encounter])) need a correlated subquery
        # because the Retrieve translates to a RetrievePlaceholder that Phase 3
        # resolves to a CTE reference.  _wrap_list_aggregate cannot handle
        # placeholders, so we build the subquery directly.
        if isinstance(arg, Retrieve):
            placeholder = self.translate(arg, usage=ExprUsage.LIST)
            agg_col = (
                SQLFunctionCall(name=agg_func, args=[SQLIdentifier(name="*")])
                if agg_func == "COUNT"
                else SQLFunctionCall(name=agg_func, args=[SQLQualifiedIdentifier(parts=["_agg_src", "resource"])])
            )
            _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
            correlated = SQLSubquery(query=SQLSelect(
                columns=[agg_col],
                from_clause=SQLAlias(expr=placeholder, alias="_agg_src"),
                where=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_agg_src", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                ),
            ))
            return correlated

        if isinstance(arg, CQLQuery):
            source_sql = self.translate(arg, usage=ExprUsage.LIST)
            result = self._wrap_list_aggregate(agg_func, source_sql)
            if result is not None:
                return result
        # FunctionRef that expands to a Query
        if isinstance(arg, FunctionRef):
            source_sql = self.translate(arg, usage=ExprUsage.LIST)
            result = self._wrap_list_aggregate(agg_func, source_sql)
            if result is not None:
                return result
        # Property-on-Query: Min((from X where Y).prop)
        if (
            name.lower() in ("min", "max", "sum", "avg", "count")
            and self._arg_involves_query(arg)
            and isinstance(arg, Property)
        ):
            inner_query_node = self._extract_innermost_query(arg.source)
            if inner_query_node is not None:
                inner_sql = self.translate(inner_query_node, usage=ExprUsage.LIST)
                result = self._build_property_aggregate(agg_func, inner_sql, arg.path)
                if result is not None:
                    return result
            scalar = self.translate(arg, usage=ExprUsage.SCALAR)
            return SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(name=agg_func, args=[scalar])],
            ))
        # AnyTrue/AllTrue with non-query source
        if name.lower() in ("anytrue", "alltrue"):
            scalar = self.translate(arg, usage=ExprUsage.SCALAR)
            return scalar
        # Min/Max on list literals
        if name.lower() in ("min", "max") and isinstance(arg, ListExpression):
            source_sql = self.translate(arg, usage=ExprUsage.SCALAR)
            if isinstance(source_sql, SQLArray):
                list_func = "list_min" if name.lower() == "min" else "list_max"
                return SQLFunctionCall(name=list_func, args=[source_sql])

        # Count/Sum/Avg on list literals — use DuckDB list functions
        if isinstance(arg, ListExpression):
            source_sql = self.translate(arg, usage=ExprUsage.SCALAR)
            if isinstance(source_sql, SQLArray):
                if name.lower() == "count":
                    return SQLFunctionCall(name="len", args=[source_sql])
                _list_agg = {"sum": "sum", "avg": "avg", "median": "median",
                             "mode": "mode"}.get(name.lower())
                if _list_agg:
                    return SQLFunctionCall(
                        name="list_aggregate",
                        args=[source_sql, SQLLiteral(value=_list_agg)],
                    )

        return None  # Fall through to standard translation

    # ── Parameterized function handlers ───────────────────────────────────

    def _translate_coalesce(self, args: list) -> SQLExpression:
        """Translate CQL Coalesce with type compatibility handling."""
        has_date_cast = any(
            isinstance(a, SQLCast) and a.target_type == "DATE" for a in args
        )
        has_non_date = any(
            not (isinstance(a, SQLCast) and a.target_type == "DATE") for a in args
        )
        if has_date_cast and has_non_date:
            args = [
                a.expression if (isinstance(a, SQLCast) and a.target_type == "DATE") else a
                for a in args
            ]

        def _is_numeric_expr(a):
            if isinstance(a, SQLCast) and a.target_type == "DOUBLE":
                return True
            if isinstance(a, SQLBinaryOp) and a.operator in ("+", "-", "*", "/"):
                return True
            if isinstance(a, SQLLiteral) and isinstance(a.value, (int, float)):
                return True
            return False

        if any(_is_numeric_expr(a) for a in args):
            def _cast_to_double(a):
                if _is_numeric_expr(a):
                    return a
                if isinstance(a, SQLFunctionCall) and a.name in ('fhirpath_text', 'fhirpath_scalar'):
                    return SQLCast(expression=a, target_type="DOUBLE", try_cast=True)
                return a
            args = [_cast_to_double(a) for a in args]

        return SQLFunctionCall(name="COALESCE", args=args)

    def _translate_count(self, args: list) -> SQLExpression:
        """Translate CQL Count to SQL."""
        if args and isinstance(args[0], SQLFunctionCall) and args[0].name in ('fhirpath_text', 'fhirpath_scalar'):
            return SQLFunctionCall(name="json_array_length", args=args)

        use_distinct = False
        if args and isinstance(args[0], SQLFunctionCall) and args[0].name in ('ARRAY_DISTINCT', 'distinct'):
            args = args[0].args
            use_distinct = True

        if args and not use_distinct:
            inner = args[0]
            if isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect):
                inner_sel = inner.query
                if inner_sel.from_clause:
                    count_select = SQLSelect(
                        columns=[SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])],
                        from_clause=inner_sel.from_clause,
                        joins=inner_sel.joins,
                        where=inner_sel.where,
                    )
                    return SQLSubquery(query=count_select)

        if use_distinct:
            inner = args[0] if args else None
            if isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect):
                inner_sel = inner.query
                if inner_sel.from_clause:
                    count_select = SQLSelect(
                        columns=[SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])],
                        from_clause=SQLSelect(
                            columns=inner_sel.columns if inner_sel.columns else [SQLIdentifier(name="*")],
                            from_clause=inner_sel.from_clause,
                            joins=inner_sel.joins,
                            where=inner_sel.where,
                            distinct=True,
                        ),
                    )
                    return SQLSubquery(query=count_select)
            func_name = "system.main.count"
            return SQLFunctionCall(name=func_name, args=args, distinct=use_distinct)

        return SQLFunctionCall(name="COUNT", args=args, distinct=False)

    def _translate_exists_func(self, args: list) -> SQLExpression:
        """Translate CQL exists() function."""
        if len(args) >= 1:
            return self._translate_exists(args[0], negated=False)
        self.context.warnings.add_semantics(
            message="exists() called without arguments, using FALSE fallback",
            suggestion="Check that the source expression resolves to a valid CTE",
        )
        return SQLLiteral(value=False)

    def _translate_not_exists_func(self, args: list) -> SQLExpression:
        """Translate CQL not exists() function."""
        if len(args) >= 1:
            return self._translate_exists(args[0], negated=True)
        return SQLLiteral(value=False)

    def _translate_substring(self, args: list) -> SQLExpression:
        """Translate CQL Substring (0-indexed) to SQL SUBSTRING (1-indexed)."""
        if len(args) >= 2:
            start_index = SQLBinaryOp(operator="+", left=args[1], right=SQLLiteral(value=1))
            if len(args) >= 3:
                return SQLFunctionCall(name="SUBSTRING", args=[args[0], start_index, args[2]])
            return SQLFunctionCall(name="SUBSTRING", args=[args[0], start_index])
        return args[0] if args else SQLNull()

    def _translate_startswith(self, args: list) -> SQLExpression:
        """Translate CQL StartsWith to SQL LIKE."""
        if len(args) >= 2:
            return SQLBinaryOp(
                operator="LIKE",
                left=args[0],
                right=SQLBinaryOp(
                    operator="||", left=args[1], right=SQLLiteral(value="%"),
                    precedence=PRECEDENCE["||"],
                ),
                precedence=PRECEDENCE["LIKE"],
            )
        return SQLLiteral(value=False)

    def _translate_endswith(self, args: list) -> SQLExpression:
        """Translate CQL EndsWith to SQL LIKE."""
        if len(args) >= 2:
            return SQLBinaryOp(
                operator="LIKE",
                left=args[0],
                right=SQLBinaryOp(
                    operator="||", left=SQLLiteral(value="%"), right=args[1],
                    precedence=PRECEDENCE["||"],
                ),
                precedence=PRECEDENCE["LIKE"],
            )
        return SQLLiteral(value=False)

    def _translate_contains_func(self, args: list) -> SQLExpression:
        """Translate CQL Contains function (string) to SQL strpos."""
        if len(args) >= 2:
            return SQLBinaryOp(
                operator=">",
                left=SQLFunctionCall(name="strpos", args=[args[0], args[1]]),
                right=SQLLiteral(value=0),
            )
        return SQLLiteral(value=False)

    def _translate_positionof(self, args: list) -> SQLExpression:
        """Translate CQL PositionOf (0-based) to DuckDB strpos (1-based)."""
        if len(args) >= 2:
            strpos_result = SQLFunctionCall(name="strpos", args=[args[1], args[0]])
            return SQLCase(
                when_clauses=[(
                    SQLBinaryOp(operator="=", left=strpos_result, right=SQLLiteral(value=0)),
                    SQLLiteral(value=-1),
                )],
                else_clause=SQLBinaryOp(operator="-", left=strpos_result, right=SQLLiteral(value=1)),
            )
        return SQLLiteral(value=-1)

    def _translate_lastpositionof(self, args: list) -> SQLExpression:
        """Translate CQL LastPositionOf (0-based) to DuckDB strrpos (1-based)."""
        if len(args) >= 2:
            strrpos_result = SQLFunctionCall(name="strrpos", args=[args[1], args[0]])
            return SQLCase(
                when_clauses=[(
                    SQLBinaryOp(operator="=", left=strrpos_result, right=SQLLiteral(value=0)),
                    SQLLiteral(value=-1),
                )],
                else_clause=SQLBinaryOp(operator="-", left=strrpos_result, right=SQLLiteral(value=1)),
            )
        return SQLLiteral(value=-1)

    def _translate_log(self, args: list) -> SQLExpression:
        """Translate CQL Log: 2-arg is LOG(base, value), 1-arg is LN."""
        if len(args) >= 2:
            return SQLFunctionCall(name="LOG", args=[args[1], args[0]])
        return SQLFunctionCall(name="LN", args=args)

    def _translate_power(self, args: list) -> SQLExpression:
        """Translate CQL Power to DuckDB POW."""
        return SQLFunctionCall(name="POW", args=args)

    def _translate_scalar_min(self, args: list) -> SQLExpression:
        """Translate CQL scalar Min (2-arg) to DuckDB LEAST."""
        return SQLFunctionCall(name="LEAST", args=args)

    def _translate_scalar_max(self, args: list) -> SQLExpression:
        """Translate CQL scalar Max (2-arg) to DuckDB GREATEST."""
        return SQLFunctionCall(name="GREATEST", args=args)

    def _translate_simple_aggregate(self, sql_name: str, args: list) -> SQLExpression:
        """Translate a simple CQL aggregate (Sum, Avg) to SQL."""
        return SQLFunctionCall(name=sql_name, args=args)

    def _translate_first(self, args: list) -> SQLExpression:
        """Translate CQL First to DuckDB LIST_EXTRACT(list, 1)."""
        if args:
            return SQLFunctionCall(name="LIST_EXTRACT", args=[args[0], SQLLiteral(value=1)])
        return SQLNull()

    def _translate_last(self, args: list) -> SQLExpression:
        """Translate CQL Last to DuckDB LIST_EXTRACT(list, -1)."""
        if args:
            return SQLFunctionCall(name="LIST_EXTRACT", args=[args[0], SQLLiteral(value=-1)])
        return SQLNull()

    def _translate_singletonfrom(self, args: list) -> SQLExpression:
        """Translate CQL SingletonFrom."""
        if args:
            return self._apply_singleton_from(args[0])
        return SQLNull()

    def _translate_message(self, args: list) -> SQLExpression:
        """Translate CQL Message — return the source value."""
        if args:
            return args[0]
        return SQLNull()

    def _translate_quantity_constructor(self, args: list) -> SQLExpression:
        """Translate CQL Quantity(value, unit) constructor."""
        if len(args) >= 2:
            value_arg = args[0]
            unit_arg = args[1]
            if isinstance(value_arg, SQLFunctionCall) and value_arg.name in ('fhirpath_text', 'fhirpath_scalar'):
                value_arg = SQLCast(expression=value_arg, target_type="DOUBLE", try_cast=True)
            return SQLFunctionCall(
                name="parse_quantity",
                args=[SQLFunctionCall(
                    name="json_object",
                    args=[
                        SQLLiteral(value="value"), value_arg,
                        SQLLiteral(value="unit"), unit_arg,
                        SQLLiteral(value="system"), SQLLiteral(value="http://unitsofmeasure.org"),
                    ],
                )],
            )
        return SQLNull()

    def _translate_maximum_func(self, args: list) -> SQLExpression:
        """Translate CQL maximum(Type) — max value for a type (parameterized path)."""
        return SQLNull()

    def _translate_minimum_func(self, args: list) -> SQLExpression:
        """Translate CQL minimum(Type) — min value for a type (parameterized path)."""
        return SQLNull()

    def _translate_maximum_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate CQL maximum(Type) — needs raw CQL AST for type name."""
        _MAX_VALUES = {
            "datetime": "9999-12-31 23:59:59",
            "date": "9999-12-31",
            "time": "23:59:59",
            "integer": 2147483647,
            "decimal": "99999999999999999999.99999999",
        }
        if func.arguments:
            type_arg = func.arguments[0]
            if isinstance(type_arg, (NamedTypeSpecifier, Identifier)):
                type_name = type_arg.name.lower()
                val = _MAX_VALUES.get(type_name)
                if val is not None:
                    return SQLLiteral(value=val)
        return SQLNull()

    def _translate_minimum_pre(self, func: FunctionRef, translator) -> Optional[SQLExpression]:
        """Pre-translate CQL minimum(Type) — needs raw CQL AST for type name."""
        _MIN_VALUES = {
            "datetime": "0001-01-01 00:00:00",
            "date": "0001-01-01",
            "time": "00:00:00",
            "integer": -2147483648,
            "decimal": "-99999999999999999999.99999999",
        }
        if func.arguments:
            type_arg = func.arguments[0]
            if isinstance(type_arg, (NamedTypeSpecifier, Identifier)):
                type_name = type_arg.name.lower()
                val = _MIN_VALUES.get(type_name)
                if val is not None:
                    return SQLLiteral(value=val)
        return SQLNull()

    def _translate_collapse(self, args: list) -> SQLExpression:
        """Translate CQL Collapse to collapse_intervals UDF."""
        arg = args[0]
        if (
            isinstance(arg, SQLQualifiedIdentifier)
            and len(arg.parts) == 2
            and self.context.query_builder
        ):
            alias_name, col_name = arg.parts
            for (cte_name, _), ref in self.context.query_builder.cte_references.items():
                if ref.alias == alias_name:
                    outer_pid = (
                        self.context.resource_alias
                        or self.context.patient_alias
                        or "p"
                    )
                    arg = SQLSubquery(query=SQLSelect(
                        columns=[SQLFunctionCall(
                            name="json_group_array",
                            args=[SQLIdentifier(name=col_name)],
                        )],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=cte_name, quoted=True),
                            alias="_collapse_sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["_collapse_sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[outer_pid, "patient_id"]),
                        ),
                    ))
                    break
        if _is_list_returning_sql(arg):
            arg = SQLFunctionCall(name="to_json", args=[arg])
        return SQLFunctionCall(name="collapse_intervals", args=[arg])

    def _translate_expand(self, func: FunctionRef) -> Optional[SQLExpression]:
        """Translate CQL Expand for integer interval lists."""
        from ...parser.ast_nodes import ListExpression, Interval as CQLInterval
        if not func.arguments:
            return None
        cql_arg = func.arguments[0]
        if isinstance(cql_arg, ListExpression) and len(cql_arg.elements) == 1:
            interval_elem = cql_arg.elements[0]
            if isinstance(interval_elem, CQLInterval):
                low_sql = self.translate(interval_elem.low, usage=ExprUsage.SCALAR)
                high_sql = self.translate(interval_elem.high, usage=ExprUsage.SCALAR)
                series = SQLFunctionCall(name="generate_series", args=[low_sql, high_sql])
                lambda_param = SQLIdentifier(name="x")
                lambda_body = SQLFunctionCall(
                    name="intervalFromBounds",
                    args=[
                        SQLCast(expression=lambda_param, target_type="VARCHAR"),
                        SQLCast(expression=SQLIdentifier(name="x"), target_type="VARCHAR"),
                        SQLLiteral(value=True),
                        SQLLiteral(value=True),
                    ],
                )
                return SQLFunctionCall(
                    name="list_transform",
                    args=[series, SQLLambda(param="x", body=lambda_body)],
                )
        return None

    def _translate_type_conversion(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """Translate a CQL type conversion function."""
        name_lower = name.lower()
        type_map = {
            "toboolean": "BOOLEAN",
            "tostring": "VARCHAR",
            "tointeger": "INTEGER",
            "todecimal": "DOUBLE",
            "todate": "DATE",
            "todatetime": "TIMESTAMP",
            "totime": "TIME",
        }

        target_type = type_map.get(name_lower)
        if target_type and args:
            return SQLCast(expression=args[0], target_type=target_type)

        return args[0] if args else SQLNull()

    def _translate_exists(self, source: SQLExpression, negated: bool = False) -> SQLExpression:
        """Translate an exists expression."""
        if negated:
            return SQLUnaryOp(operator="IS NULL", operand=source, prefix=False)
        return SQLUnaryOp(operator="IS NOT NULL", operand=source, prefix=False)

    def _build_correlated_exists(self, cte_name: str) -> SQLExpression:
        """
        Build a correlated EXISTS subquery for a CTE reference.

        In population context, EXISTS subqueries must correlate the CTE's patient_id
        with the outer query's patient context to avoid cross-patient data leakage.

        Args:
            cte_name: The name of the CTE to reference.

        Returns:
            SQLExists with correlated WHERE clause if in population context,
            otherwise a simple EXISTS.
        """
        # Build the subquery: SELECT 1 FROM "CTE" sub WHERE sub.patient_id = outer.patient_id
        # Always correlate on patient_id. During translate_library(),
        # patient_alias is None; fall back to "p" which gets fixed up
        # later by replace_qualified_alias in translator.py.
        outer_alias = self.context.patient_alias or "p"
        if self.context.current_patient_id:
            correlation_where = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLLiteral(value=self.context.current_patient_id),
            )
        else:
            correlation_where = SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
            )

        # Use SQLAlias for the FROM clause to enable correlation detection
        # Note: No LIMIT 1 - EXISTS stops at first match anyway
        exists_select = SQLSelect(
            columns=[SQLLiteral(value=1)],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=cte_name, quoted=True),
                alias="sub",
            ),
            where=correlation_where,
        )

        return SQLExists(subquery=SQLSubquery(query=exists_select))

    @staticmethod
    def _strip_aggregates_for_exists(select: "SQLSelect") -> "SQLSelect":
        """Replace aggregate columns with ``SELECT 1`` for EXISTS subqueries.

        Aggregate functions like ``list()`` always produce exactly one output
        row even when the input set is empty.  This breaks ``NOT EXISTS``
        checks because the subquery returns a row regardless of input.
        Since EXISTS only needs to know whether any rows match, we can
        safely replace aggregate column lists with a literal ``1``.
        """
        _AGGREGATE_NAMES = frozenset({"list", "count", "sum", "avg", "min", "max",
                                       "string_agg", "array_agg", "group_concat"})
        if not isinstance(select, SQLSelect) or not select.columns:
            return select
        has_aggregate = False
        for col in select.columns:
            expr = col.expr if isinstance(col, SQLAlias) else col
            if isinstance(expr, SQLFunctionCall) and expr.name.lower() in _AGGREGATE_NAMES:
                has_aggregate = True
                break
        if has_aggregate:
            return SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=select.from_clause,
                joins=select.joins,
                where=select.where,
                group_by=select.group_by,
                having=select.having,
                order_by=select.order_by,
                limit=select.limit,
                distinct=select.distinct,
            )
        return select

    def _add_patient_id_correlation_to_exists(self, select: "SQLSelect") -> "SQLSelect":
        """Add patient_id correlation to an EXISTS subquery's inner SELECT.

        When an ``exists`` wraps a query whose FROM clause is backed by a CTE
        (or UNION of CTEs), the inner query must be correlated with the outer
        query's patient context to prevent cross-patient data leakage.

        The ``with/such that`` code-path already adds this correlation
        (see ``_translate_query``).  This helper covers the ``exists(query)``
        code-path which previously did not.
        """
        from ...translator.placeholder import RetrievePlaceholder

        # Determine the outer alias to correlate against
        outer_alias = self.context.resource_alias or self.context.patient_alias
        if not outer_alias:
            return select

        # Extract inner alias from FROM clause
        from_clause = select.from_clause
        if not isinstance(from_clause, SQLAlias):
            return select
        inner_alias = from_clause.alias
        if not inner_alias or inner_alias == outer_alias:
            return select

        # Check if the FROM source is CTE-backed (has patient_id column)
        def _is_cte_backed(expr):
            if isinstance(expr, SQLAlias):
                return _is_cte_backed(expr.expr)
            if isinstance(expr, SQLIdentifier) and expr.quoted:
                return True
            if isinstance(expr, RetrievePlaceholder):
                return True
            if isinstance(expr, SQLUnion):
                return True
            if isinstance(expr, SQLSubquery):
                inner = expr.query
                if isinstance(inner, SQLSelect) and inner.from_clause:
                    return _is_cte_backed(inner.from_clause)
                if isinstance(inner, SQLUnion):
                    return True
            return False

        if not _is_cte_backed(from_clause):
            return select

        # Check if patient_id correlation is already present (avoid duplicates)
        def _has_patient_id_corr(where_expr):
            if isinstance(where_expr, SQLBinaryOp):
                if where_expr.operator == "=":
                    left_str = _qual_id_str(where_expr.left)
                    right_str = _qual_id_str(where_expr.right)
                    if left_str and right_str:
                        if "patient_id" in left_str and "patient_id" in right_str:
                            return True
                if where_expr.operator == "AND":
                    return _has_patient_id_corr(where_expr.left) or _has_patient_id_corr(where_expr.right)
            return False

        def _qual_id_str(expr):
            if isinstance(expr, SQLQualifiedIdentifier):
                return ".".join(str(p) for p in expr.parts)
            return None

        if select.where and _has_patient_id_corr(select.where):
            return select

        # Add: inner_alias.patient_id = outer_alias.patient_id
        patient_corr = SQLBinaryOp(
            left=SQLQualifiedIdentifier(parts=[inner_alias, "patient_id"]),
            operator="=",
            right=SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"]),
        )
        new_where = (
            SQLBinaryOp(left=select.where, operator="AND", right=patient_corr)
            if select.where
            else patient_corr
        )
        return SQLSelect(
            columns=select.columns,
            from_clause=select.from_clause,
            where=new_where,
            joins=getattr(select, 'joins', None),
            group_by=getattr(select, 'group_by', None),
            having=getattr(select, 'having', None),
            order_by=getattr(select, 'order_by', None),
            limit=getattr(select, 'limit', None),
            distinct=getattr(select, 'distinct', None),
        )

    def _get_operand_resource_type(self, operand: SQLExpression) -> Optional[str]:
        """Extract resource type from a union operand if determinable."""
        if isinstance(operand, RetrievePlaceholder):
            return operand.resource_type
        if isinstance(operand, SQLSubquery):
            inner = operand.query if hasattr(operand, 'query') else None
            if isinstance(inner, RetrievePlaceholder):
                return inner.resource_type
            if isinstance(inner, SQLSelect) and inner.from_clause:
                from_clause = inner.from_clause
                if isinstance(from_clause, SQLIdentifier) and from_clause.quoted:
                    name = from_clause.name
                    if ":" in name:
                        return name.split(":")[0].strip()
        if isinstance(operand, SQLIdentifier) and operand.quoted:
            name = operand.name
            if ":" in name:
                return name.split(":")[0].strip()
        return None

    def _check_union_disjointness(self, operands: List[SQLExpression]) -> bool:
        """Check if all union operands reference different resource types."""
        resource_types = [self._get_operand_resource_type(op) for op in operands]
        all_known = all(rt is not None for rt in resource_types)
        if not all_known or len(resource_types) < 2:
            return False
        return len(set(resource_types)) == len(resource_types)

    def _extract_subqueries_from_union(self, expr: SQLExpression) -> List[SQLExpression]:
        """
        Recursively extract subqueries from nested jsonConcat expressions.

        Args:
            expr: SQL expression that might be jsonConcat with subquery args

        Returns:
            List of SQLSubquery objects found, or empty list if not extractable
        """
        if isinstance(expr, SQLSubquery):
            return [expr]

        if isinstance(expr, SQLFunctionCall) and expr.name.lower() == "jsonconcat":
            left_subs = self._extract_subqueries_from_union(expr.args[0]) if len(expr.args) > 0 else []
            right_subs = self._extract_subqueries_from_union(expr.args[1]) if len(expr.args) > 1 else []
            return left_subs + right_subs

        if isinstance(expr, SQLUnion):
            # Already a union, extract all subquery operands
            result = []
            for op in expr.operands:
                if isinstance(op, SQLSubquery):
                    result.append(op)
            return result

        # Wrap row-producing set operations (INTERSECT, EXCEPT) in a
        # subquery so they can participate in UNION composition.
        # Normalize operands: strip patient_id correlation added by
        # SCALAR-context translation, since in UNION context each branch
        # must produce ALL rows independently.
        if isinstance(expr, (SQLIntersect, SQLExcept)):
            normalized_ops = [self._normalize_set_operand_for_union(op) for op in expr.operands]
            return [SQLSubquery(query=type(expr)(operands=normalized_ops))]

        return []  # Cannot extract - not a union-compatible expression

    @staticmethod
    def _normalize_set_operand_for_union(op: SQLExpression) -> SQLExpression:
        """Strip patient_id correlation from a set operation operand.

        When ExpressionRefs are translated in SCALAR context, they gain
        ``WHERE sub.patient_id = <alias>.patient_id``.  In UNION context
        that correlation is invalid (there is no outer ``FROM _patients``).
        This helper widens the subquery to ``SELECT * FROM "CTE"`` and
        removes the correlation filter.
        """
        if isinstance(op, SQLSubquery) and isinstance(op.query, SQLSelect):
            inner = op.query
            where = inner.where
            if where is not None and _is_patient_id_correlation(where):
                from_clause = inner.from_clause
                if isinstance(from_clause, SQLAlias) and isinstance(from_clause.expr, SQLIdentifier):
                    from_ident = from_clause.expr
                elif isinstance(from_clause, SQLIdentifier):
                    from_ident = from_clause
                else:
                    return op
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=from_ident,
                ))
        return op

    def _translate_age_function(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """Translate AgeInYears/AgeInMonths/etc. using calendar-duration macros.

        Uses the demographics CTE to access Patient.birthDate and the
        YearsBetween/MonthsBetween/DaysBetween macros for CQL-compliant
        calendar duration semantics (CQL §2.3, §18.4).
        """
        name_lower = name.lower()

        # Map to calendar-duration macro names
        macro_map = {
            "ageinyears": "YearsBetween",
            "ageinmonths": "MonthsBetween",
            "ageindays": "DaysBetween",
            "ageinhours": "HoursBetween",
            "ageinminutes": "MinutesBetween",
            "ageinseconds": "SecondsBetween",
        }

        macro_name = macro_map.get(name_lower, "YearsBetween")

        if args:
            birth_date = args[0]
        else:
            # Use demographics CTE for birthDate access (mirrors _translate_age_at_function)
            self.context._needs_demographics = True
            _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
            birth_date = SQLSubquery(query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["_pd", "birth_date"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_patient_demographics"),
                    alias="_pd",
                ),
                where=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_pd", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                ),
                limit=1,
            ))

        return SQLFunctionCall(
            name=macro_name,
            args=[birth_date, SQLFunctionCall(name="CURRENT_DATE", args=[])],
        )

    def _translate_age_at_function(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """
        Translate age calculation functions with explicit as_of date.

        These functions call DuckDB UDFs directly:
        - AgeInYearsAt(patient_resource, as_of_date)
        - AgeInMonthsAt(patient_resource, as_of_date)
        - AgeInDaysAt(patient_resource, as_of_date)

        When _patient_demographics CTE is available in population mode,
        this function uses birthday-aware age calculation by joining to
        the demographics CTE instead of correlated subqueries.
        """
        # Map function names to UDF names (proper casing)
        udf_name_map = {
            "ageinyearsat": "AgeInYearsAt",
            "ageinmonthsat": "AgeInMonthsAt",
            "ageindaysat": "AgeInDaysAt",
        }

        udf_name = udf_name_map.get(name.lower(), "AgeInYearsAt")

        # Args should be (patient_resource, as_of_date)
        # If only one arg provided, assume it's the as_of_date and use current resource
        if len(args) == 1:
            # Use demographics CTE for birthday-aware age calculation.
            # Always flag that demographics CTE is needed.
            self.context._needs_demographics = True
            unit_map = {
                "ageinyearsat": "year",
                "ageinmonthsat": "month",
                "ageindaysat": "day",
            }
            unit = unit_map.get(name.lower(), "year")

            _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
            birth_date = SQLSubquery(query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["_pd", "birth_date"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_patient_demographics"),
                    alias="_pd",
                ),
                where=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_pd", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                ),
                limit=1,
            ))
            as_of_date = self._ensure_date_cast(args[0])

            if unit == "year":
                # Birthday-aware: subtract 1 if birthday hasn't occurred yet
                month_as_of = SQLExtract(extract_field="MONTH", source=as_of_date)
                day_as_of = SQLExtract(extract_field="DAY", source=as_of_date)
                month_birth = SQLExtract(extract_field="MONTH", source=birth_date)
                day_birth = SQLExtract(extract_field="DAY", source=birth_date)

                birthday_not_reached = SQLBinaryOp(
                    operator="OR",
                    left=SQLBinaryOp(operator="<", left=month_as_of, right=month_birth),
                    right=SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(operator="=", left=month_as_of, right=month_birth),
                        right=SQLBinaryOp(operator="<", left=day_as_of, right=day_birth),
                    ),
                )

                return SQLBinaryOp(
                    operator="-",
                    left=SQLBinaryOp(
                        operator="-",
                        left=SQLExtract(extract_field="YEAR", source=as_of_date),
                        right=SQLExtract(extract_field="YEAR", source=birth_date),
                    ),
                    right=SQLCase(
                        when_clauses=[(
                            birthday_not_reached,
                            SQLLiteral(value=1),
                        )],
                        else_clause=SQLLiteral(value=0),
                    ),
                )
            else:
                # For months/days, date_diff is acceptable
                return SQLFunctionCall(
                    name="date_diff",
                    args=[SQLLiteral(value=unit), birth_date, as_of_date]
                )
        elif len(args) >= 2:
            patient_resource = args[0]
            as_of_date = args[1]
        else:
            return SQLNull()

        return SQLFunctionCall(name=udf_name, args=[patient_resource, as_of_date])


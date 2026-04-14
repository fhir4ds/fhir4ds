"""Core expression translation: literals, identifiers, and type conversions."""
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

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

logger = logging.getLogger(__name__)


class CoreMixin:
    """Mixin providing literal, identifier, and basic conversion translations."""
    def _camel_to_snake(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def _translate_literal(self, lit: Literal, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL literal to SQL."""
        value = lit.value

        if value is None:
            return SQLNull()

        if isinstance(value, bool):
            return SQLLiteral(value=value)

        if isinstance(value, str):
            return SQLLiteral(value=value)

        if isinstance(value, (int, float)):
            # Handle special numeric values
            if isinstance(value, float):
                if value == float("inf"):
                    return SQLLiteral(value=float("inf"))
                elif value == float("-inf"):
                    return SQLLiteral(value=float("-inf"))
                elif value != value:  # NaN
                    return SQLLiteral(value=float("nan"))
            return SQLLiteral(value=value)

        # Fallback
        return SQLLiteral(value=str(value))

    def _translate_date_time_literal(self, dt: DateTimeLiteral, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL DateTime literal to SQL TIMESTAMP."""
        value = dt.value
        # CQL format: @2024-01-15T12:30:00 or @2024-01-15
        # DuckDB format: TIMESTAMP '2024-01-15 12:30:00' or '2024-01-15'

        # Remove @ prefix if present
        if value.startswith("@"):
            value = value[1:]

        # Replace T with space for DuckDB
        value = value.replace("T", " ")

        # Return as string literal - DuckDB can parse ISO date/datetime strings
        return SQLLiteral(value=value)

    def _translate_time_literal(self, t: TimeLiteral, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL Time literal to SQL TIME."""
        value = t.value
        # CQL format: @T12:30:00 or @T14:00
        # DuckDB format: TIME '12:30:00'

        # Remove @T prefix if present
        if value.startswith("@T"):
            value = value[2:]
        elif value.startswith("T"):
            value = value[1:]

        return SQLFunctionCall(
            name="CAST",
            args=[
                SQLLiteral(value=value),
            ],
        )

    def _translate_quantity(self, qty: Quantity, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL Quantity to SQL (as JSON or UDF call)."""
        value = qty.value
        unit = qty.unit

        # Create a JSON representation of the quantity
        quantity_dict = {
            "value": float(value) if not isinstance(value, float) else value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
        }

        # Return as JSON string that can be used with quantity UDFs
        result = SQLFunctionCall(
            name="parse_quantity",
            args=[SQLLiteral(value=json.dumps(quantity_dict))],
        )
        result.result_type = "Quantity"
        return result

    def _translate_identifier(self, ident: Identifier, usage: ExprUsage = ExprUsage.LIST) -> SQLExpression:
        """Translate a CQL identifier to SQL.

        Args:
            ident: The CQL identifier to translate.
            usage: How the expression result will be used (LIST, SCALAR, BOOLEAN, EXISTS).

        Returns:
            SQL expression appropriate for the given usage context.
        """
        # For backward compatibility with old handlers that still pass boolean_context
        # This will be removed after full migration
        if isinstance(usage, bool):
            usage = ExprUsage.BOOLEAN if usage else ExprUsage.LIST

        name = ident.name


        # Check if this is a known alias with a stored SQL expression
        if self.context.is_alias(name):
            symbol = self.context.lookup_symbol(name)
            # Check for union_expr marker (stored for SQLUnion or SQLCase with SQLUnion)
            union_expr = getattr(symbol, 'union_expr', None) if symbol else None
            if union_expr is not None:
                # This alias was stored with a union_expr - return it directly
                # The caller (e.g., _translate_property) will handle it
                return union_expr

            # Check for AST expression first (fixes B4-B6 violations)
            ast_expr = getattr(symbol, 'ast_expr', None) if symbol else None
            if ast_expr is not None:
                # When ast_expr is an SQLSubquery but the symbol also has a
                # cte_name, skip the ast_expr and fall through to the cte_name
                # path below.  The cte_name path produces the correct
                # SQLQualifiedIdentifier(parts=[alias, "resource"]) which is
                # the proper row-level reference.  Returning the SQLSubquery
                # here would produce an uncorrelated scalar subquery that
                # scans the entire CTE instead of referencing the current row.
                _skip_ast = (
                    isinstance(ast_expr, SQLSubquery)
                    and symbol is not None
                    and getattr(symbol, 'cte_name', None)
                )
                if not _skip_ast:
                    # Use AST introspection instead of string inspection
                    from ...translator.ast_utils import (
                        ast_is_case_with_union,
                        ast_is_list_operation,
                        ast_is_boolean_result,
                    )

                    # Check for invalid pattern: CASE with SQLUnion in branches (B4)
                    if ast_is_case_with_union(ast_expr):
                        # This is problematic - the CASE has UNION in branches
                        # Log a warning as it indicates a structural issue
                        pass

                    # Check if expression is a list operation (B5)
                    is_list_expr = ast_is_list_operation(ast_expr)

                    # Check if expression is already boolean-valued (B6)
                    is_boolean_result = ast_is_boolean_result(ast_expr)

                    if is_list_expr and not is_boolean_result:
                        # Wrap in list_extract to get first element for scalar use
                        return SQLFunctionCall(
                            name="list_extract",
                            args=[ast_expr, SQLLiteral(value=1)]
                        )

                    # Return the AST expression directly
                    return ast_expr

            sql_expr_val = getattr(symbol, 'sql_expr', None) if symbol else None
            if not sql_expr_val:
                sql_expr_val = getattr(symbol, 'sql_ref', None) if symbol else None
            if sql_expr_val:
                # Try to construct a proper AST node from the string
                if sql_expr_val.startswith('"') and sql_expr_val.endswith('"') and '.' not in sql_expr_val:
                    # Quoted identifier like '"MyCTE"'
                    return SQLIdentifier(name=sql_expr_val.strip('"'))
                if '.' in sql_expr_val and not any(c in sql_expr_val for c in '()+*/ '):
                    # Qualified identifier like 'alias.column'
                    parts = [p.strip('"') for p in sql_expr_val.split('.')]
                    return SQLQualifiedIdentifier(parts=parts)
                logger.warning("AliasRef '%s' using SQLRaw fallback (no ast_expr on symbol)", name)
                return SQLRaw(raw_sql=sql_expr_val)
            # When both ast_expr and sql_expr are absent but cte_name is set,
            # qualify with the appropriate CTE column to avoid returning the
            # full DuckDB row STRUCT.
            if symbol and symbol.cte_name:
                # Use the SQL-level table alias when available (e.g., from
                # _translate_query_on_alias), falling back to the CQL name.
                _sql_alias = symbol.table_alias or name
                meta = self.context.definition_meta.get(symbol.cte_name)
                if meta:
                    col = "resource" if meta.has_resource else (meta.value_column or "value")
                    return SQLQualifiedIdentifier(parts=[_sql_alias, col])
                else:
                    col = self._get_definition_value_column(symbol.cte_name)
                    return SQLQualifiedIdentifier(parts=[_sql_alias, col])
            return SQLIdentifier(name=name)

        # Look up in symbol table
        symbol = self.context.lookup_symbol(name)
        if symbol:
            if symbol.symbol_type == "parameter":
                # Generic interval parameter binding lookup
                binding = self.context.get_parameter_binding(name)
                if binding is not None and isinstance(binding, tuple) and len(binding) == 2:
                    b_start, b_end = binding
                    p_start = b_start or "{mp_start}"
                    p_end = b_end or "{mp_end}"
                    # For Interval<DateTime> parameters, use TIMESTAMP precision
                    # so that datetime comparisons are exact (e.g.,
                    # 2026-01-01T08:00 is NOT within [2025-07-01, 2026-01-01]
                    # because at datetime precision 08:00 > 00:00).
                    # Date-only end bounds get end-of-day (T23:59:59.999)
                    # to match CQL date→datetime promotion semantics.
                    _date_only_re = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
                    is_dt = symbol.cql_type and "DateTime" in str(symbol.cql_type)
                    if is_dt:
                        if isinstance(p_start, str) and _date_only_re.match(p_start):
                            p_start = p_start + "T00:00:00.000"
                        if isinstance(p_end, str) and _date_only_re.match(p_end):
                            p_end = p_end + "T23:59:59.999"
                        cast_type = "TIMESTAMP"
                    else:
                        cast_type = "DATE"
                    return SQLFunctionCall(
                        name="intervalFromBounds",
                        args=[
                            SQLCast(expression=SQLLiteral(value=p_start), target_type=cast_type),
                            SQLCast(expression=SQLLiteral(value=p_end), target_type=cast_type),
                            SQLLiteral(value=True),
                            SQLLiteral(value=True),
                        ],
                    )
                return SQLParameterRef(name=name)
            elif symbol.symbol_type == "definition":
                # Reference to a named expression - generate subquery reference to CTE
                # The definition will be available as a CTE in the final SQL
                # For SCALAR/BOOLEAN/EXISTS context, register JOIN with query builder
                # Fetch meta here so it's available for LIST context too.
                meta = self.context.definition_meta.get(name)
                if usage in (ExprUsage.SCALAR, ExprUsage.BOOLEAN, ExprUsage.EXISTS):

                    if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
                        # FIX: Always use EXISTS subquery for BOOLEAN/EXISTS context CTE references.
                        # JOIN aliases (j1.resource IS NOT NULL) are only valid in the same SELECT scope
                        # where the JOIN is added, but this reference may appear inside nested subqueries
                        # where the alias is not visible. Using EXISTS is safer and works in all contexts.
                        return self._build_correlated_exists(name)

                    elif usage == ExprUsage.SCALAR:
                        # Check if RESOURCE_ROWS is used in SCALAR context - emit warning
                        if meta and meta.shape == RowShape.RESOURCE_ROWS:
                            self.context.warnings.add_semantics(
                                message="RESOURCE_ROWS used in SCALAR context - using LIMIT 1 or correlated subquery",
                                definition=name,
                                suggestion="Use First() or Last() for explicit single-value selection"
                            )
                        # FIX: Always use correlated subquery for SCALAR context CTE references.
                        # JOIN aliases (j1.resource) are only valid in the same SELECT scope where
                        # the JOIN is added, but this reference may appear inside nested subqueries
                        # (e.g., WHERE clause of a First/Last query) where the alias is not visible.
                        # Using a subquery is safer and works in all contexts.
                        # For boolean definitions (PATIENT_SCALAR, no resource, Boolean type), use EXISTS check
                        if meta and meta.shape == RowShape.PATIENT_SCALAR and not meta.has_resource and meta.cql_type == "Boolean":
                            return self._build_correlated_exists(name)
                        # Forward reference: infer if definition is boolean from CQL AST
                        if not meta:
                            if self._is_forward_ref_boolean(name):
                                return self._build_correlated_exists(name)
                        # Determine the outer patient_id alias for correlation.
                        # Use resource_alias (e.g., query loop alias) or patient_alias
                        # to avoid broken "p.patient_id" refs inside CTE definitions.
                        _outer_pid_alias = self.context.resource_alias or self.context.patient_alias or "p"

                        # For CTEs with value column (scalars), select value
                        if meta and not meta.has_resource:
                            subq = SQLSubquery(query=SQLSelect(
                                columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                                from_clause=SQLAlias(
                                    expr=SQLIdentifier(name=name, quoted=True),
                                    alias="sub",
                                ),
                                where=SQLBinaryOp(
                                    operator="=",
                                    left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                    right=SQLQualifiedIdentifier(parts=[_outer_pid_alias, "patient_id"]),
                                ),
                                limit=1
                            ))
                            if meta.sql_result_type:
                                subq.result_type = meta.sql_result_type
                            return subq
                        # For other types, use meta-aware or forward-reference-aware column
                        col = self._get_definition_value_column(name)
                        subq = SQLSubquery(query=SQLSelect(
                            columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=name, quoted=True),
                                alias="sub",
                            ),
                            where=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                right=SQLQualifiedIdentifier(parts=[_outer_pid_alias, "patient_id"]),
                            ),
                            limit=1
                        ))
                        if meta and meta.sql_result_type:
                            subq.result_type = meta.sql_result_type
                        return subq

                # Check if the referenced definition IS boolean, regardless of how WE're using it.
                # This handles: define Denominator: "Initial Population"
                # where Initial Population is Boolean but Denominator uses it as a value reference.
                if meta and meta.shape == RowShape.PATIENT_SCALAR and meta.cql_type == "Boolean":
                    # This definition evaluates to true/false per patient.
                    # Even in LIST/SCALAR context, the right pattern is EXISTS/JOIN.
                    if self.context.query_builder:
                        alias = self.context.query_builder.track_cte_reference(
                            name, usage=ExprUsage.BOOLEAN, shape=meta.shape
                        )
                        return SQLBinaryOp(
                            operator="IS NOT",
                            left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
                            right=SQLNull(),
                        )
                    else:
                        return self._build_correlated_exists(name)

                # LIST context - use existing logic
                if self.context.query_builder:
                    self.context.query_builder.track_cte_reference(name)
                # Check if this CTE is already being tracked for JOIN conversion
                if self.context.query_builder:
                    ref = self.context.query_builder.get_cte_reference(name)
                    if ref:
                        # Only short-circuit to column reference when the CTE has a
                        # resource column; otherwise fall through to subquery so that
                        # definitions which produce only patient_id (boolean/scalar
                        # results) are handled correctly.
                        if meta and meta.has_resource:
                            return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])

                # Narrow to the appropriate column so that scalar usage
                # does not receive the whole row as a DuckDB STRUCT.
                if meta and meta.has_resource:
                    val_col = "resource"
                elif meta and not meta.has_resource and meta.cql_type != "Boolean":
                    val_col = meta.value_column or "value"
                else:
                    val_col = "*"
                subquery = SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name=val_col)],
                    from_clause=SQLIdentifier(name=name, quoted=True)
                ))
                return subquery
            elif symbol.symbol_type == "alias":
                # When the alias has a known CTE backing, qualify with the
                # appropriate column so DuckDB doesn't return the full row STRUCT.
                if symbol.cte_name:
                    meta = self.context.definition_meta.get(symbol.cte_name)
                    if meta:
                        col = "resource" if meta.has_resource else (meta.value_column or "value")
                        return SQLQualifiedIdentifier(parts=[name, col])
                    else:
                        # Forward reference — meta not yet available.
                        # Infer column from the CQL AST definition.
                        col = self._get_definition_value_column(symbol.cte_name)
                        return SQLQualifiedIdentifier(parts=[name, col])
                return SQLIdentifier(name=name)
            elif symbol.sql_expr:
                # A-1: Handle both string and AST node during migration
                if isinstance(symbol.sql_expr, str):
                    return SQLIdentifier(name=symbol.sql_expr)
                else:
                    # It's an AST node, return it directly
                    return symbol.sql_expr

        # Check if this is a let variable
        if name in self.context.let_variables:
            return self.context.let_variables[name]

        # Check if this is Patient context reference
        if name == "Patient":
            # In population context, use correlated subquery to get patient resource.
            # Always flag that demographics CTE is needed so it gets created.
            self.context._needs_demographics = True
            # Determine the outer patient_id reference for correlation.
            outer_alias = self.context.resource_alias
            if outer_alias:
                outer_pid = SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"])
            else:
                outer_pid = SQLQualifiedIdentifier(parts=["p", "patient_id"])
            return SQLSubquery(query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["_pd", "resource"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_patient_demographics", quoted=False),
                    alias="_pd"
                ),
                where=SQLBinaryOp(
                    left=SQLQualifiedIdentifier(parts=["_pd", "patient_id"]),
                    operator="=",
                    right=outer_pid,
                ),
                limit=1,
            ))

        # Check if this is a code reference
        if hasattr(self.context, 'codes') and name in self.context.codes:
            code_info = self.context.codes[name]
            # Return the code value for use in comparisons
            system = code_info.get("codesystem", code_info.get("system", ""))
            code = code_info.get("code", "")
            # Return as a formatted string that can be used in comparisons
            return SQLLiteral(value=f"{system}|{code}")

        # Check if this is a definition reference (not in symbol table but defined in context)
        definition = self.context.get_definition(name)
        if definition:
            # Fetch meta here so it's available for LIST context too.
            meta = self.context.definition_meta.get(name)
            # For SCALAR/BOOLEAN/EXISTS context, register JOIN with query builder
            if usage in (ExprUsage.SCALAR, ExprUsage.BOOLEAN, ExprUsage.EXISTS):

                if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
                    # FIX: Always use EXISTS subquery for BOOLEAN/EXISTS context CTE references.
                    # JOIN aliases (j1.resource IS NOT NULL) are only valid in the same SELECT scope
                    # where the JOIN is added, but this reference may appear inside nested subqueries
                    # where the alias is not visible. Using EXISTS is safer and works in all contexts.
                    return self._build_correlated_exists(name)

                elif usage == ExprUsage.SCALAR:
                    # FIX: Always use correlated subquery for SCALAR context CTE references.
                    # JOIN aliases (j1.resource) are only valid in the same SELECT scope where
                    # the JOIN is added, but this reference may appear inside nested subqueries
                    # (e.g., WHERE clause of a First/Last query) where the alias is not visible.
                    # Using a subquery is safer and works in all contexts.
                    # For boolean definitions (PATIENT_SCALAR, no resource, Boolean type), use EXISTS check
                    if meta and meta.shape == RowShape.PATIENT_SCALAR and not meta.has_resource and meta.cql_type == "Boolean":
                        return self._build_correlated_exists(name)
                    # For CTEs with value column (scalars), select value
                    if meta and not meta.has_resource:
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLQualifiedIdentifier(parts=["sub", "value"])],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=name, quoted=True),
                                alias="sub",
                            ),
                            where=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                            ),
                            limit=1
                        ))
                    # For other types, use meta-aware or forward-reference-aware column
                    col = self._get_definition_value_column(name)
                    return SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=name, quoted=True),
                            alias="sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                        ),
                        limit=1
                    ))

            # Check if the referenced definition IS boolean, regardless of how WE're using it.
            # This handles: define Denominator: "Initial Population"
            # where Initial Population is Boolean but Denominator uses it as a value reference.
            if meta and meta.shape == RowShape.PATIENT_SCALAR and meta.cql_type == "Boolean":
                # This definition evaluates to true/false per patient.
                # Even in LIST/SCALAR context, the right pattern is EXISTS/JOIN.
                if self.context.query_builder:
                    alias = self.context.query_builder.track_cte_reference(
                        name, usage=ExprUsage.BOOLEAN, shape=meta.shape
                    )
                    return SQLBinaryOp(
                        operator="IS NOT",
                        left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
                        right=SQLNull(),
                    )
                else:
                    return self._build_correlated_exists(name)

            # LIST context - track CTE reference for JOIN optimization.
            # Only use the JOIN-alias shortcut when the definition shape is
            # known.  UNKNOWN-shape definitions might be RESOURCE_ROWS with a
            # ``resource`` column, so defaulting to ``value`` would break.
            from ...translator.context import RowShape as _RS
            if self.context.query_builder and meta is not None and meta.shape != _RS.UNKNOWN:
                self.context.query_builder.track_cte_reference(name)
                ref = self.context.query_builder.get_cte_reference(name)
                if ref:
                    if meta.has_resource:
                        return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                    elif not meta.has_resource and meta.cql_type != "Boolean":
                        return SQLQualifiedIdentifier(parts=[ref.alias, meta.value_column])
            if meta and not meta.has_resource and meta.cql_type != "Boolean" and meta.shape != _RS.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                    limit=1
                ))
            # For boolean CTEs (patient_id only), SELECT * is fine
            if meta and not meta.has_resource and meta.shape != _RS.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLIdentifier(name=name, quoted=True)
                ))
            # When meta is None (forward reference not yet translated),
            # use _get_definition_value_column to infer the correct column
            if meta is None:
                col = self._get_definition_value_column(name)
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                    limit=1
                ))
            # For RESOURCE_ROWS or fully unknown, select resource column
            return SQLSubquery(query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name=name, quoted=True)
            ))

        # Check if this is a forward reference to a definition (not yet translated but will be)
        if hasattr(self.context, '_definition_names') and name in self.context._definition_names:
            # Emit warning for forward reference
            self.context.warnings.add_performance(
                message="Forward reference caused fallback to correlated subquery",
                definition=name,
                suggestion="Ensure definitions are ordered by dependency (check topological sort)"
            )

            # Fetch meta here so it's available for LIST context too.
            meta = self.context.definition_meta.get(name)
            # For SCALAR/BOOLEAN/EXISTS context, register JOIN with query builder
            if usage in (ExprUsage.SCALAR, ExprUsage.BOOLEAN, ExprUsage.EXISTS):

                if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
                    # FIX: Always use EXISTS subquery for BOOLEAN/EXISTS context CTE references.
                    # JOIN aliases (j1.resource IS NOT NULL) are only valid in the same SELECT scope
                    # where the JOIN is added, but this reference may appear inside nested subqueries
                    # where the alias is not visible. Using EXISTS is safer and works in all contexts.
                    return self._build_correlated_exists(name)

                elif usage == ExprUsage.SCALAR:
                    # Check if RESOURCE_ROWS is used in SCALAR context - emit warning
                    if meta and meta.shape == RowShape.RESOURCE_ROWS:
                        self.context.warnings.add_semantics(
                            message="RESOURCE_ROWS used in SCALAR context - using LIMIT 1 or correlated subquery",
                            definition=name,
                            suggestion="Use First() or Last() for explicit single-value selection"
                        )
                    # FIX: Always use correlated subquery for SCALAR context CTE references.
                    # JOIN aliases (j1.resource) are only valid in the same SELECT scope where
                    # the JOIN is added, but this reference may appear inside nested subqueries
                    # (e.g., WHERE clause of a First/Last query) where the alias is not visible.
                    # Using a subquery is safer and works in all contexts.
                    # For boolean definitions (PATIENT_SCALAR, no resource, Boolean type), use EXISTS check
                    if meta and meta.shape == RowShape.PATIENT_SCALAR and not meta.has_resource and meta.cql_type == "Boolean":
                        return self._build_correlated_exists(name)
                    # For CTEs with value column (scalars), select value
                    if meta and not meta.has_resource:
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=name, quoted=True),
                                alias="sub",
                            ),
                            where=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                            ),
                            limit=1
                        ))
                    # For other types, use meta-aware or forward-reference-aware column
                    col = self._get_definition_value_column(name)
                    return SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=name, quoted=True),
                            alias="sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                        ),
                        limit=1
                    ))

            # LIST context - track CTE reference for JOIN optimization
            from ...translator.context import RowShape as _RS2
            if self.context.query_builder and meta is not None and meta.shape != _RS2.UNKNOWN:
                self.context.query_builder.track_cte_reference(name)
                ref = self.context.query_builder.get_cte_reference(name)
                if ref:
                    if meta.has_resource:
                        return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                    elif not meta.has_resource and meta.cql_type != "Boolean":
                        return SQLQualifiedIdentifier(parts=[ref.alias, meta.value_column])

            # For non-resource CTEs with a value column, select only value column
            if meta and not meta.has_resource and meta.cql_type != "Boolean" and meta.shape != _RS2.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                    limit=1
                ))
            # Boolean CTE - select all
            if meta and not meta.has_resource and meta.shape != _RS2.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLIdentifier(name=name, quoted=True)
                ))
            # When meta is None, infer column from CQL AST
            if meta is None:
                col = self._get_definition_value_column(name)
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                    limit=1
                ))
            # When meta has UNKNOWN shape but column info, use correlated subquery
            if meta is not None and meta.shape == _RS2.UNKNOWN:
                col = "resource" if meta.has_resource else meta.value_column
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    ),
                    limit=1
                ))
            # For RESOURCE_ROWS, select resource column
            return SQLSubquery(query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name=name, quoted=True)
            ))

        # Default: treat as identifier
        return SQLIdentifier(name=name)

    def _translate_qualified_identifier(self, qi: QualifiedIdentifier, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL qualified identifier (e.g., Library.Function) to SQL."""
        parts = qi.parts

        if not parts:
            return SQLNull()

        first = parts[0]

        # Check if first part is an include reference
        if first in self.context.includes:
            # Reference to included library
            # e.g., FHIRHelpers.ToDateTime or AIFrailLTCF."Some Definition"
            if len(parts) >= 2:
                full_name = ".".join(parts)
                # Check if this definition was successfully loaded
                if hasattr(self.context, 'has_included_definition') and not self.context.has_included_definition(full_name):
                    # Definition wasn't loaded (library failed to parse)
                    # Add a warning to make the issue visible
                    self.context.warnings.add_semantics(
                        message=f"Included library definition '{full_name}' was not loaded, generating EXISTS subquery",
                        definition=full_name,
                        suggestion="Ensure the included library parses correctly for optimal results"
                    )
                    # Generate an EXISTS subquery referencing the expected CTE name
                    # The CTE will be generated by the query builder even if the definition wasn't parsed
                    # This ensures the SQL is syntactically correct and references the CTE properly
                    if boolean_context:
                        return self._build_correlated_exists(full_name)
                    # For list context, return a subquery selecting from the expected CTE
                    return SQLSubquery(
                        query=SQLSelect(
                            columns=[SQLIdentifier(name="resource")],
                            from_clause=SQLIdentifier(name=full_name, quoted=True),
                        )
                    )
                # This is a reference to a definition in an included library
                # Return a proper subquery to the CTE
                # Track CTE reference for JOIN optimization
                if self.context.query_builder:
                    self.context.query_builder.track_cte_reference(full_name)
                if boolean_context:
                    # Use correlated EXISTS for boolean context
                    return self._build_correlated_exists(full_name)
                else:
                    # Check if this CTE is already being tracked for JOIN conversion
                    meta = self.context.get_definition_meta(full_name)
                    if self.context.query_builder:
                        ref = self.context.query_builder.get_cte_reference(full_name)
                        if ref:
                            if meta and meta.has_resource:
                                return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                            elif meta and (meta.is_scalar or (not meta.has_resource and meta.cql_type != "Boolean")):
                                return SQLQualifiedIdentifier(parts=[ref.alias, meta.value_column])

                    # For non-resource CTEs with value column, select only value column
                    if meta and not meta.has_resource and meta.cql_type != "Boolean":
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=full_name, quoted=True),
                                alias="sub",
                            ),
                            where=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                            ),
                            limit=1
                        ))
                    subquery = SQLSubquery(query=SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLIdentifier(name=full_name, quoted=True)
                    ))
                    return subquery
            return SQLIdentifier(name=first)

        # Check if this is a valueset reference
        if first in self.context.valuesets and len(parts) == 1:
            return SQLLiteral(value=self.context.valuesets[first])

        # Check if this is a codesystem reference
        if first in self.context.codesystems:
            cs_url = self.context.codesystems[first]
            if len(parts) > 1:
                # Code from codesystem: codesystem|code
                return SQLLiteral(value=f"{cs_url}|{parts[1]}")
            return SQLLiteral(value=cs_url)

        # Default: qualified identifier
        return SQLQualifiedIdentifier(parts=parts)

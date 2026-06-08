"""Interval operations for CQL to SQL translation.

Handles interval bound extraction, resource-to-interval conversion,
interval overlap decomposition, and FHIR interval detection.
"""
from __future__ import annotations

from typing import Any, Optional

from ...parser.ast_nodes import (
    BinaryExpression,
    Identifier,
    Interval,
    QualifiedIdentifier,
)
from ...translator.context import ExprUsage
from ...translator.types import (
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLLiteral,
    SQLNull,
    SQLSelect,
    SQLSubquery,
)


class IntervalMixin:
    """Interval operations for CQL to SQL translation.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, ``_KNOWN_CHOICE_PATHS``, and the
    other helpers available on ExpressionTranslator.
    """

    # Mapping from FHIR resource types to their primary date/period paths.
    # Used by _ensure_resource_to_interval to convert a bare resource alias
    # (e.g., TotalHip.resource) into its canonical interval for temporal ops.
    #
    # Source: FHIR R4 StructureDefinitions (https://hl7.org/fhir/R4/resourcelist.html).
    # Extend via subclass or by adding entries at runtime:
    #   TemporalIntervalMixin._RESOURCE_PRIMARY_DATE_PATHS["MyResource"] = "dateField"
    _RESOURCE_PRIMARY_DATE_PATHS: dict = {
        "Encounter": "period",
        "Procedure": "performed",
        "Observation": "effective",
        "Condition": "onset",
        "MedicationRequest": "authoredOn",
        "MedicationAdministration": "effective",
        "MedicationDispense": "whenHandedOver",
        "Immunization": "occurrence",
        "ServiceRequest": "authoredOn",
        "Communication": "sent",
        "DiagnosticReport": "effective",
        "Claim": "billablePeriod",
        "Coverage": "period",
        "AllergyIntolerance": "onset",
        "DeviceRequest": "authoredOn",
    }

    def _try_decompose_interval_overlaps(
        self,
        left: SQLExpression,
        right: SQLExpression,
        expr: BinaryExpression,
    ) -> Optional[SQLExpression]:
        """
        Try to decompose interval overlaps to simple date comparisons.

        Instead of: intervalOverlaps(intervalFromBounds(a_start, a_end), intervalFromBounds(b_start, b_end))
        Generate: a_start < b_end AND COALESCE(a_end, '9999-12-31') >= b_start

        This is more efficient and allows the optimizer to use precomputed columns.

        Args:
            left: The left interval expression (already translated to SQL)
            right: The right interval expression (already translated to SQL)
            expr: The original CQL binary expression

        Returns:
            Decomposed SQL expression, or None if decomposition not possible
        """
        # Extract bounds from both intervals
        # Handle case where expr might be None (for testing)
        cql_left = expr.left if expr is not None else None
        cql_right = expr.right if expr is not None else None
        left_bounds = self._extract_interval_bounds(left, cql_left)
        right_bounds = self._extract_interval_bounds(right, cql_right)

        if left_bounds is None or right_bounds is None:
            return None

        left_start, left_end, left_low_closed, left_high_closed = left_bounds
        right_start, right_end, right_low_closed, right_high_closed = right_bounds

        # This decomposition is DATE/TIMESTAMP-specific (uses COALESCE with
        # '9999-12-31' sentinel and CAST AS DATE).  Bail out for non-temporal
        # bounds (e.g., integer interval literals) and let the caller fall
        # through to the generic intervalOverlaps UDF.
        def _is_numeric_literal(e: SQLExpression) -> bool:
            return isinstance(e, SQLLiteral) and isinstance(e.value, (int, float))

        def _is_time_or_quantity_literal(e: SQLExpression) -> bool:
            """Detect time strings, Quantity JSON, and parse_quantity() calls that can't be CAST AS DATE."""
            if isinstance(e, SQLFunctionCall) and e.name == "parse_quantity":
                return True
            if isinstance(e, SQLLiteral) and isinstance(e.value, str):
                v = e.value
                # Time strings: "10:00:00.000", "T10:00"
                if v.startswith('T') or (len(v) <= 16 and ':' in v and '-' not in v):
                    return True
                # Quantity JSON
                if v.startswith('{') and '"value"' in v:
                    return True
            return False

        all_bounds = [left_start, left_end, right_start, right_end]
        if any(_is_numeric_literal(b) for b in all_bounds if b is not None):
            return None
        if any(_is_time_or_quantity_literal(b) for b in all_bounds if b is not None):
            return None

        # Bail out for partial-precision date strings (e.g., '2012-02', '2013')
        # that cannot be CAST AS DATE. Let the intervalOverlaps UDF handle them.
        def _is_partial_date(e: SQLExpression) -> bool:
            if isinstance(e, SQLLiteral) and isinstance(e.value, str):
                v = e.value
                # Full date is at least YYYY-MM-DD (10 chars)
                if v and v[0].isdigit() and len(v) < 10:
                    return True
            return False

        if any(_is_partial_date(b) for b in all_bounds if b is not None):
            return None

        # Ensure interval bounds from fhirpath UDFs are cast consistently.
        # Use VARCHAR throughout to avoid DATE/VARCHAR type mismatches
        # (CQL datetime literals are now VARCHAR; FHIR values may be DATE).
        def _to_varchar(e: SQLExpression) -> SQLExpression:
            if e is None or isinstance(e, SQLNull):
                return e
            if isinstance(e, SQLLiteral) and isinstance(e.value, str):
                return e  # already VARCHAR
            if isinstance(e, SQLCast) and e.target_type == "VARCHAR":
                return e
            return SQLCast(expression=e, target_type="VARCHAR")

        left_start = _to_varchar(self._ensure_date_cast(left_start))
        left_end = _to_varchar(self._ensure_date_cast(left_end))
        right_start = _to_varchar(self._ensure_date_cast(right_start))
        right_end = _to_varchar(self._ensure_date_cast(right_end))

        # For overlaps, we need:
        # left.start < right.end (considering closedness) AND
        # left.end >= right.start (considering closedness)
        #
        # With NULL end (open-ended interval like active conditions):
        #   left_start < right_end AND COALESCE(left_end, '9999-12-31') >= right_start

        # Handle unbounded starts/ends.  The interval UDFs treat NULL low/high
        # bounds as unbounded; keep the optimized temporal SQL equivalent.
        # Use VARCHAR consistently to avoid type mismatches.
        left_start_coalesced = SQLFunctionCall(
            name="COALESCE",
            args=[
                (left_start if left_start and not isinstance(left_start, SQLNull) else SQLNull()),
                SQLLiteral(value="0001-01-01"),
            ]
        )
        right_start_coalesced = SQLFunctionCall(
            name="COALESCE",
            args=[
                (right_start if right_start and not isinstance(right_start, SQLNull) else SQLNull()),
                SQLLiteral(value="0001-01-01"),
            ]
        )
        # Always COALESCE left_end because prevalenceInterval().end can be NULL
        # for active conditions (no abatement date), and NULL >= X is NULL (false).
        left_end_coalesced = SQLFunctionCall(
            name="COALESCE",
            args=[
                (left_end if left_end and not isinstance(left_end, SQLNull) else SQLNull()),
                SQLLiteral(value="9999-12-31"),
            ]
        )
        # Also COALESCE right_end — if the right interval is open-ended
        # (e.g. active condition with no abatement), right_end is NULL and
        # left_start < NULL evaluates to NULL (falsy), incorrectly returning
        # no overlap.  Treat NULL as far-future so any left_start < far-future.
        right_end_coalesced = SQLFunctionCall(
            name="COALESCE",
            args=[
                (right_end if right_end and not isinstance(right_end, SQLNull) else SQLNull()),
                SQLLiteral(value="9999-12-31"),
            ]
        )

        # For [a, b) overlaps [c, d):
        # a < d (since d is exclusive) AND b >= c
        # If bounds are closed, adjust operators
        left_op = "<=" if right_high_closed else "<"
        right_op = ">=" if left_high_closed else ">"

        # Build the comparison: left_start < right_end
        # All bounds are VARCHAR — lexicographic comparison of ISO 8601 strings
        # preserves correct temporal ordering for full-precision dates.
        start_comparison = SQLBinaryOp(
            operator=left_op,
            left=left_start_coalesced,
            right=right_end_coalesced,
        )

        # Build the comparison: left_end >= right_start
        end_comparison = SQLBinaryOp(
            operator=right_op,
            left=left_end_coalesced,
            right=right_start_coalesced,
        )

        # Combine with AND
        return SQLBinaryOp(
            operator="AND",
            left=start_comparison,
            right=end_comparison,
        )

    def _ensure_resource_to_interval(
        self, sql_expr: SQLExpression, cql_expr
    ) -> SQLExpression:
        """Convert a bare resource alias to its primary date interval.

        When temporal operators like ``starts``/``ends`` receive a resource
        alias (e.g. ``TotalHip``), the translated SQL is
        ``TotalHip.resource`` — a full resource JSON.  UDFs like
        ``intervalStart`` cannot parse that.  This helper detects the
        situation and wraps the expression in a ``toInterval`` conversion
        using the resource type's primary date/period path.

        Returns the original expression unchanged if it is already an
        interval or if the resource type is unknown.
        """
        from ...parser.ast_nodes import Identifier

        if not isinstance(cql_expr, Identifier):
            return sql_expr
        alias_name = cql_expr.name

        # If the alias has a stored ast_expr (e.g., from a query's return
        # clause that already computes an interval), use it directly instead
        # of trying to convert the raw resource JSON.
        symbol = self.context.lookup_symbol(alias_name)
        if symbol and getattr(symbol, "ast_expr", None) is not None:
            _ast = symbol.ast_expr
            # Unwrap SQLSubquery to get the inner SQLSelect
            _inner = _ast
            if isinstance(_inner, SQLSubquery) and isinstance(
                _inner.query, SQLSelect
            ):
                _inner = _inner.query
            # If the inner SELECT has computed columns (not just * or resource),
            # it's a query return clause that already produces interval values.
            if isinstance(_inner, SQLSelect) and _inner.columns:
                _first_col = _inner.columns[0]
                if not (
                    isinstance(_first_col, SQLIdentifier)
                    and _first_col.name in ("*", "resource")
                ):
                    return _ast

        resource_type = getattr(self.context, "_alias_resource_types", {}).get(
            alias_name
        )
        if not resource_type:
            # Fallback: look up CTE name from the symbol table and infer
            # resource type from the CTE prefix (e.g., "Procedure: ..." → Procedure)
            symbol = self.context.lookup_symbol(alias_name)
            cte_name = getattr(symbol, "cte_name", None) if symbol else None
            if cte_name:
                for rt in self._RESOURCE_PRIMARY_DATE_PATHS:
                    if cte_name.startswith(f"{rt}:") or cte_name == rt:
                        resource_type = rt
                        break
        if not resource_type:
            # Fallback 2: Look up the definition's CQL AST to find the
            # resource type.  For ``define Enc: [Encounter]``, the CQL AST
            # is a Retrieve node with type='Encounter'.
            cql_asts = getattr(self.context, "_definition_cql_asts", {})
            def_cql = cql_asts.get(alias_name)
            if def_cql is not None:
                # Navigate to the Retrieve node (might be wrapped in other nodes)
                _node = def_cql
                from ...parser.ast_nodes import Retrieve
                if isinstance(_node, Retrieve):
                    resource_type = _node.type
        if not resource_type:
            # Fallback 3: Infer resource type from the SQL subquery.
            # For ``define Enc: [Encounter]``, the SQL is
            # ``(SELECT sub.resource FROM "Enc" AS sub ...)`` where CTE "Enc"
            # references CTE "Encounter".  Walk the CTE chain to find the
            # FHIR resource type.
            resource_type = self._infer_resource_type_from_sql(sql_expr, alias_name)
        if not resource_type:
            return sql_expr
        primary_path = self._RESOURCE_PRIMARY_DATE_PATHS.get(resource_type)
        if not primary_path:
            return sql_expr

        # Build toInterval-style CASE expression for choice-type paths
        # (e.g. performed -> performedPeriod or performedDateTime)
        if primary_path in self._KNOWN_CHOICE_PATHS:
            period_path = f"{primary_path}Period"
            datetime_path = f"{primary_path}DateTime"
            # CASE WHEN fhirpath_text(res, 'performedPeriod') IS NOT NULL
            #   THEN fhirpath_text(res, 'performedPeriod')   -- JSON interval
            #   ELSE intervalFromBounds(fhirpath_text(res, 'performedDateTime'),
            #                           fhirpath_text(res, 'performedDateTime'),
            #                           TRUE, TRUE)
            # END
            period_expr = SQLFunctionCall(
                name="fhirpath_text", args=[sql_expr, SQLLiteral(period_path)]
            )
            datetime_expr = SQLFunctionCall(
                name="fhirpath_text", args=[sql_expr, SQLLiteral(datetime_path)]
            )
            return SQLCase(
                when_clauses=[
                    (
                        SQLBinaryOp(
                            operator="IS NOT", left=period_expr, right=SQLNull()
                        ),
                        period_expr,
                    )
                ],
                else_clause=SQLFunctionCall(
                    name="intervalFromBounds",
                    args=[
                        datetime_expr,
                        datetime_expr,
                        SQLLiteral(True),
                        SQLLiteral(True),
                    ],
                ),
            )
        # Non-choice path (e.g. Encounter.period, Communication.sent)
        # Check if it's a known period property
        _PERIOD_PATHS = {"period", "billablePeriod"}
        if primary_path in _PERIOD_PATHS:
            return SQLFunctionCall(
                name="fhirpath_text", args=[sql_expr, SQLLiteral(primary_path)]
            )
        # Scalar date/dateTime — wrap as point interval
        scalar_expr = SQLFunctionCall(
            name="fhirpath_text", args=[sql_expr, SQLLiteral(primary_path)]
        )
        return SQLFunctionCall(
            name="intervalFromBounds",
            args=[scalar_expr, scalar_expr, SQLLiteral(True), SQLLiteral(True)],
        )

    def _infer_resource_type_from_sql(
        self, sql_expr: SQLExpression, alias_name: str
    ) -> Optional[str]:
        """Infer FHIR resource type from a SQL subquery expression.

        For ``define Enc: [Encounter]``, the generated SQL is
        ``(SELECT sub.resource FROM "Enc" AS sub ...)`` where the FROM
        CTE ``"Enc"`` ultimately references CTE ``"Encounter"`` (the
        resource-type CTE).  This method walks the CTE chain to find the
        FHIR resource type.

        Returns:
            Resource type string (e.g. ``"Encounter"``) or ``None``.
        """
        from ..types import SQLAlias, SQLQualifiedIdentifier

        if not isinstance(sql_expr, SQLSubquery):
            return None
        inner = sql_expr.query
        if not isinstance(inner, SQLSelect):
            return None

        # Check that the SELECT selects sub.resource (raw resource JSON)
        if not inner.columns or len(inner.columns) != 1:
            return None
        col = inner.columns[0]
        if isinstance(col, SQLAlias):
            col = col.expr
        is_resource_col = (
            (isinstance(col, SQLQualifiedIdentifier) and col.parts[-1] == "resource")
            or (isinstance(col, SQLIdentifier) and col.name == "resource")
        )
        if not is_resource_col:
            return None

        # Extract CTE name from FROM clause
        # Pattern: SQLAlias(expr=SQLIdentifier(name='Enc'), alias='sub')
        # The CTE name is in expr.name, not in alias (which is the table alias 'sub')
        from_clause = inner.from_clause
        cte_name = None
        if isinstance(from_clause, SQLAlias):
            inner_from = from_clause.expr
            if isinstance(inner_from, SQLIdentifier):
                cte_name = inner_from.name
        elif isinstance(from_clause, SQLIdentifier):
            cte_name = from_clause.name

        if not cte_name:
            return None

        # Strip quotes
        if cte_name.startswith('"') and cte_name.endswith('"'):
            cte_name = cte_name[1:-1]

        # Resolve CTE chain: "Enc" -> "Encounter" by looking up symbols
        visited = set()
        current_name = cte_name
        while current_name and current_name not in visited:
            visited.add(current_name)

            # Direct resource type match?
            if current_name in self._RESOURCE_PRIMARY_DATE_PATHS:
                return current_name

            # Check if this CTE references another CTE (via symbol or definition)
            sym = self.context.lookup_symbol(current_name)
            if sym:
                # Check sql_expr for the symbol - it might be SQLIdentifier pointing to another CTE
                sym_sql = getattr(sym, 'sql_expr', None)
                if isinstance(sym_sql, SQLIdentifier):
                    next_name = sym_sql.name
                    if next_name.startswith('"') and next_name.endswith('"'):
                        next_name = next_name[1:-1]
                    current_name = next_name
                    continue

                # Check cte_name attribute
                ref_cte = getattr(sym, 'cte_name', None)
                if ref_cte:
                    if ref_cte in self._RESOURCE_PRIMARY_DATE_PATHS:
                        return ref_cte
                    current_name = ref_cte
                    continue

            # Check definition ASTs for FROM references
            def_ast = getattr(self.context, 'expression_definitions', {}).get(current_name)
            if def_ast:
                break

            break

        return None

    def _is_fhir_interval_expression(self, expr: SQLExpression) -> bool:
        """Check if a SQL expression extracts a FHIR Period/interval property.

        FHIR Period properties (e.g. Encounter.period) return JSON objects
        like {"start":"...","end":"..."} from fhirpath_text(), not scalar dates.

        Also detects CASE expressions produced by ToInterval translation
        where one branch contains a fhirpath_text of a period property,
        intervalFromBounds() calls which always produce intervals, and
        SQLInterval AST nodes from CQL Interval literals.
        """
        # SQLInterval nodes from CQL Interval literals are always intervals
        if isinstance(expr, SQLInterval):
            return True
        if isinstance(expr, SQLFunctionCall):
            if expr.name == "fhirpath_text" and len(expr.args) >= 2:
                path_arg = expr.args[1]
                path_str = getattr(path_arg, "value", None) if isinstance(path_arg, SQLLiteral) else None
                if isinstance(path_str, str):
                    _FHIR_PERIOD_PROPERTIES = {"period", "effectivePeriod", "performedPeriod"}
                    return path_str in _FHIR_PERIOD_PROPERTIES
            # intervalFromBounds() always produces an interval
            if expr.name == "intervalFromBounds":
                return True
            if expr.name in ("intervalExcept", "intervalIntersect", "intervalUnion"):
                return True
            # DATE_TRUNC(precision, interval_expr) wraps an interval when
            # precision-of is applied — check the inner argument.
            if expr.name and expr.name.upper() == "DATE_TRUNC" and len(expr.args) >= 2:
                return self._is_fhir_interval_expression(expr.args[1])
            return False
        # CASE expressions from ToInterval: check THEN/ELSE branches
        if isinstance(expr, SQLCase):
            for _, result in expr.when_clauses:
                if self._is_fhir_interval_expression(result):
                    return True
            if expr.else_clause and self._is_fhir_interval_expression(expr.else_clause):
                return True
        # CAST wrapping an interval expression (e.g., CAST(intervalFromBounds(...) AS DATE))
        if isinstance(expr, SQLCast):
            return self._is_fhir_interval_expression(expr.expression)
        # SQLSubquery referencing a CTE whose definition is known to be an Interval type
        if isinstance(expr, SQLSubquery):
            query = expr.query
            if isinstance(query, SQLSelect) and query.from_clause is not None:
                from ...translator.types import SQLAlias
                from_node = query.from_clause
                cte_name = None
                if isinstance(from_node, SQLAlias) and isinstance(from_node.expr, SQLIdentifier):
                    cte_name = from_node.expr.name
                elif isinstance(from_node, SQLIdentifier):
                    cte_name = from_node.name
                if cte_name and getattr(self.context, 'definition_meta', None) is not None:
                    meta = self.context.definition_meta.get(cte_name)
                    if meta and meta.cql_type and (
                        meta.cql_type.startswith("Interval") or meta.cql_type == "Period"
                    ):
                        return True
        return False

    def _is_list_typed_ast(self, cql_expr) -> bool:
        """Return True when the CQL AST node is statically typed as a list."""
        from ...parser.ast_nodes import BinaryExpression, Identifier, Interval, ListExpression, Query, QuerySource, Retrieve, SingletonExpression, TupleExpression, UnaryExpression
        from ...translator.context import RowShape

        if cql_expr is None or isinstance(cql_expr, Interval):
            return False
        if isinstance(cql_expr, Retrieve):
            return False
        if isinstance(cql_expr, Query):
            sources = cql_expr.source if isinstance(cql_expr.source, list) else [cql_expr.source]
            source_pairs = []
            for source in sources:
                if isinstance(source, QuerySource):
                    source_pairs.append((source.alias, source.expression))
                else:
                    source_pairs.append((getattr(source, "alias", None), source))

            def _source_is_scalar_list(source_expr: object) -> bool:
                if isinstance(source_expr, Retrieve):
                    return False
                if isinstance(source_expr, ListExpression):
                    return True
                if isinstance(source_expr, Identifier):
                    ast_defs = getattr(self.context, "_definition_cql_asts", {})
                    ast_def = ast_defs.get(source_expr.name)
                    return ast_def is not None and ast_def is not source_expr and self._is_list_typed_ast(ast_def)
                return self._is_list_typed_ast(source_expr)

            if not source_pairs or not all(_source_is_scalar_list(source_expr) for _alias, source_expr in source_pairs):
                return False
            return_clause = getattr(cql_expr, "return_clause", None)
            return_expr = getattr(return_clause, "expression", return_clause)
            if isinstance(return_expr, TupleExpression):
                return False
            if return_expr is not None:
                return True
            return True
        if isinstance(cql_expr, ListExpression):
            return True
        if isinstance(cql_expr, BinaryExpression) and getattr(cql_expr, "operator", "") == "as":
            type_spec = getattr(cql_expr, "right", None)
            if type_spec is not None and "list" in str(type_spec).lower():
                return True
        if isinstance(cql_expr, SingletonExpression):
            source = cql_expr.source
            if isinstance(source, ListExpression):
                return any(self._is_list_typed_ast(element) for element in source.elements)
            infer_cql_type = getattr(self, "_infer_cql_type", None)
            if infer_cql_type is not None:
                try:
                    source_type = str(infer_cql_type(source))
                except Exception:
                    source_type = ""
                return source_type.startswith("List<List<")
        if (
            isinstance(cql_expr, UnaryExpression)
            and getattr(cql_expr, "operator", "") == "singleton from"
        ):
            source = cql_expr.operand
            if isinstance(source, ListExpression):
                return any(self._is_list_typed_ast(element) for element in source.elements)
            infer_cql_type = getattr(self, "_infer_cql_type", None)
            if infer_cql_type is not None:
                try:
                    source_type = str(infer_cql_type(source))
                except Exception:
                    source_type = ""
                return source_type.startswith("List<List<")

        if isinstance(cql_expr, Identifier):
            meta = getattr(self.context, "definition_meta", {}).get(cql_expr.name)
            if (
                meta
                and meta.shape == RowShape.PATIENT_SCALAR
                and str(meta.cql_type).startswith("List<")
            ):
                return True
            definition_asts = getattr(self.context, "_definition_cql_asts", {})
            ast_def = definition_asts.get(cql_expr.name)
            if ast_def is not None and ast_def is not cql_expr:
                if self._is_list_typed_ast(ast_def):
                    return True

        infer_cql_type = getattr(self, "_infer_cql_type", None)
        if infer_cql_type is not None:
            try:
                infer_row_shape = getattr(self, "_infer_row_shape", None)
                if infer_row_shape is not None and infer_row_shape(cql_expr) != RowShape.PATIENT_SCALAR:
                    return False
                return str(infer_cql_type(cql_expr)).startswith("List<")
            except Exception:
                return False
        return False

    def _is_single_list_expr(self, sql_expr: SQLExpression, cql_expr) -> bool:
        """Return True when a single operand represents a CQL list."""
        from ...parser.ast_nodes import ListExpression
        from ...translator.types import SQLArray
        if isinstance(sql_expr, SQLArray):
            return True
        if isinstance(cql_expr, ListExpression):
            return True
        if self._is_list_typed_ast(cql_expr):
            return True
        if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name in (
            'list_filter', 'list_concat', 'list_distinct', 'list_sort',
            'list_transform', 'Distinct', '"Distinct"', 'Tail',
            'CQLListDistinctEq', 'CQLListExceptEq', 'CQLListIntersectEq',
        ):
            return True
        return False

    def _is_list_operands(self, left: SQLExpression, right: SQLExpression, expr) -> bool:
        """Return True when at least one operand represents a CQL list (not interval).

        Used to route ``includes`` / ``included in`` / ``properly includes`` /
        ``properly included in`` to DuckDB list functions instead of interval
        UDFs.  The detection looks at the translated SQL (SQLArray) and falls
        back to the CQL AST node types.
        """
        from ...parser.ast_nodes import ListExpression, Interval
        from ...translator.types import SQLArray
        # If either side is an SQLArray or a CQL ListExpression, this is
        # a list operation (CQL overloads these operators for both types).
        if isinstance(left, SQLArray) or isinstance(right, SQLArray):
            return True
        if hasattr(expr, 'left') and isinstance(expr.left, ListExpression):
            return True
        if hasattr(expr, 'right') and isinstance(expr.right, ListExpression):
            return True
        if hasattr(expr, 'left') and self._is_list_typed_ast(expr.left):
            return True
        if hasattr(expr, 'right') and self._is_list_typed_ast(expr.right):
            return True
        # If neither side is an interval, but both look like arrays, treat as list
        if hasattr(expr, 'left') and hasattr(expr, 'right'):
            if not isinstance(expr.left, Interval) and not isinstance(expr.right, Interval):
                if isinstance(left, SQLFunctionCall) and left.name in ('list_filter', 'list_concat', 'list_distinct'):
                    return True
                if isinstance(left, SQLFunctionCall) and left.name in ('CQLListDistinctEq', 'CQLListExceptEq', 'CQLListIntersectEq', '"Distinct"'):
                    return True
                if isinstance(right, SQLFunctionCall) and right.name in ('list_filter', 'list_concat', 'list_distinct'):
                    return True
                if isinstance(right, SQLFunctionCall) and right.name in ('CQLListDistinctEq', 'CQLListExceptEq', 'CQLListIntersectEq', '"Distinct"'):
                    return True
        return False

    def _extract_interval_bounds(
        self,
        sql_expr: SQLExpression,
        cql_expr: Any,
    ) -> Optional[tuple]:
        """
        Extract start and end bounds from an interval expression.

        Handles:
        - SQLInterval objects
        - intervalFromBounds() UDF calls
        - Interval literals in CQL
        - Parameter references (like "Measurement Period")

        Args:
            sql_expr: The translated SQL expression
            cql_expr: The original CQL expression

        Returns:
            Tuple of (start, end, low_closed, high_closed) or None if not extractable
        """
        # Case 1: SQLInterval literal
        if isinstance(sql_expr, SQLInterval):
            return (
                sql_expr.low,
                sql_expr.high,
                sql_expr.low_closed,
                sql_expr.high_closed,
            )

        # Case 2: SQLCase with intervalFromBounds in branches (from prevalenceInterval)
        if isinstance(sql_expr, SQLCase):
            # CASE expressions have conditional bounds — different branches may
            # have different start/end values (e.g. prevalenceInterval with
            # abatementDateTime in one branch and NULL in another).  Decomposing
            # picks one branch's bounds unconditionally, losing the conditionality.
            # Always bail out so callers use intervalStart/intervalEnd on the
            # whole CASE, which correctly evaluates the right branch at runtime.
            return None

        # Case 3: intervalFromBounds() UDF call
        if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name == "intervalFromBounds":
            if len(sql_expr.args) >= 2:
                low = sql_expr.args[0]
                high = sql_expr.args[1]
                low_closed = sql_expr.args[2] if len(sql_expr.args) > 2 else SQLLiteral(True)
                high_closed = sql_expr.args[3] if len(sql_expr.args) > 3 else SQLLiteral(False)

                # Convert literal booleans
                low_closed_bool = True
                high_closed_bool = False
                if isinstance(low_closed, SQLLiteral):
                    low_closed_bool = bool(low_closed.value)
                if isinstance(high_closed, SQLLiteral):
                    high_closed_bool = bool(high_closed.value)

                return (low, high, low_closed_bool, high_closed_bool)
            return None

        # Case 4: CQL Interval literal
        if isinstance(cql_expr, Interval):
            # Translate the bounds
            low = self.translate(cql_expr.low, usage=ExprUsage.SCALAR) if cql_expr.low else None
            high = self.translate(cql_expr.high, usage=ExprUsage.SCALAR) if cql_expr.high else None
            return (low, high, cql_expr.low_closed, cql_expr.high_closed)

        # Case 5: Parameter reference or identifier that resolves to an interval
        if isinstance(cql_expr, (Identifier, QualifiedIdentifier)):
            name = cql_expr.name if isinstance(cql_expr, Identifier) else cql_expr.parts[-1]
            # Generic interval parameter binding lookup
            binding = self.context.get_parameter_binding(name)
            interval_parts = self._interval_parameter_binding_parts(binding)
            if interval_parts is not None:
                b_start, b_end, low_closed, high_closed = interval_parts
                is_dt = getattr(self.context.lookup_symbol(name), "cql_type", None)
                is_dt = bool(is_dt and "DateTime" in str(is_dt))
                cast_type = "TIMESTAMP" if is_dt else "DATE"
                start = SQLCast(
                    expression=self._interval_parameter_bound_sql(
                        b_start,
                        is_datetime=is_dt,
                        is_high=False,
                    ),
                    target_type=cast_type,
                )
                end = SQLCast(
                    expression=self._interval_parameter_bound_sql(
                        b_end,
                        is_datetime=is_dt,
                        is_high=True,
                    ),
                    target_type=cast_type,
                )
                return (start, end, low_closed, high_closed)
            # For intervalFromBounds SQL nodes, extract directly
            if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name == "intervalFromBounds" and len(sql_expr.args) >= 2:
                return (sql_expr.args[0], sql_expr.args[1], True, False)
            # Fallback: use intervalStart/intervalEnd functions
            start = SQLFunctionCall(name="intervalStart", args=[sql_expr])
            end = SQLFunctionCall(name="intervalEnd", args=[sql_expr])
            # intervalStart/intervalEnd return semantic effective bounds.
            # Even when the authored interval was half-open, callers comparing
            # against these helper results should use closed comparisons.
            return (start, end, True, True)

        # Case 6: Function call that might be intervalFromBounds wrapped in COALESCE
        if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name == "COALESCE":
            # Try to extract from first non-null arg
            for arg in sql_expr.args:
                bounds = self._extract_interval_bounds(arg, None)
                if bounds:
                    return bounds

        return None

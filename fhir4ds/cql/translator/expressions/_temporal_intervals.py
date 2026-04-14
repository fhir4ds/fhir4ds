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

        # Ensure interval bounds from fhirpath UDFs are cast to DATE
        # fhirpath_date/fhirpath_text and COALESCE of those return VARCHAR
        left_start = self._ensure_date_cast(left_start)
        left_end = self._ensure_date_cast(left_end)
        right_start = self._ensure_date_cast(right_start)
        right_end = self._ensure_date_cast(right_end)

        # For overlaps, we need:
        # left.start < right.end (considering closedness) AND
        # left.end >= right.start (considering closedness)
        #
        # For [left_start, left_end) overlaps [right_start, right_end):
        #   left_start < right_end AND left_end >= right_start
        #
        # With NULL end (open-ended interval like active conditions):
        #   left_start < right_end AND COALESCE(left_end, '9999-12-31') >= right_start

        # Handle the end comparison - use COALESCE for NULL handling
        # Always COALESCE left_end because prevalenceInterval().end can be NULL
        # for active conditions (no abatement date), and NULL >= X is NULL (false)
        left_end_coalesced = SQLCast(
            expression=SQLFunctionCall(
                name="COALESCE",
                args=[
                    left_end if left_end and not isinstance(left_end, SQLNull) else SQLNull(),
                    SQLLiteral(value="9999-12-31"),
                ]
            ),
            target_type="DATE",
        )

        # For [a, b) overlaps [c, d):
        # a < d (since d is exclusive) AND b >= c
        # If bounds are closed, adjust operators
        left_op = "<=" if right_high_closed else "<"
        right_op = ">=" if left_low_closed else ">"

        # Build the comparison: left_start < right_end
        start_comparison = SQLBinaryOp(
            operator=left_op,
            left=left_start,
            right=right_end,
        )

        # Build the comparison: left_end >= right_start
        end_comparison = SQLBinaryOp(
            operator=right_op,
            left=left_end_coalesced,
            right=right_start,
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

    def _is_fhir_interval_expression(self, expr: SQLExpression) -> bool:
        """Check if a SQL expression extracts a FHIR Period/interval property.

        FHIR Period properties (e.g. Encounter.period) return JSON objects
        like {"start":"...","end":"..."} from fhirpath_text(), not scalar dates.

        Also detects CASE expressions produced by ToInterval translation
        where one branch contains a fhirpath_text of a period property,
        and intervalFromBounds() calls which always produce intervals.
        """
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
            return False
        # CASE expressions from ToInterval: check THEN/ELSE branches
        if isinstance(expr, SQLCase):
            for _, result in expr.when_clauses:
                if self._is_fhir_interval_expression(result):
                    return True
            if expr.else_clause and self._is_fhir_interval_expression(expr.else_clause):
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
            if binding is not None and isinstance(binding, tuple) and len(binding) == 2:
                b_start, b_end = binding
                p_start = b_start or "{mp_start}"
                p_end = b_end or "{mp_end}"
                start = SQLCast(expression=SQLLiteral(value=p_start), target_type="DATE")
                end = SQLCast(expression=SQLLiteral(value=p_end), target_type="DATE")
                return (start, end, True, True)
            # For intervalFromBounds SQL nodes, extract directly
            if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name == "intervalFromBounds" and len(sql_expr.args) >= 2:
                return (sql_expr.args[0], sql_expr.args[1], True, False)
            # Fallback: use intervalStart/intervalEnd functions
            start = SQLFunctionCall(name="intervalStart", args=[sql_expr])
            end = SQLFunctionCall(name="intervalEnd", args=[sql_expr])
            return (start, end, True, False)

        # Case 6: Function call that might be intervalFromBounds wrapped in COALESCE
        if isinstance(sql_expr, SQLFunctionCall) and sql_expr.name == "COALESCE":
            # Try to extract from first non-null arg
            for arg in sql_expr.args:
                bounds = self._extract_interval_bounds(arg, None)
                if bounds:
                    return bounds

        return None

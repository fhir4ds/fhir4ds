"""Temporal comparison operator translations for CQL to SQL.

Handles same/during/on-or-before/on-or-after/starts/ends/within operators
and complex interval temporal comparisons with quantity offsets.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...translator.context import ExprUsage
from ...translator.types import (
    SQLBinaryOp,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLIntervalLiteral,
    SQLLiteral,
    SQLNull,
    SQLUnaryOp,
)

from ...parser.ast_nodes import FunctionRef
from ...parser.ast_nodes import Interval as IntervalAst
from ...parser.ast_nodes import Literal as LiteralAst
from ...parser.ast_nodes import UnaryExpression

if TYPE_CHECKING:
    from ...parser.ast_nodes import BinaryExpression

_NUMERIC_POINT_KINDS = {"Integer", "Long", "Decimal"}

# Unary operators that extract a scalar from an interval operand; the
# result point type is the interval's point type (CQL §19.19 Start,
# §19.15 End, §19.22 Point From, §19.25 Width). Size (§19.18) is a
# FunctionRef handled alongside these.
_INTERVAL_SCALAR_OPERATORS = {"start of", "end of", "point from", "width of"}


class TemporalComparisonMixin:
    """Temporal comparison operator translations for CQL to SQL.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, ``_KNOWN_CHOICE_PATHS``, and the
    other helpers available on ExpressionTranslator.
    """

    def _numeric_interval_point_kind(self, expr) -> str | None:
        """Classify the point type of a no-precision same/same-or interval
        comparison when it is statically known to be NON-temporal.

        Returns "numeric" for Integer/Long/Decimal points (including mixed
        Integer/Decimal literals, which structural typing reports as
        Interval<Any>), "quantity" for Quantity points, and None when the
        operands are temporal or the point type cannot be determined
        statically (in which case the existing temporal lowering must be
        preserved).
        """
        if expr is None:
            return None
        for side in (getattr(expr, "left", None), getattr(expr, "right", None)):
            name = self._static_structural_type_name(side)
            if name and name.startswith("Interval<"):
                point = name[len("Interval<"):-1]
                if point in _NUMERIC_POINT_KINDS:
                    return "numeric"
                if point == "Quantity":
                    return "quantity"
                if point in ("Date", "DateTime", "Time"):
                    return None
                # Interval<Any> or unknown point type: peek at literal
                # bounds — a numeric/Quantity literal bound can never be a
                # temporal interval.
                if isinstance(side, IntervalAst):
                    for bound in (side.low, side.high):
                        if isinstance(bound, LiteralAst) and getattr(bound, "value", None) is not None:
                            bound_type = (
                                getattr(bound, "type", None)
                                or self._static_structural_type_name(bound)
                            )
                            if bound_type in _NUMERIC_POINT_KINDS:
                                return "numeric"
                            if bound_type == "Quantity":
                                return "quantity"
                return None
        return None

    def _interval_scalar_point_kind(self, node) -> str | None:
        """Classify the point kind of an interval-derived scalar operand.

        ``start of``/``end of``/``point from``/``width of`` (unary) and
        ``Size`` (function) extract a scalar whose type is the interval's
        point type (CQL §19.19/§19.15/§19.22/§19.25/§19.18). Returns
        "numeric", "quantity", or None (temporal / not an interval scalar).
        Used by arithmetic dispatch so numeric interval scalars never route
        through temporal dateAddQuantity or raw SQL over VARCHAR
        (CQL-17 EXPLORER QA-001).
        """
        if node is None:
            return None
        operand = None
        if isinstance(node, UnaryExpression) and node.operator in _INTERVAL_SCALAR_OPERATORS:
            operand = node.operand
        elif (
            isinstance(node, FunctionRef)
            and getattr(node, "name", "") in ("Size", "size")
            and node.arguments
        ):
            operand = node.arguments[0]
        if operand is None:
            return None
        from ...parser.ast_nodes import BinaryExpression as _BinaryExpression

        return self._numeric_interval_point_kind(
            _BinaryExpression(operator="and", left=operand, right=None)
        )

    @staticmethod
    def _numeric_point_compare(
        left_value: SQLExpression, right_value: SQLExpression, sql_op: str, kind: str
    ) -> SQLExpression:
        """Compare two extracted interval boundary points with CQL §9
        Integer/Decimal/Quantity comparison semantics (never temporal)."""
        if kind == "quantity":
            return SQLFunctionCall(
                name="quantityCompare",
                args=[
                    SQLCast(expression=left_value, target_type="VARCHAR"),
                    SQLCast(expression=right_value, target_type="VARCHAR"),
                    SQLLiteral(value={"=": "==", ">=": ">=", "<=": "<="}[sql_op]),
                ],
            )
        return SQLBinaryOp(
            operator=sql_op,
            left=SQLCast(expression=left_value, target_type="DECIMAL(38,10)"),
            right=SQLCast(expression=right_value, target_type="DECIMAL(38,10)"),
        )

    def _translate_same_operator(
        self, operator: str, left: SQLExpression, right: SQLExpression, expr=None
    ) -> SQLExpression:
        """
        Translate same precision operators to SQL.

        Handles:
        - same day as -> DATE(x) = DATE(y)
        - same month as -> DATE_TRUNC('month', x) = DATE_TRUNC('month', y)
        - same year as -> DATE_TRUNC('year', x) = DATE_TRUNC('year', y)
        - same or before day of -> DATE(x) <= DATE(y)
        - same or after day of -> DATE(x) >= DATE(y)
        """

        # Pattern: same <precision> as OR same <precision> or before/after
        # Examples: "same day as", "same month as", "same or before", "same day or after"

        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        def _same_call(name: str, left_value: SQLExpression, right_value: SQLExpression, precision: str) -> SQLFunctionCall:
            return SQLFunctionCall(
                name=name,
                args=[
                    SQLCast(expression=left_value, target_type="VARCHAR"),
                    SQLCast(expression=right_value, target_type="VARCHAR"),
                    SQLLiteral(value=precision),
                ],
            )

        def _is_interval(value: SQLExpression) -> bool:
            return self._is_fhir_interval_expression(value)

        def _as_interval(value: SQLExpression) -> SQLExpression:
            return value if _is_interval(value) else self._point_as_interval(value)

        def _same_interval(precision: str) -> SQLExpression:
            left_interval = _as_interval(left)
            right_interval = _as_interval(right)
            starts_same = _same_call(
                "cqlSameAsP",
                SQLFunctionCall(name="intervalStart", args=[left_interval]),
                SQLFunctionCall(name="intervalStart", args=[right_interval]),
                precision,
            )
            ends_same = _same_call(
                "cqlSameAsP",
                SQLFunctionCall(name="intervalEnd", args=[left_interval]),
                SQLFunctionCall(name="intervalEnd", args=[right_interval]),
                precision,
            )
            return SQLBinaryOp(operator="AND", left=starts_same, right=ends_same)

        # Check for "same <precision> or before/after" patterns first
        # The CQL parser emits two forms depending on source syntax:
        #   "same month or before"      (from: same month or before X)
        #   "same or before month of"   (from: same or before month of X)
        # Both must map to the same precision-aware UDF.
        for precision in precisions:
            pattern_before = f"same {precision} or before"
            pattern_before_alt = f"same or before {precision} of"
            pattern_after = f"same {precision} or after"
            pattern_after_alt = f"same or after {precision} of"
            pattern_as = f"same {precision} as"
            pattern_as_alt = f"same as {precision} of"

            if operator == pattern_before or operator == pattern_before_alt:
                # CQL §19.16: Compare at specified precision with timezone
                # normalization. Returns null if either operand is coarser than
                # the specified precision (uncertain per CQL §18.4).
                left_value = SQLFunctionCall(name="intervalEnd", args=[left]) if _is_interval(left) else left
                right_value = SQLFunctionCall(name="intervalStart", args=[right]) if _is_interval(right) else right
                return _same_call("cqlSameOrBeforeP", left_value, right_value, precision)

            if operator == pattern_after or operator == pattern_after_alt:
                left_value = SQLFunctionCall(name="intervalStart", args=[left]) if _is_interval(left) else left
                right_value = SQLFunctionCall(name="intervalEnd", args=[right]) if _is_interval(right) else right
                return _same_call("cqlSameOrAfterP", left_value, right_value, precision)

            if operator == pattern_as or operator == pattern_as_alt:
                if _is_interval(left) or _is_interval(right):
                    return _same_interval(precision)
                return _same_call("cqlSameAsP", left, right, precision)

        # Handle generic "same or before/after" without precision.
        # CQL §9.25/§9.26: for interval operands, "the first interval starts
        # on or after the second one ends" (same or after) / "the first
        # interval ends on or before the second one starts" (same or before);
        # point operands are used directly. Comparisons then proceed at the
        # finest precision specified in either input (§19.16-17), returning
        # null when precision is insufficient to determine ordering.
        if operator == "same or before" or operator == "same or after":
            # CQL-17 HISTORIAN QA-002: §19.28/§19.29 apply to any point type.
            # Numeric (Integer/Long/Decimal) and Quantity interval bounds
            # must compare numerically — routing them through the temporal
            # UDFs returns NULL (native) or raises (Python) on decimal
            # strings like '1.0'. Temporal operands keep the temporal path.
            numeric_kind = self._numeric_interval_point_kind(expr)
            if operator == "same or before":
                left_value = SQLFunctionCall(name="intervalEnd", args=[left]) if _is_interval(left) else left
                right_value = SQLFunctionCall(name="intervalStart", args=[right]) if _is_interval(right) else right
                if numeric_kind:
                    return self._numeric_point_compare(left_value, right_value, "<=", numeric_kind)
                udf_name = "cqlSameOrBefore"
            else:
                left_value = SQLFunctionCall(name="intervalStart", args=[left]) if _is_interval(left) else left
                right_value = SQLFunctionCall(name="intervalEnd", args=[right]) if _is_interval(right) else right
                if numeric_kind:
                    return self._numeric_point_compare(left_value, right_value, ">=", numeric_kind)
                udf_name = "cqlSameOrAfter"
            return SQLFunctionCall(
                name=udf_name,
                args=[
                    SQLCast(expression=left_value, target_type="VARCHAR"),
                    SQLCast(expression=right_value, target_type="VARCHAR"),
                ],
            )

        if operator == "same as":
            # CQL 1.5 §8.12 (points) / §9.24 (intervals), no precision:
            # compare at the finest precision specified in either input,
            # null when uncertain. Intervals compare start AND end points.
            if _is_interval(left) or _is_interval(right):
                left_interval = _as_interval(left)
                right_interval = _as_interval(right)
                # CQL-17 HISTORIAN QA-001: §19.27 applies to any point type.
                # Numeric (Integer/Long/Decimal) and Quantity interval bounds
                # must compare with CQL §9 numeric/Quantity equality — the
                # temporal cqlDateTimeEqual path raises (Python) or returns
                # NULL (native) on decimal bound strings like '1.0'.
                numeric_kind = self._numeric_interval_point_kind(expr)
                if numeric_kind:
                    starts_same = self._numeric_point_compare(
                        SQLFunctionCall(name="intervalStart", args=[left_interval]),
                        SQLFunctionCall(name="intervalStart", args=[right_interval]),
                        "=",
                        numeric_kind,
                    )
                    ends_same = self._numeric_point_compare(
                        SQLFunctionCall(name="intervalEnd", args=[left_interval]),
                        SQLFunctionCall(name="intervalEnd", args=[right_interval]),
                        "=",
                        numeric_kind,
                    )
                    return SQLBinaryOp(operator="AND", left=starts_same, right=ends_same)
                starts_same = SQLFunctionCall(
                    name="cqlDateTimeEqual",
                    args=[
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalStart", args=[left_interval]),
                            target_type="VARCHAR",
                        ),
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalStart", args=[right_interval]),
                            target_type="VARCHAR",
                        ),
                    ],
                )
                ends_same = SQLFunctionCall(
                    name="cqlDateTimeEqual",
                    args=[
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalEnd", args=[left_interval]),
                            target_type="VARCHAR",
                        ),
                        SQLCast(
                            expression=SQLFunctionCall(name="intervalEnd", args=[right_interval]),
                            target_type="VARCHAR",
                        ),
                    ],
                )
                return SQLBinaryOp(operator="AND", left=starts_same, right=ends_same)
            return SQLFunctionCall(
                name="cqlDateTimeEqual",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )

        # Fallback: pass through as-is (should not reach here normally)
        return SQLBinaryOp(operator="=", left=left, right=right)

    def _translate_during_operator(
        self, operator: str, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression:
        """
        Translate during precision operators to SQL.

        Handles:
        - during day of -> DATE(x) BETWEEN DATE(START(y)) AND DATE(END(y))
        - during month of -> DATE_TRUNC('month', x) BETWEEN ...
        """
        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        for precision in precisions:
            pattern = f"during {precision} of"
            if operator == pattern:
                # Truncate the left side to the precision
                left_truncated = self._truncate_to_precision(left, precision)

                # Gap 11: Try to extract interval bounds for boundary-aware comparison
                right_bounds = self._extract_interval_bounds(right, None)
                if right_bounds:
                    right_start, right_end, low_closed, high_closed = right_bounds
                    start_truncated = self._truncate_to_precision(right_start, precision)
                    end_truncated = self._truncate_to_precision(right_end, precision)
                    start_op = ">=" if low_closed else ">"
                    end_op = "<=" if high_closed else "<"
                    return SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(operator=start_op, left=left_truncated, right=start_truncated),
                        right=SQLBinaryOp(operator=end_op, left=left_truncated, right=end_truncated),
                    )

                # Fallback: Get interval bounds with intervalStart/intervalEnd
                right_start = SQLFunctionCall(name="intervalStart", args=[right])
                right_end = SQLFunctionCall(name="intervalEnd", args=[right])
                start_truncated = self._truncate_to_precision(right_start, precision)
                end_truncated = self._truncate_to_precision(right_end, precision)
                # Handle NULL end bound (open-ended intervals like active conditions
                # without abatementDateTime): treat NULL as far-future so "during"
                # succeeds for any point after the start.
                end_coalesced = SQLFunctionCall(
                    name="COALESCE",
                    args=[end_truncated, SQLCast(expression=SQLLiteral("9999-12-31"), target_type="DATE")],
                )
                # intervalStart/intervalEnd return semantic bounds; use closed comparison
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator=">=", left=left_truncated, right=start_truncated),
                    right=SQLBinaryOp(operator="<=", left=left_truncated, right=end_coalesced),
                )

        # Default during (no precision) -> intervalIncludes for intervals, intervalContains for points
        left_is_interval = self._is_fhir_interval_expression(left)
        if left_is_interval:
            return SQLFunctionCall(name="intervalIncludes", args=[right, left])
        return SQLFunctionCall(name="intervalContains", args=[right, self._ensure_interval_varchar(left)])

    def _translate_on_or_before_operator(
        self, operator: str, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression:
        """
        Translate on or before operators to SQL.

        CQL §19.18:
        - T on or before Interval<T>: T <= start of Interval
        - Interval<T> on or before T: end of Interval <= T
        - Interval<T> on or before Interval<T>: end of X <= start of Y
        """
        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        for precision in precisions:
            pattern = f"on or before {precision} of"
            if operator == pattern:
                left_is_interval = self._is_fhir_interval_expression(left)
                right_is_interval = self._is_fhir_interval_expression(right)
                if left_is_interval or right_is_interval:
                    # For date/datetime intervals, extract bound + truncate.
                    # For time/quantity/numeric, delegate to UDF (bounds aren't
                    # castable to TIMESTAMP).
                    if self._is_time_or_quantity_literal(left) or self._is_time_or_quantity_literal(right):
                        l = left if left_is_interval else self._point_as_interval(left)
                        r = right if right_is_interval else self._point_as_interval(right)
                        return SQLFunctionCall(name="intervalOnOrBefore", args=[l, r])
                    left_bound = SQLFunctionCall(name="intervalEnd", args=[left]) if left_is_interval else left
                    right_bound = SQLFunctionCall(name="intervalStart", args=[right]) if right_is_interval else right
                    left_val = self._truncate_to_precision(left_bound, precision)
                    right_val = self._truncate_to_precision(right_bound, precision)
                    return SQLBinaryOp(operator="<=", left=left_val, right=right_val)
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                op = "<" if getattr(right, 'is_exclusive_boundary', False) else "<="
                return SQLBinaryOp(operator=op, left=left_truncated, right=right_truncated)

        left_is_interval = self._is_fhir_interval_expression(left)
        right_is_interval = self._is_fhir_interval_expression(right)
        if left_is_interval or right_is_interval:
            l = self._unwrap_precision_wrapper(left) if left_is_interval else self._point_as_interval(left)
            r = self._unwrap_precision_wrapper(right) if right_is_interval else self._point_as_interval(right)
            return SQLFunctionCall(name="intervalOnOrBefore", args=[l, r])

        op = "<" if getattr(right, 'is_exclusive_boundary', False) else "<="
        cast_type = self._infer_cast_type_for_comparison(left, right)
        if cast_type in ("TIMESTAMP", "DATE"):
            # CQL §19.15: SameOrBefore with precision-awareness
            udf_name = "cqlBefore" if op == "<" else "cqlSameOrBefore"
            return SQLFunctionCall(
                name=udf_name,
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )
        return SQLBinaryOp(
            operator=op,
            left=self._ensure_date_cast(left, cast_type),
            right=self._ensure_date_cast(right, cast_type),
        )

    def _translate_on_or_after_operator(
        self, operator: str, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression:
        """
        Translate on or after operators to SQL.

        CQL §19.17:
        - T on or after Interval<T>: T >= end of Interval
        - Interval<T> on or after T: start of Interval >= T
        - Interval<T> on or after Interval<T>: start of X >= end of Y
        """
        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        for precision in precisions:
            pattern = f"on or after {precision} of"
            if operator == pattern:
                left_is_interval = self._is_fhir_interval_expression(left)
                right_is_interval = self._is_fhir_interval_expression(right)
                if left_is_interval or right_is_interval:
                    if self._is_time_or_quantity_literal(left) or self._is_time_or_quantity_literal(right):
                        l = left if left_is_interval else self._point_as_interval(left)
                        r = right if right_is_interval else self._point_as_interval(right)
                        return SQLFunctionCall(name="intervalOnOrAfter", args=[l, r])
                    left_bound = SQLFunctionCall(name="intervalStart", args=[left]) if left_is_interval else left
                    right_bound = SQLFunctionCall(name="intervalEnd", args=[right]) if right_is_interval else right
                    left_val = self._truncate_to_precision(left_bound, precision)
                    right_val = self._truncate_to_precision(right_bound, precision)
                    return SQLBinaryOp(operator=">=", left=left_val, right=right_val)
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(operator=">=", left=left_truncated, right=right_truncated)

        left_is_interval = self._is_fhir_interval_expression(left)
        right_is_interval = self._is_fhir_interval_expression(right)
        if left_is_interval or right_is_interval:
            l = self._unwrap_precision_wrapper(left) if left_is_interval else self._point_as_interval(left)
            r = self._unwrap_precision_wrapper(right) if right_is_interval else self._point_as_interval(right)
            return SQLFunctionCall(name="intervalOnOrAfter", args=[l, r])

        cast_type = self._infer_cast_type_for_comparison(left, right)
        if cast_type in ("TIMESTAMP", "DATE"):
            return SQLFunctionCall(
                name="cqlSameOrAfter",
                args=[
                    SQLCast(expression=left, target_type="VARCHAR"),
                    SQLCast(expression=right, target_type="VARCHAR"),
                ],
            )
        return SQLBinaryOp(
            operator=">=",
            left=self._ensure_date_cast(left, cast_type),
            right=self._ensure_date_cast(right, cast_type),
        )

    def _translate_simple_starts_ends_temporal(
        self, operator: str, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression | None:
        """Translate simple starts/ends on or before/after operators with optional precision.

        Handles:
          - "starts on or before [<precision> of]"
          - "starts on or after [<precision> of]"
          - "ends on or before [<precision> of]"
          - "ends on or after [<precision> of]"

        Returns None if the operator doesn't match any of these patterns.
        """
        _patterns = {
            "starts on or before": ("intervalStart", "<="),
            "starts on or after": ("intervalStart", ">="),
            "ends on or before": ("intervalEnd", "<="),
            "ends on or after": ("intervalEnd", ">="),
        }

        for prefix, (func_name, cmp_op) in _patterns.items():
            if operator == prefix or operator.startswith(prefix + " "):
                # Extract optional precision from suffix (e.g. "day of" → "day")
                suffix = operator[len(prefix):].strip()
                precision = None
                if suffix.endswith(" of"):
                    precision = suffix[:-3].strip() or None
                elif suffix:
                    precision = suffix.strip() or None

                boundary_expr = SQLFunctionCall(name=func_name, args=[left])

                if getattr(right, 'is_exclusive_boundary', False) and cmp_op == "<=":
                    cmp_op = "<"

                # When the right operand is a FHIR interval (e.g. Period),
                # extract the appropriate bound for point-vs-interval comparison.
                # CQL: point on or before Interval → point <= start of Interval
                # CQL: point on or after Interval → point >= end of Interval
                right_resolved = right
                if self._is_fhir_interval_expression(right):
                    right_bound_fn = "intervalStart" if cmp_op in ("<=", "<") else "intervalEnd"
                    right_resolved = SQLFunctionCall(name=right_bound_fn, args=[right])

                left_cmp = self._truncate_to_precision(boundary_expr, precision) if precision else boundary_expr
                right_cmp = self._truncate_to_precision(right_resolved, precision) if precision else right_resolved

                # Without explicit precision, normalize FHIR temporal VARCHARs
                # to 23-char ISO 8601 (strip timezone suffixes) so bare <= / >=
                # works correctly at time boundaries (CQL §18.13).
                if not precision:
                    left_cmp = self._normalize_temporal_for_compare(left_cmp)
                    right_cmp = self._normalize_temporal_for_compare(right_cmp)

                return SQLBinaryOp(operator=cmp_op, left=left_cmp, right=right_cmp)

        return None

    def _translate_complex_interval_temporal(
        self, operator: str, left: SQLExpression, right: SQLExpression, boundary: str
    ) -> SQLExpression:
        """
        Translate complex temporal operators with quantity.

        Handles patterns like:
        - "starts 1 day or less on or after day of" - interval starts within 1 day after reference
        - "ends 1 day or more on or before day of" - interval ends at least 1 day before reference

        Args:
            operator: The full operator string (e.g., "starts 1 day or less on or after day of")
            left: The SQL expression for the quantity (Quantity(value, unit))
            right: The SQL expression for the reference point
            boundary: Either "start" or "end" depending on which interval boundary

        Returns:
            SQL expression for the complex temporal comparison.

        SQL Pattern:
            "starts 1 day or less on or after day of X" ->
                intervalStarts(interval, X) AND intervalWidth(interval) <= INTERVAL '1 day'

        NOTE (B7): Uses structured string parsing (no regex) to decompose temporal operator strings.
        """
        # Parse the operator string using structured decomposition (no regex)
        components = self._parse_temporal_operator_components(operator)

        if components is None:
            # Fallback: just do a simple comparison if we can't parse
            return SQLBinaryOp(operator="=", left=left, right=right)

        starts_or_ends = components["boundary_type"]
        quantity_value = components["quantity_value"]
        quantity_unit = components["quantity_unit"]
        less_or_more = components["constraint"]
        before_or_after = components["direction"]
        precision = components.get("precision")

        # The 'left' is the translated Quantity - we need to handle it
        # For now, we'll build the SQL directly since the quantity info is in the operator string

        # Build the interval literal for the quantity
        # DuckDB uses INTERVAL '1 day' syntax
        quantity_value_int = int(float(quantity_value))
        interval_literal = SQLIntervalLiteral(value=quantity_value_int, unit=quantity_unit)

        # Get the interval start or end function
        if boundary == "start":
            boundary_func = SQLFunctionCall(name="intervalStart", args=[right])
        else:
            boundary_func = SQLFunctionCall(name="intervalEnd", args=[right])

        # The core logic:
        # "starts 1 day or less on or after X" means:
        #   - the interval starts on or after X
        #   - AND the distance is at most 1 day (or less)
        # This simplifies to: the start is between X and X + 1 day
        #
        # "starts 1 day or more on or after X" means:
        #   - the interval starts at least 1 day after X
        # This simplifies to: the start >= X + 1 day

        # For "on or after" with "or less": start >= right AND start <= right + quantity
        # For "on or after" with "or more": start >= right + quantity
        # For "on or before" with "or less": start <= right AND start >= right - quantity
        # For "on or before" with "or more": start <= right - quantity

        # Apply precision truncation if specified
        if precision:
            right_for_compare = self._truncate_to_precision(right, precision)
        else:
            right_for_compare = right

        # intervalStart/End return VARCHAR; cast for DuckDB arithmetic.
        # Use TIMESTAMP for sub-day units to preserve time-of-day precision.
        cast_type = self._temporal_target_type(quantity_unit)
        right_for_compare = self._ensure_date_cast(right_for_compare, cast_type)
        boundary_func = self._ensure_date_cast(boundary_func, cast_type)

        # For INTERVAL arithmetic (+/-), DuckDB requires TIMESTAMP, not VARCHAR.
        right_for_arithmetic = self._cast_for_interval_arithmetic(right_for_compare)

        # When no precision qualifier, cast FHIR temporal VARCHARs through
        # TIMESTAMP so comparisons are temporal instead of lexicographic.
        if not precision:
            right_for_compare = self._normalize_temporal_for_compare(right_for_compare)
            boundary_func = self._normalize_temporal_for_compare(boundary_func)

        if before_or_after in ("on or after", "after"):
            if less_or_more == "exact":
                # Exact offset: boundary = right + quantity
                target = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=boundary_func, right=target)
            elif less_or_more == "or less":
                # start >= right AND start <= right + quantity
                lower_bound = right_for_compare
                upper_bound = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))

                if precision:
                    lower_bound = self._truncate_to_precision(lower_bound, precision)
                    upper_bound = self._truncate_to_precision(upper_bound, precision)

                # "after" is exclusive (>), "on or after" is inclusive (>=)
                lower_op = "<" if before_or_after == "after" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator=lower_op, left=lower_bound, right=boundary_func),
                    right=SQLBinaryOp(operator="<=", left=boundary_func, right=upper_bound),
                )
            else:  # or more
                # start >= right + quantity
                threshold = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    threshold = self._truncate_to_precision(threshold, precision)
                return SQLBinaryOp(operator="<=", left=threshold, right=boundary_func)

        else:  # on or before / before
            if less_or_more == "exact":
                # Exact offset: boundary = right - quantity
                target = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=boundary_func, right=target)
            elif less_or_more == "or less":
                # start <= right AND start >= right - quantity
                upper_bound = right_for_compare
                lower_bound = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))

                if precision:
                    lower_bound = self._truncate_to_precision(lower_bound, precision)
                    upper_bound = self._truncate_to_precision(upper_bound, precision)

                # "before" is exclusive (<), "on or before" is inclusive (<=)
                upper_op = "<" if before_or_after == "before" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator="<=", left=lower_bound, right=boundary_func),
                    right=SQLBinaryOp(operator=upper_op, left=boundary_func, right=upper_bound),
                )
            else:  # or more
                # start <= right - quantity
                threshold = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    threshold = self._truncate_to_precision(threshold, precision)
                return SQLBinaryOp(operator="<=", left=boundary_func, right=threshold)

    def _translate_complex_interval_temporal_with_interval(
        self, operator: str, interval_sql: SQLExpression, inner_expr: "BinaryExpression", boundary: str
    ) -> SQLExpression:
        """
        Translate complex temporal operators when we have the full interval.

        This handles the case where the parser creates:
        BinaryExpression(operator='starts', left=Interval, right=BinaryExpression(operator='starts 1 day or less...', ...))

        Args:
            operator: The inner operator string (e.g., "starts 1 day or less on or after day of")
            interval_sql: The SQL expression for the outer interval (already translated)
            inner_expr: The inner BinaryExpression containing Quantity and reference
            boundary: Either "start" or "end" depending on which interval boundary

        Returns:
            SQL expression for the complex temporal comparison.

        NOTE (B8): Uses structured string parsing (no regex) to decompose temporal operator strings.
        """
        from ...parser.ast_nodes import Quantity

        # Parse the operator string using structured decomposition (no regex)
        components = self._parse_temporal_operator_components(operator)

        if components is None:
            # Try bare temporal parsing (e.g., "92 days or more before")
            # The operator may still carry the "starts"/"ends" prefix from the
            # parser (e.g. "starts 92 days or more before").  Strip it so the
            # bare-temporal parser sees "92 days or more before".
            bare_op = operator
            for _prefix in ("starts ", "ends "):
                if bare_op.startswith(_prefix):
                    bare_op = bare_op[len(_prefix):]
                    break
            bare = self._parse_bare_temporal_operator(bare_op)
            if bare is not None:
                boundary_func = "intervalStart" if boundary == "start" else "intervalEnd"
                boundary_expr = SQLFunctionCall(name=boundary_func, args=[interval_sql])
                right_translated = self.translate(inner_expr.right, usage=ExprUsage.SCALAR)
                return self._translate_bare_temporal_operator(bare, boundary_expr, right_translated)
            # Fallback: return intervalStartsSame/intervalEndsSame as-is
            # Ensure both args are VARCHAR for the UDF
            right_sql = self.translate(inner_expr.right)
            left_arg = SQLCast(expression=interval_sql, target_type="VARCHAR") if isinstance(interval_sql, SQLCast) and interval_sql.target_type != "VARCHAR" else interval_sql
            right_arg = SQLCast(expression=right_sql, target_type="VARCHAR") if isinstance(right_sql, SQLCast) and right_sql.target_type != "VARCHAR" else right_sql
            if boundary == "start":
                return SQLFunctionCall(name="intervalStartsSame", args=[left_arg, right_arg])
            else:
                return SQLFunctionCall(name="intervalEndsSame", args=[left_arg, right_arg])

        starts_or_ends = components["boundary_type"]
        quantity_value = components["quantity_value"]
        quantity_unit = components["quantity_unit"]
        less_or_more = components["constraint"]
        before_or_after = components["direction"]
        precision = components.get("precision")

        # Translate the reference point (inner_expr.right)
        right_sql = self.translate(inner_expr.right)

        # Get the interval's start or end point
        if boundary == "start":
            interval_point = SQLFunctionCall(name="intervalStart", args=[interval_sql])
        else:
            interval_point = SQLFunctionCall(name="intervalEnd", args=[interval_sql])

        # Build the interval literal for the quantity
        quantity_value_int = int(float(quantity_value))
        interval_literal = SQLIntervalLiteral(value=quantity_value_int, unit=quantity_unit)

        # Apply precision truncation if specified
        if precision:
            right_for_compare = self._truncate_to_precision(right_sql, precision)
            interval_point_for_compare = self._truncate_to_precision(interval_point, precision)
        else:
            right_for_compare = right_sql
            interval_point_for_compare = interval_point

        # intervalStart/End return VARCHAR; cast for DuckDB arithmetic.
        # Use TIMESTAMP for sub-day units to preserve time-of-day precision.
        cast_type = self._temporal_target_type(quantity_unit)
        right_for_compare = self._ensure_date_cast(right_for_compare, cast_type)
        interval_point_for_compare = self._ensure_date_cast(interval_point_for_compare, cast_type)

        # For INTERVAL arithmetic (+/-), DuckDB requires TIMESTAMP, not VARCHAR.
        right_for_arithmetic = self._cast_for_interval_arithmetic(right_for_compare)

        # When no precision qualifier, cast FHIR temporal VARCHARs through
        # TIMESTAMP so comparisons are temporal instead of lexicographic.
        if not precision:
            right_for_compare = self._normalize_temporal_for_compare(right_for_compare)
            interval_point_for_compare = self._normalize_temporal_for_compare(interval_point_for_compare)

        if before_or_after in ("on or after", "after"):
            if less_or_more == "exact":
                target = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=interval_point_for_compare, right=target)
            elif less_or_more == "or less":
                lower_bound = right_for_compare
                upper_bound = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))

                if precision:
                    lower_bound = self._truncate_to_precision(lower_bound, precision)
                    upper_bound = self._truncate_to_precision(upper_bound, precision)

                lower_op = "<" if before_or_after == "after" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator=lower_op, left=lower_bound, right=interval_point_for_compare),
                    right=SQLBinaryOp(operator="<=", left=interval_point_for_compare, right=upper_bound),
                )
            else:  # or more
                threshold = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    threshold = self._truncate_to_precision(threshold, precision)
                return SQLBinaryOp(operator="<=", left=threshold, right=interval_point_for_compare)

        else:  # on or before / before
            if less_or_more == "exact":
                target = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=interval_point_for_compare, right=target)
            elif less_or_more == "or less":
                upper_bound = right_for_compare
                lower_bound = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))

                if precision:
                    lower_bound = self._truncate_to_precision(lower_bound, precision)
                    upper_bound = self._truncate_to_precision(upper_bound, precision)

                upper_op = "<" if before_or_after == "before" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator="<=", left=lower_bound, right=interval_point_for_compare),
                    right=SQLBinaryOp(operator=upper_op, left=interval_point_for_compare, right=upper_bound),
                )
            else:  # or more
                threshold = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
                if precision:
                    threshold = self._truncate_to_precision(threshold, precision)
                return SQLBinaryOp(operator="<=", left=interval_point_for_compare, right=threshold)

    def _translate_bare_temporal_operator(
        self, components: dict, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression:
        """
        Translate bare (non-starts/ends) CQL temporal quantifier operators to SQL.

        CQL semantics for point-level temporal quantifiers:
        - "A 42 weeks or less before B" → A is at most 42 weeks before B
          i.e., B - 42 weeks <= A <= B
        - "A 241 minutes or more before B" → A is at least 241 minutes before B
          i.e., A <= B - 241 minutes
        - "A 3 days or less after B" → A is at most 3 days after B
          i.e., B <= A <= B + 3 days
        - "A 60 days or more after B" → A is at least 60 days after B
          i.e., A >= B + 60 days
        - "on or before" / "on or after" variants are equivalent to "before" / "after"
          with inclusive boundaries.
        """
        quantity_value = components["quantity_value"]
        quantity_unit = components["quantity_unit"]
        constraint = components["constraint"]
        direction = components["direction"]
        precision = components.get("precision")

        quantity_value_int = int(float(quantity_value))
        interval_literal = SQLIntervalLiteral(value=quantity_value_int, unit=quantity_unit)

        # Choose cast type based on the quantity unit — sub-day needs TIMESTAMP
        cast_type = self._temporal_target_type(quantity_unit)

        # Apply precision truncation if specified
        if precision:
            left_cmp = self._ensure_date_cast(self._truncate_to_precision(left, precision), cast_type)
            right_cmp = self._ensure_date_cast(self._truncate_to_precision(right, precision), cast_type)
        else:
            left_cmp = self._ensure_date_cast(left, cast_type)
            right_cmp = self._ensure_date_cast(right, cast_type)

        # For INTERVAL arithmetic, DuckDB requires TIMESTAMP, not VARCHAR.
        right_for_arithmetic = self._cast_for_interval_arithmetic(right_cmp)

        # When no precision qualifier, cast FHIR temporal VARCHARs through
        # TIMESTAMP so comparisons are temporal instead of lexicographic.
        if not precision:
            left_cmp = self._normalize_temporal_for_compare(left_cmp)
            right_cmp = self._normalize_temporal_for_compare(right_cmp)

        # "before" and "on or before" both mean left <= right
        # "after" and "on or after" both mean left >= right
        is_before = direction in ("before", "on or before")

        # Truncate TIMESTAMP arithmetic results when an explicit precision
        # qualifier is given (e.g. "day of") so that VARCHAR comparison works
        # correctly against precision-truncated operands (CQL R1.5 §18.13).
        trunc_precision = precision

        if is_before:
            if constraint == "or less":
                lower = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
                if trunc_precision:
                    lower = self._truncate_to_precision(lower, trunc_precision)
                upper_op = "<" if direction == "before" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator="<=", left=lower, right=left_cmp),
                    right=SQLBinaryOp(operator=upper_op, left=left_cmp, right=right_cmp),
                )
            else:
                threshold = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
                if trunc_precision:
                    threshold = self._truncate_to_precision(threshold, trunc_precision)
                return SQLBinaryOp(operator="<=", left=left_cmp, right=threshold)
        else:
            # after / on or after
            if constraint == "or less":
                upper = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))
                if trunc_precision:
                    upper = self._truncate_to_precision(upper, trunc_precision)
                lower_op = "<" if direction == "after" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator=lower_op, left=right_cmp, right=left_cmp),
                    right=SQLBinaryOp(operator="<=", left=left_cmp, right=upper),
                )
            else:
                threshold = self._timestamp_arith_for_compare(
                    SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))
                if trunc_precision:
                    threshold = self._truncate_to_precision(threshold, trunc_precision)
                return SQLBinaryOp(operator=">=", left=left_cmp, right=threshold)

    def _translate_within_operator(
        self, components: dict, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression:
        """
        Translate CQL "within N unit of" to SQL.

        CQL semantics: "A within 60 days of B" → |A - B| <= 60 days
        SQL: B - 60 days <= A <= B + 60 days
        (i.e., A is within 60 days of B in either direction)
        """
        quantity_value_int = int(float(components["quantity_value"]))
        quantity_unit = components["quantity_unit"]
        interval_literal = SQLIntervalLiteral(value=quantity_value_int, unit=quantity_unit)

        cast_type = self._temporal_target_type(quantity_unit)
        left_cmp = self._ensure_date_cast(left, cast_type)
        right_cmp = self._ensure_date_cast(right, cast_type)

        right_for_arithmetic = self._cast_for_interval_arithmetic(right_cmp)

        # Cast FHIR temporal VARCHARs through TIMESTAMP so comparisons are
        # temporal instead of lexicographic.
        left_cmp = self._normalize_temporal_for_compare(left_cmp)

        lower = self._timestamp_arith_for_compare(
            SQLBinaryOp(operator="-", left=right_for_arithmetic, right=interval_literal))
        upper = self._timestamp_arith_for_compare(
            SQLBinaryOp(operator="+", left=right_for_arithmetic, right=interval_literal))

        return SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator="<=", left=lower, right=left_cmp),
            right=SQLBinaryOp(operator="<=", left=left_cmp, right=upper),
        )

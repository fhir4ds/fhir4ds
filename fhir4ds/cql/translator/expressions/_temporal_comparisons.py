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
)

if TYPE_CHECKING:
    from ...parser.ast_nodes import BinaryExpression


class TemporalComparisonMixin:
    """Temporal comparison operator translations for CQL to SQL.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, ``_KNOWN_CHOICE_PATHS``, and the
    other helpers available on ExpressionTranslator.
    """

    def _translate_same_operator(
        self, operator: str, left: SQLExpression, right: SQLExpression
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

        # Check for "same <precision> or before/after" patterns first
        for precision in precisions:
            pattern_before = f"same {precision} or before"
            pattern_after = f"same {precision} or after"
            pattern_as = f"same {precision} as"

            if operator == pattern_before:
                # same day or before -> DATE(x) <= DATE(y)
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(operator="<=", left=left_truncated, right=right_truncated)

            if operator == pattern_after:
                # same day or after -> DATE(x) >= DATE(y)
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(operator=">=", left=left_truncated, right=right_truncated)

            if operator == pattern_as:
                # same day as -> DATE(x) = DATE(y)
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(operator="=", left=left_truncated, right=right_truncated)

        # Handle generic "same or before/after" without precision (use day as default)
        if operator == "same or before":
            left_truncated = self._truncate_to_precision(left, "day")
            right_truncated = self._truncate_to_precision(right, "day")
            return SQLBinaryOp(operator="<=", left=left_truncated, right=right_truncated)

        if operator == "same or after":
            left_truncated = self._truncate_to_precision(left, "day")
            right_truncated = self._truncate_to_precision(right, "day")
            return SQLBinaryOp(operator=">=", left=left_truncated, right=right_truncated)

        if operator == "same as":
            left_truncated = self._truncate_to_precision(left, "day")
            right_truncated = self._truncate_to_precision(right, "day")
            return SQLBinaryOp(operator="=", left=left_truncated, right=right_truncated)

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

        Handles:
        - on or before -> x <= y
        - on or before day of -> DATE(x) <= DATE(y)
        """
        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        for precision in precisions:
            pattern = f"on or before {precision} of"
            if operator == pattern:
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                # Gap 18: If right is an exclusive boundary, use < instead of <=
                op = "<" if getattr(right, 'is_exclusive_boundary', False) else "<="
                return SQLBinaryOp(operator=op, left=left_truncated, right=right_truncated)

        # Default on or before
        # Gap 18: If right is an exclusive boundary, use < instead of <=
        op = "<" if getattr(right, 'is_exclusive_boundary', False) else "<="
        # Use TIMESTAMP to preserve time-of-day precision.  DuckDB promotes
        # plain Date values to midnight TIMESTAMP, so this is safe for both
        # Date and DateTime operands.
        return SQLBinaryOp(
            operator=op,
            left=self._ensure_date_cast(left, "TIMESTAMP"),
            right=self._ensure_date_cast(right, "TIMESTAMP"),
        )

    def _translate_on_or_after_operator(
        self, operator: str, left: SQLExpression, right: SQLExpression
    ) -> SQLExpression:
        """
        Translate on or after operators to SQL.

        Handles:
        - on or after -> x >= y
        - on or after day of -> DATE(x) >= DATE(y)
        """
        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        for precision in precisions:
            pattern = f"on or after {precision} of"
            if operator == pattern:
                left_truncated = self._truncate_to_precision(left, precision)
                right_truncated = self._truncate_to_precision(right, precision)
                return SQLBinaryOp(operator=">=", left=left_truncated, right=right_truncated)

        # Default on or after
        # Use TIMESTAMP to preserve time-of-day precision.
        return SQLBinaryOp(
            operator=">=",
            left=self._ensure_date_cast(left, "TIMESTAMP"),
            right=self._ensure_date_cast(right, "TIMESTAMP"),
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

        if before_or_after in ("on or after", "after"):
            if less_or_more == "exact":
                # Exact offset: boundary = right + quantity
                target = SQLBinaryOp(operator="+", left=right_for_compare, right=interval_literal)
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=boundary_func, right=target)
            elif less_or_more == "or less":
                # start >= right AND start <= right + quantity
                lower_bound = right_for_compare
                upper_bound = SQLBinaryOp(operator="+", left=right_for_compare, right=interval_literal)

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
                threshold = SQLBinaryOp(operator="+", left=right_for_compare, right=interval_literal)
                if precision:
                    threshold = self._truncate_to_precision(threshold, precision)
                return SQLBinaryOp(operator="<=", left=threshold, right=boundary_func)

        else:  # on or before / before
            if less_or_more == "exact":
                # Exact offset: boundary = right - quantity
                target = SQLBinaryOp(operator="-", left=right_for_compare, right=interval_literal)
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=boundary_func, right=target)
            elif less_or_more == "or less":
                # start <= right AND start >= right - quantity
                upper_bound = right_for_compare
                lower_bound = SQLBinaryOp(operator="-", left=right_for_compare, right=interval_literal)

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
                threshold = SQLBinaryOp(operator="-", left=right_for_compare, right=interval_literal)
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

        if before_or_after in ("on or after", "after"):
            if less_or_more == "exact":
                # Exact offset: interval_point = right + quantity
                target = SQLBinaryOp(operator="+", left=right_for_compare, right=interval_literal)
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=interval_point_for_compare, right=target)
            elif less_or_more == "or less":
                # start >= right AND start <= right + quantity
                # i.e., interval_point BETWEEN right AND right + quantity
                lower_bound = right_for_compare
                upper_bound = SQLBinaryOp(operator="+", left=right_for_compare, right=interval_literal)

                if precision:
                    lower_bound = self._truncate_to_precision(lower_bound, precision)
                    upper_bound = self._truncate_to_precision(upper_bound, precision)

                # "after" is exclusive (>), "on or after" is inclusive (>=)
                lower_op = "<" if before_or_after == "after" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator=lower_op, left=lower_bound, right=interval_point_for_compare),
                    right=SQLBinaryOp(operator="<=", left=interval_point_for_compare, right=upper_bound),
                )
            else:  # or more
                # interval_point >= right + quantity
                threshold = SQLBinaryOp(operator="+", left=right_for_compare, right=interval_literal)
                if precision:
                    threshold = self._truncate_to_precision(threshold, precision)
                return SQLBinaryOp(operator="<=", left=threshold, right=interval_point_for_compare)

        else:  # on or before / before
            if less_or_more == "exact":
                # Exact offset: interval_point = right - quantity
                target = SQLBinaryOp(operator="-", left=right_for_compare, right=interval_literal)
                if precision:
                    target = self._truncate_to_precision(target, precision)
                return SQLBinaryOp(operator="=", left=interval_point_for_compare, right=target)
            elif less_or_more == "or less":
                # interval_point <= right AND interval_point >= right - quantity
                # i.e., interval_point BETWEEN right - quantity AND right
                upper_bound = right_for_compare
                lower_bound = SQLBinaryOp(operator="-", left=right_for_compare, right=interval_literal)

                if precision:
                    lower_bound = self._truncate_to_precision(lower_bound, precision)
                    upper_bound = self._truncate_to_precision(upper_bound, precision)

                # "before" is exclusive (<), "on or before" is inclusive (<=)
                upper_op = "<" if before_or_after == "before" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator="<=", left=lower_bound, right=interval_point_for_compare),
                    right=SQLBinaryOp(operator=upper_op, left=interval_point_for_compare, right=upper_bound),
                )
            else:  # or more
                # interval_point <= right - quantity
                threshold = SQLBinaryOp(operator="-", left=right_for_compare, right=interval_literal)
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

        # "before" and "on or before" both mean left <= right
        # "after" and "on or after" both mean left >= right
        is_before = direction in ("before", "on or before")

        if is_before:
            if constraint == "or less":
                # "A N or less before B" → B - N <= A < B  (exclusive for "before")
                # "A N or less on or before B" → B - N <= A <= B  (inclusive)
                lower = SQLBinaryOp(operator="-", left=right_cmp, right=interval_literal)
                upper_op = "<" if direction == "before" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator="<=", left=lower, right=left_cmp),
                    right=SQLBinaryOp(operator=upper_op, left=left_cmp, right=right_cmp),
                )
            else:
                # "A N or more before B" → A <= B - N
                threshold = SQLBinaryOp(operator="-", left=right_cmp, right=interval_literal)
                return SQLBinaryOp(operator="<=", left=left_cmp, right=threshold)
        else:
            # after / on or after
            if constraint == "or less":
                # "A N or less after B" → B < A <= B + N  (exclusive for "after")
                # "A N or less on or after B" → B <= A <= B + N  (inclusive)
                upper = SQLBinaryOp(operator="+", left=right_cmp, right=interval_literal)
                lower_op = "<" if direction == "after" else "<="
                return SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(operator=lower_op, left=right_cmp, right=left_cmp),
                    right=SQLBinaryOp(operator="<=", left=left_cmp, right=upper),
                )
            else:
                # "A N or more after B" → A >= B + N
                threshold = SQLBinaryOp(operator="+", left=right_cmp, right=interval_literal)
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

        lower = SQLBinaryOp(operator="-", left=right_cmp, right=interval_literal)
        upper = SQLBinaryOp(operator="+", left=right_cmp, right=interval_literal)

        return SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator="<=", left=lower, right=left_cmp),
            right=SQLBinaryOp(operator="<=", left=left_cmp, right=upper),
        )

"""Shared temporal utilities and constants for CQL to SQL translation.

Provides helper methods used across all temporal sub-mixins: precision
truncation, date casting, interval detection, operator string parsing, etc.
"""
from __future__ import annotations

from ...parser.ast_nodes import (
    BinaryExpression,
    DateTimeLiteral,
    FunctionRef,
    UnaryExpression,
)
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
    SQLRaw,
    SQLSelect,
    SQLSubquery,
)

# Subset of operator map needed by temporal methods (comparison operators are identity-mapped).
BINARY_OPERATOR_MAP = {
    "=": "=",
    "!=": "!=",
    "<>": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
}


class TemporalUtilsMixin:
    """Shared utility methods and constants for temporal translations.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, ``_KNOWN_CHOICE_PATHS``, and the
    other helpers available on ExpressionTranslator.
    """

    @staticmethod
    def _strip_and_conditions(ast_node):
        """Strip mis-parsed AND conditions from temporal operator operands.

        The CQL parser sometimes mis-parses:
            starts before start of "MP" and not X
        as:
            starts(before(start of("MP" and not(X))))
        instead of:
            starts(before(start of("MP"))) and not(X)

        Also handles "precision of" wrappers, e.g.:
            starts before day of start of "MP" and Y
        parsed as:
            starts(before(precision of(day, start of("MP" and Y))))

        This walks through wrapper nodes to find the innermost operand,
        strips any AND chain, and returns
        (cleaned_node, extra_condition_ast_or_None).
        """
        _START_END_OPS = ("start", "end", "start of", "end of")

        # Walk through wrappers to find the innermost operand that might have AND
        # The chain can be:
        #   UnaryExpr("start of", X) or UnaryExpr("end of", X)
        #   BinaryExpr("precision of", precision_literal, inner)
        chain = []  # list of (type, node) for reconstruction
        current = ast_node

        while True:
            if isinstance(current, UnaryExpression) and current.operator in _START_END_OPS:
                chain.append(("unary", current))
                current = current.operand
            elif isinstance(current, BinaryExpression) and current.operator == "precision of":
                chain.append(("precision", current))
                current = current.right  # right side is the inner expression
            else:
                break

        # Now 'current' is the innermost operand that might contain AND
        if not isinstance(current, BinaryExpression) or current.operator != "and":
            return ast_node, None

        # Strip AND conditions
        actual_expr = current
        extra_conditions = []
        while isinstance(actual_expr, BinaryExpression) and actual_expr.operator == "and":
            extra_conditions.append(actual_expr.right)
            actual_expr = actual_expr.left

        # Rebuild the chain of wrappers with the cleaned operand
        result = actual_expr
        for wrapper_type, wrapper_node in reversed(chain):
            if wrapper_type == "unary":
                result = UnaryExpression(operator=wrapper_node.operator, operand=result)
            elif wrapper_type == "precision":
                result = BinaryExpression(
                    operator="precision of", left=wrapper_node.left, right=result
                )

        # Combine extra conditions
        extra_condition_ast = None
        for cond in reversed(extra_conditions):
            if extra_condition_ast is None:
                extra_condition_ast = cond
            else:
                extra_condition_ast = BinaryExpression(
                    operator="and", left=extra_condition_ast, right=cond
                )

        return result, extra_condition_ast

    @staticmethod
    def _is_cql_date_expression(node) -> bool:
        """Check if a CQL AST node produces a Date or DateTime value.

        Used to detect CQL Date +/- Integer arithmetic which requires year
        units per the CQL specification.
        """
        if isinstance(node, UnaryExpression) and node.operator in ('start of', 'end of'):
            return True
        if isinstance(node, FunctionRef) and node.name in ('DateTime', 'Date', 'Today', 'Now'):
            return True
        if isinstance(node, DateTimeLiteral):
            return True
        return False

    @staticmethod
    def _ensure_interval_varchar(arg: SQLExpression) -> SQLExpression:
        """Wrap arg in CAST(... AS VARCHAR) unless it's already clearly VARCHAR.

        Interval UDFs (intervalContains, intervalIncludes, etc.) have
        signature (VARCHAR, VARCHAR).  Point arguments extracted from
        FHIR resources via fhirpath may resolve to DATE or TIMESTAMP;
        an explicit cast ensures DuckDB can match the UDF signature.
        CAST(varchar AS VARCHAR) is a no-op so this is always safe.
        """
        # Already a function that returns VARCHAR — skip cast
        if isinstance(arg, SQLFunctionCall) and arg.name in (
            "intervalFromBounds", "intervalStart", "intervalEnd",
            "fhirpath_text", "intervalIntersect",
        ):
            return arg
        if isinstance(arg, SQLCast) and arg.target_type.upper() == "VARCHAR":
            return arg
        return SQLCast(expression=arg, target_type="VARCHAR")

    @staticmethod
    def _temporal_target_type(unit: str) -> str:
        """Return the appropriate SQL cast type for a temporal unit.

        Always uses TIMESTAMP to preserve time-of-day precision.  When
        operands are plain Date values DuckDB promotes them to midnight
        TIMESTAMP which keeps day-level semantics intact, while DateTime
        operands retain their time component for correct comparisons.
        """
        return "TIMESTAMP"

    @staticmethod
    def _infer_cast_type_for_comparison(left: SQLExpression, right: SQLExpression) -> str:
        """Infer the appropriate SQL cast type for comparing two CQL operands.

        CQL before/after/on-or-before/on-or-after apply to any ordered type,
        not only temporal types.  When an operand is a numeric literal we must
        cast the peer (typically an ``intervalStart``/``intervalEnd`` VARCHAR
        result) to a numeric type instead of TIMESTAMP.

        Returns one of ``"BIGINT"``, ``"DOUBLE"``, ``"VARCHAR"``, or ``"TIMESTAMP"``.
        """
        for expr in (left, right):
            if isinstance(expr, SQLLiteral):
                if isinstance(expr.value, int):
                    return "BIGINT"
                if isinstance(expr.value, float):
                    return "DOUBLE"
                # Decimal-like string literals (e.g., '2.5' from CQL decimal).
                # Only match strings containing a decimal point to avoid
                # misclassifying ISO 8601 year strings like '2012' as numeric.
                if isinstance(expr.value, str) and '.' in expr.value:
                    try:
                        float(expr.value)
                        return "DOUBLE"
                    except (ValueError, TypeError):
                        pass
            if isinstance(expr, SQLCast):
                if expr.target_type in ("INTEGER", "BIGINT", "DOUBLE", "DECIMAL"):
                    return expr.target_type if expr.target_type != "DECIMAL" else "DOUBLE"
            # Detect Quantity JSON patterns — should NOT be cast to TIMESTAMP
            if isinstance(expr, SQLFunctionCall):
                fn = expr.name.lower() if isinstance(expr.name, str) else ""
                if fn in ("intervalstart", "intervalend"):
                    # Check if the interval is constructed from numeric/quantity bounds
                    if expr.args:
                        inner = expr.args[0]
                        if isinstance(inner, SQLFunctionCall) and inner.name.lower() == "intervalfrombounds":
                            if inner.args:
                                bound = inner.args[0]
                                if isinstance(bound, SQLCast) and bound.target_type == "VARCHAR":
                                    inner_expr = bound.expression
                                    if isinstance(inner_expr, SQLLiteral):
                                        if isinstance(inner_expr.value, (int, float)):
                                            return "DOUBLE" if isinstance(inner_expr.value, float) or '.' in str(inner_expr.value) else "BIGINT"
                                        if isinstance(inner_expr.value, str):
                                            try:
                                                float(inner_expr.value)
                                                return "DOUBLE" if '.' in inner_expr.value else "BIGINT"
                                            except (ValueError, TypeError):
                                                pass
            # Raw SQL with numeric literal pattern
            if isinstance(expr, SQLRaw):
                raw = expr.raw_sql.strip()
                try:
                    float(raw)
                    return "DOUBLE" if '.' in raw else "BIGINT"
                except (ValueError, TypeError):
                    pass
        return "TIMESTAMP"

    def _ensure_date_cast(self, expr: SQLExpression, target_type: str = "DATE") -> SQLExpression:
        """Wrap a VARCHAR-returning expression in CAST(... AS <target_type>).

        For temporal types (DATE/TIMESTAMP), we now cast to VARCHAR to preserve
        precision information in ISO 8601 format.  For numeric types (BIGINT,
        DOUBLE), the original cast behaviour is preserved.

        Args:
            expr: The SQL expression to potentially wrap.
            target_type: "DATE", "TIMESTAMP", "VARCHAR", "BIGINT", "DOUBLE", etc.
        """
        if expr is None or isinstance(expr, SQLNull):
            return expr

        # Temporal types → VARCHAR to preserve precision
        if target_type in ("DATE", "TIMESTAMP"):
            target_type = "VARCHAR"

        if isinstance(expr, SQLCast):
            # If already cast to DATE or TIMESTAMP, re-cast to VARCHAR
            if expr.target_type in ("DATE", "TIMESTAMP"):
                return SQLCast(expression=expr.expression, target_type="VARCHAR")
            return expr  # already cast — respect existing type
        if isinstance(expr, SQLRaw):
            raw = expr.raw_sql
            if raw.startswith("DATE ") or raw.startswith("TIMESTAMP "):
                return expr  # already typed
        if isinstance(expr, SQLLiteral):
            if isinstance(expr.value, str):
                if target_type == "VARCHAR":
                    return expr  # already a string literal, no cast needed
                if len(expr.value) >= 8:
                    return SQLCast(expression=expr, target_type=target_type)
                return expr  # short string — no cast needed
        if isinstance(expr, SQLFunctionCall):
            if target_type == "VARCHAR":
                # Many UDFs already return VARCHAR; skip redundant cast
                fn_lower = (expr.name or "").lower()
                if fn_lower in (
                    "dateaddquantity", "datesubtractquantity",
                    "intervalstart", "intervalend",
                    "cqlsameoafter", "cqlsameorbefore", "cqlbefore", "cqlafter",
                    "cqldatetimeadd", "cqldatetimesubtract",
                    "fhirpath_date", "fhirpath_text",
                ):
                    return expr
            return SQLCast(expression=expr, target_type=target_type)
        if isinstance(expr, (SQLSubquery, SQLSelect)):
            return SQLCast(expression=expr, target_type=target_type)
        if isinstance(expr, SQLCase):
            if self._is_interval_case(expr):
                return SQLCast(
                    expression=SQLFunctionCall(name="intervalStart", args=[expr]),
                    target_type=target_type,
                )
            return SQLCast(expression=expr, target_type=target_type)
        # Catch-all: wrap any unhandled expression type (e.g., SQLBinaryOp
        # from INTERVAL arithmetic) in a CAST to the target type.
        if target_type == "VARCHAR":
            return SQLCast(expression=expr, target_type="VARCHAR")
        return SQLCast(expression=expr, target_type=target_type)

    @staticmethod
    def _timestamp_arith_to_varchar(expr: SQLExpression) -> SQLExpression:
        """Convert TIMESTAMP arithmetic result to 23-char ISO 8601 VARCHAR.

        Uses ``STRFTIME`` with millisecond precision to produce a
        consistent 23-character output (``2014-01-01T00:00:00.000``)
        regardless of whether the TIMESTAMP has sub-second components.
        This avoids length mismatches in bare VARCHAR comparisons
        against FHIR datetime strings that carry timezone suffixes.
        """
        return SQLFunctionCall(
            name="STRFTIME",
            args=[
                expr,
                SQLLiteral("%Y-%m-%dT%H:%M:%S.%g"),
            ],
        )

    @staticmethod
    def _normalize_temporal_for_compare(expr: SQLExpression) -> SQLExpression:
        """Normalize a temporal VARCHAR to 23-char ISO 8601 for bare comparison.

        FHIR datetime strings may carry timezone suffixes
        (``2027-05-01T02:00:00.000+00:00``, 29 chars) while TIMESTAMP
        arithmetic results are 23 chars.  Bare ``<=`` / ``>=`` between
        these produces wrong results at boundaries because VARCHAR
        comparison is lexicographic.  This normalizes by casting through
        TIMESTAMP (which strips the timezone) and formatting back to a
        consistent 23-character string.
        """
        return SQLFunctionCall(
            name="STRFTIME",
            args=[
                SQLCast(expression=expr, target_type="TIMESTAMP"),
                SQLLiteral("%Y-%m-%dT%H:%M:%S.%g"),
            ],
        )

    @staticmethod
    def _cast_for_interval_arithmetic(expr: SQLExpression) -> SQLExpression:
        """Cast a temporal VARCHAR to TIMESTAMP for INTERVAL arithmetic.

        DuckDB requires TIMESTAMP (not VARCHAR) for ``+ INTERVAL`` /
        ``- INTERVAL`` operations.  This wraps the expression in an explicit
        CAST(... AS TIMESTAMP) so the arithmetic succeeds.
        """
        if isinstance(expr, SQLCast) and expr.target_type == "TIMESTAMP":
            return expr
        return SQLCast(expression=expr, target_type="TIMESTAMP")

    @staticmethod
    def _parse_temporal_operator_components(operator: str) -> dict | None:
        """
        Parse a CQL temporal operator string into structured components.

        Uses deterministic string splitting instead of regex.

        Args:
            operator: e.g. "starts 1 day or less on or after day of"

        Returns:
            Dict with keys: boundary_type, quantity_value, quantity_unit,
            constraint, direction, precision (optional). Returns None if parsing fails.
        """
        tokens = operator.split()
        # Minimum: boundary(1) + value(1) + unit(1) + direction(1) = 4
        # (constraint "or less/more" is optional for exact offsets)
        if len(tokens) < 4:
            return None

        boundary_type = tokens[0]  # "starts" or "ends"
        if boundary_type not in ("starts", "ends"):
            return None

        # tokens[1] = quantity value, tokens[2] = unit
        quantity_value = tokens[1]
        # Validate it's a number
        try:
            float(quantity_value)
        except ValueError:
            return None
        quantity_unit = tokens[2]

        # Find "or less" / "or more" (optional — absent means exact offset)
        remaining = " ".join(tokens[3:])
        constraint = None
        for c in ("or less", "or more"):
            if remaining.startswith(c):
                constraint = c
                remaining = remaining[len(c):].strip()
                break
        # No "or less"/"or more" → exact offset (e.g. "ends 1 day after day of")
        if constraint is None:
            constraint = "exact"

        # Find "on or before" / "on or after" / bare "before" / "after"
        direction = None
        for d in ("on or before", "on or after", "before", "after"):
            if remaining.startswith(d):
                direction = d
                remaining = remaining[len(d):].strip()
                break
        if direction is None:
            return None

        # Optional precision: "<precision> of"
        precision = None
        if remaining.endswith(" of"):
            precision = remaining[:-3].strip()
        elif remaining:
            precision = remaining.strip() if remaining.strip() else None

        return {
            "boundary_type": boundary_type,
            "quantity_value": quantity_value,
            "quantity_unit": quantity_unit,
            "constraint": constraint,
            "direction": direction,
            "precision": precision if precision else None,
        }

    def _truncate_to_precision(self, expr: SQLExpression, precision: str) -> SQLExpression:
        """Truncate a temporal expression to the specified precision.

        CQL §18.2: DateTime values are compared at the finest common precision.
        Truncation is done via LEFT() on VARCHAR ISO 8601 strings, ensuring
        consistent format regardless of whether the input was originally a
        TIMESTAMP or a precision-preserving VARCHAR literal.

        Args:
            expr: The SQL expression to truncate.
            precision: The precision level (e.g., 'day', 'hour', 'month').

        Returns:
            SQL expression for the truncated value as VARCHAR.
        """
        precision_lower = precision.lower()

        # If the expression is an interval-producing CASE (from toInterval()),
        # extract the start point before truncating to a date/time precision.
        expr = self._unwrap_interval_case(expr)

        # Interval expressions: truncate each bound individually so that
        # precision-qualified comparisons (e.g., "included in day of Interval")
        # compare at the correct precision.
        if isinstance(expr, SQLInterval):
            new_low = (
                self._truncate_to_precision(expr.low, precision)
                if expr.low and not isinstance(expr.low, SQLNull)
                else expr.low
            )
            new_high = (
                self._truncate_to_precision(expr.high, precision)
                if expr.high and not isinstance(expr.high, SQLNull)
                else expr.high
            )
            return SQLInterval(
                low=new_low, high=new_high,
                low_closed=expr.low_closed, high_closed=expr.high_closed,
            )
        if isinstance(expr, SQLFunctionCall):
            fn_lower = (expr.name or "").lower()
            if fn_lower in (
                "intervalfrombounds", "intervalintersect",
                "collapse_intervals",
            ):
                return expr

        # Map CQL precision names to ISO 8601 string lengths.
        # Normalize space→T ensures consistent format from TIMESTAMP casts.
        # Time values ('T' prefix) have different lengths than DateTime.
        precision_lengths_dt = {
            'year': 4,          # YYYY
            'month': 7,         # YYYY-MM
            'week': 10,         # YYYY-MM-DD (week → truncate to day)
            'day': 10,          # YYYY-MM-DD
            'hour': 13,         # YYYY-MM-DDTHH
            'minute': 16,       # YYYY-MM-DDTHH:MM
            'second': 19,       # YYYY-MM-DDTHH:MM:SS
            'millisecond': 23,  # YYYY-MM-DDTHH:MM:SS.mmm
        }
        precision_lengths_time = {
            'hour': 3,          # THH
            'minute': 6,        # THH:MM
            'second': 9,        # THH:MM:SS
            'millisecond': 13,  # THH:MM:SS.mmm
        }

        dt_length = precision_lengths_dt.get(precision_lower)
        time_length = precision_lengths_time.get(precision_lower)

        if dt_length:
            # Build AST nodes instead of calling .to_sql() to avoid premature
            # placeholder resolution during translation.
            replace_expr = SQLFunctionCall(
                name="REPLACE",
                args=[SQLCast(expr, "VARCHAR"), SQLLiteral(' '), SQLLiteral('T')],
            )
            if time_length:
                # Must handle both Time and DateTime values
                return SQLCase(
                    when_clauses=[
                        (
                            SQLBinaryOp(
                                operator="=",
                                left=SQLFunctionCall(name="SUBSTR", args=[replace_expr, SQLLiteral(1), SQLLiteral(1)]),
                                right=SQLLiteral('T'),
                            ),
                            SQLFunctionCall(name="LEFT", args=[replace_expr, SQLLiteral(time_length)]),
                        ),
                    ],
                    else_clause=SQLFunctionCall(name="LEFT", args=[replace_expr, SQLLiteral(dt_length)]),
                )
            return SQLFunctionCall(name="LEFT", args=[replace_expr, SQLLiteral(dt_length)])

        # Unknown precision - return as-is
        return expr

    @staticmethod
    def _cast_for_date_trunc(expr: SQLExpression, precision: str) -> SQLExpression:
        """Ensure *expr* is typed before passing to ``date_trunc``.

        DuckDB's ``date_trunc`` only supports DATE, TIMESTAMP, TIMESTAMPTZ,
        and INTERVAL — **not** TIME.  This helper adds explicit casts and,
        for time-only values, anchors them to ``1970-01-01`` so they become
        a valid TIMESTAMP that ``date_trunc`` can handle.

        For bare integer year literals (e.g. ``2003``), the value is turned
        into a ``make_timestamp(year, 1, 1, 0, 0, 0)`` call.
        """
        if isinstance(expr, SQLCast):
            # If already cast to TIME, re-anchor as TIMESTAMP
            if expr.target_type and expr.target_type.upper() == "TIME":
                # '1970-01-01 ' || CAST(x AS VARCHAR) → TIMESTAMP
                return SQLCast(
                    expression=SQLBinaryOp(
                        operator="||",
                        left=SQLLiteral(value="1970-01-01 "),
                        right=SQLCast(expression=expr, target_type="VARCHAR"),
                    ),
                    target_type="TIMESTAMP",
                )
            return expr  # already has an explicit non-TIME type
        if isinstance(expr, SQLLiteral):
            if isinstance(expr.value, (int, float)):
                # Bare year literal like 2003 → make_timestamp(2003,1,1,0,0,0)
                return SQLFunctionCall(
                    name="make_timestamp",
                    args=[
                        SQLLiteral(value=int(expr.value)),
                        SQLLiteral(value=1), SQLLiteral(value=1),
                        SQLLiteral(value=0), SQLLiteral(value=0), SQLLiteral(value=0),
                    ],
                )
            if isinstance(expr.value, str):
                val = expr.value.strip()
                # CQL Time values: ' 14:30:00' or 'T14:30:00' — no date part
                if len(val) <= 15 and ':' in val and '-' not in val:
                    # Anchor to 1970-01-01 so date_trunc works
                    anchored = "1970-01-01 " + val.lstrip("T").strip()
                    return SQLCast(
                        expression=SQLLiteral(value=anchored),
                        target_type="TIMESTAMP",
                    )
                # Everything else — datetime / date string → TIMESTAMP
                return SQLCast(expression=expr, target_type="TIMESTAMP")
        # Function calls returning VARCHAR or TIME
        if isinstance(expr, SQLFunctionCall):
            fn_lower = (expr.name or "").lower()
            # make_time returns TIME — anchor to 1970-01-01 for date_trunc
            if fn_lower == "make_time":
                return SQLCast(
                    expression=SQLBinaryOp(
                        operator="||",
                        left=SQLLiteral(value="1970-01-01 "),
                        right=SQLCast(expression=expr, target_type="VARCHAR"),
                    ),
                    target_type="TIMESTAMP",
                )
            # intervalStart/intervalEnd return VARCHAR which may be a time
            # string, quantity JSON, or numeric — use TRY_CAST to avoid
            # errors on non-temporal values
            if fn_lower in ("intervalstart", "intervalend"):
                return SQLRaw(f"TRY_CAST(({expr.to_sql()}) AS TIMESTAMP)")
            # Interval-returning functions should not be date_trunc'd —
            # they return JSON VARCHAR, not temporal values.
            if fn_lower in (
                "intervalfrombounds", "intervalintersect",
                "collapse_intervals", "intervalmeets", "intervalmeetsbefore",
                "intervalmeetsafter", "intervaloverlaps",
            ):
                return expr
            return SQLCast(expression=expr, target_type="TIMESTAMP")
        # Raw SQL or identifiers — try TIMESTAMP cast
        if isinstance(expr, (SQLRaw, SQLIdentifier)):
            return SQLCast(expression=expr, target_type="TIMESTAMP")
        return expr

    @staticmethod
    def _is_interval_case(expr: SQLExpression) -> bool:
        """Check if a SQLCase produces an interval (from toInterval())."""
        if not isinstance(expr, SQLCase):
            return False
        if expr.else_clause and isinstance(expr.else_clause, SQLFunctionCall):
            if expr.else_clause.name == "intervalFromBounds":
                return True
        for _, when_result in (expr.when_clauses or []):
            if isinstance(when_result, SQLFunctionCall) and when_result.name == "intervalFromBounds":
                return True
        return False

    @classmethod
    def _unwrap_interval_case(cls, expr: SQLExpression) -> SQLExpression:
        """If expr is an interval-producing CASE, wrap with intervalStart()."""
        if cls._is_interval_case(expr):
            return SQLFunctionCall(name="intervalStart", args=[expr])
        return expr

    @staticmethod
    def _parse_bare_temporal_operator(operator: str) -> dict | None:
        """
        Parse a bare (non-starts/ends) CQL temporal quantifier operator.

        Handles patterns like:
        - "42 weeks or less before"
        - "241 minutes or more before"
        - "3 days or less after day of"
        - "90 days or less on or after"
        - "42 weeks or less on or before"

        Returns:
            Dict with keys: quantity_value, quantity_unit, constraint,
            direction, precision (optional). Returns None if not a bare temporal operator.
        """
        tokens = operator.split()
        if len(tokens) < 5:
            return None

        # tokens[0] = quantity value, tokens[1] = unit
        quantity_value = tokens[0]
        try:
            float(quantity_value)
        except ValueError:
            return None
        quantity_unit = tokens[1]

        # Find "or less" / "or more" starting at tokens[2]
        remaining = " ".join(tokens[2:])
        constraint = None
        for c in ("or less", "or more"):
            if remaining.startswith(c):
                constraint = c
                remaining = remaining[len(c):].strip()
                break
        if constraint is None:
            return None

        # Find direction: "on or before", "on or after", "before", "after"
        direction = None
        for d in ("on or before", "on or after", "before", "after"):
            if remaining.startswith(d):
                direction = d
                remaining = remaining[len(d):].strip()
                break
        if direction is None:
            return None

        # Optional precision: "<precision> of"
        precision = None
        if remaining.endswith(" of"):
            precision = remaining[:-3].strip()
        elif remaining:
            precision = remaining.strip() if remaining.strip() else None

        return {
            "quantity_value": quantity_value,
            "quantity_unit": quantity_unit,
            "constraint": constraint,
            "direction": direction,
            "precision": precision if precision else None,
        }

    @staticmethod
    def _parse_within_operator(operator: str) -> dict | None:
        """
        Parse a CQL "within N unit of" operator string.

        Handles: "within 60 days of", "within 3 months of", etc.

        Returns:
            Dict with keys: quantity_value, quantity_unit. Returns None if not a within operator.
        """
        if not operator.startswith("within ") or not operator.endswith(" of"):
            return None

        # "within 60 days of" → ["within", "60", "days", "of"]
        tokens = operator.split()
        if len(tokens) != 4:
            return None

        quantity_value = tokens[1]
        try:
            float(quantity_value)
        except ValueError:
            return None

        quantity_unit = tokens[2]
        return {
            "quantity_value": quantity_value,
            "quantity_unit": quantity_unit,
        }

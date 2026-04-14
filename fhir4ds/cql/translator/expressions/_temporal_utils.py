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
    SQLCase,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
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

    def _ensure_date_cast(self, expr: SQLExpression, target_type: str = "DATE") -> SQLExpression:
        """Wrap a VARCHAR-returning expression in CAST(... AS <target_type>).

        fhirpath_date, fhirpath_text, COALESCE of those, intervalStart/End,
        and dateAddQuantity/dateSubtractQuantity all return VARCHAR in DuckDB.
        When used in temporal comparisons they need a CAST.

        Args:
            expr: The SQL expression to potentially wrap.
            target_type: "DATE" (default) or "TIMESTAMP" for sub-day precision.
        """
        if expr is None or isinstance(expr, SQLNull):
            return expr
        if isinstance(expr, SQLCast):
            return expr  # already cast — respect existing type
        if isinstance(expr, SQLRaw):
            raw = expr.raw_sql
            if raw.startswith("DATE ") or raw.startswith("TIMESTAMP "):
                return expr  # already typed
        if isinstance(expr, SQLLiteral):
            if isinstance(expr.value, str) and len(expr.value) >= 8:
                return SQLCast(expression=expr, target_type=target_type)
        if isinstance(expr, SQLFunctionCall):
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
        return expr

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
        """
        Truncate an expression to the specified precision.

        Args:
            expr: The SQL expression to truncate.
            precision: The precision level (e.g., 'day', 'hour', 'month').

        Returns:
            SQL expression for the truncated value.
        """
        precision_lower = precision.lower()

        # If the expression is an interval-producing CASE (from toInterval()),
        # extract the start point before truncating to a date/time precision.
        expr = self._unwrap_interval_case(expr)

        if precision_lower == "day":
            # DuckDB doesn't support DATE(expr) for casting - use CAST(expr AS DATE)
            return SQLCast(expression=expr, target_type="DATE")
        elif precision_lower in ("year", "month", "week", "hour", "minute", "second", "millisecond"):
            return SQLFunctionCall(
                name="DATE_TRUNC",
                args=[SQLLiteral(value=precision_lower), expr],
            )
        else:
            # Unknown precision - return as-is
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

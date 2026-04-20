"""Duration and difference computation translations for CQL to SQL.

Handles years/months/days/hours between, duration of, and difference between.
"""
from __future__ import annotations

from typing import List

from ...parser.ast_nodes import (
    BinaryExpression,
    DifferenceBetween,
    DurationBetween,
    Literal,
)
from ...translator.context import ExprUsage
from ...translator.expressions._temporal_utils import BINARY_OPERATOR_MAP
from ...translator.types import (
    SQLBinaryOp,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLLiteral,
)


class DurationMixin:
    """Duration/difference computation translations for CQL to SQL.

    Intended to be mixed into ExpressionTranslator.  All methods assume
    ``self`` has ``translate``, ``context``, and the other helpers available
    on ExpressionTranslator.
    """

    def _translate_duration_between(self, node: DurationBetween, boolean_context: bool = False) -> SQLExpression:
        """Handle AST node: years between X and Y.

        CQL §22.21: DurationBetween may return uncertainty intervals when
        operand precision is coarser than the unit being measured.
        Uses cqlDurationBetween UDF (returns VARCHAR: int string or interval JSON).
        """
        from ...parser.ast_nodes import BinaryExpression as CQLBinaryExpr, Interval as CQLInterval

        # Detect absorbed "in Interval" on the right operand
        trailing_interval = None
        # Detect absorbed comparison operators (< 24, >= 10, etc.)
        trailing_comparison = None
        actual_right = node.operand_right
        if (isinstance(actual_right, CQLBinaryExpr)
                and actual_right.operator == 'in'
                and isinstance(actual_right.right, CQLInterval)):
            trailing_interval = actual_right.right
            actual_right = actual_right.left
        elif (isinstance(actual_right, CQLBinaryExpr)
                and actual_right.operator in ('<', '<=', '>', '>=', '=', '!=')):
            trailing_comparison = (actual_right.operator, actual_right.right)
            actual_right = actual_right.left

        left = self.translate(node.operand_left, usage=ExprUsage.SCALAR)
        right = self.translate(actual_right, usage=ExprUsage.SCALAR)
        unit = node.precision.lower()
        # Use uncertainty-aware UDF that returns VARCHAR (int or interval JSON)
        duration_expr = SQLFunctionCall(
            name="cqlDurationBetween",
            args=[
                SQLCast(expression=left, target_type="VARCHAR"),
                SQLCast(expression=right, target_type="VARCHAR"),
                SQLLiteral(value=unit),
            ],
        )

        if trailing_interval is not None:
            low = self.translate(trailing_interval.low, usage=ExprUsage.SCALAR)
            high = self.translate(trailing_interval.high, usage=ExprUsage.SCALAR)
            # cqlDurationBetween returns VARCHAR; cast to INTEGER for BETWEEN
            duration_int = SQLCast(expression=duration_expr, target_type="INTEGER", try_cast=True)
            return SQLBinaryOp(
                operator="BETWEEN",
                left=duration_int,
                right=SQLFunctionCall(name="__between_args__", args=[low, high]),
            )

        if trailing_comparison is not None:
            cmp_op, cmp_right_node = trailing_comparison
            cmp_right = self.translate(cmp_right_node, usage=ExprUsage.SCALAR)
            # Use uncertainty-aware comparison for three-valued logic
            return SQLFunctionCall(
                name="cqlUncertainCompare",
                args=[
                    duration_expr,
                    SQLCast(expression=cmp_right, target_type="VARCHAR"),
                    SQLLiteral(value=cmp_op),
                ],
            )

        return duration_expr

    def _translate_duration_of(self, precision_of_expr: BinaryExpression) -> SQLExpression:
        """Translate 'duration in <unit> of <interval>' to interval width computation.

        The parser produces:
          BinaryExpression(operator='precision of', left=Literal(unit), right=interval_expr)
        We translate to: UnitsBetween(intervalStart(interval), intervalEnd(interval))

        The parser may also absorb a trailing comparison, producing:
          right=BinaryExpression(operator='>=', left=actual_interval, right=Literal(24))
        In that case we emit: UnitsBetween(start, end) >= 24
        """
        precision_map = {
            'years': 'YearsBetween', 'months': 'MonthsBetween',
            'weeks': 'weeksBetween', 'days': 'DaysBetween',
            'hours': 'HoursBetween', 'minutes': 'MinutesBetween',
            'seconds': 'SecondsBetween', 'milliseconds': 'millisecondsBetween',
            'year': 'YearsBetween', 'month': 'MonthsBetween',
            'week': 'weeksBetween', 'day': 'DaysBetween',
            'hour': 'HoursBetween', 'minute': 'MinutesBetween',
            'second': 'SecondsBetween', 'millisecond': 'millisecondsBetween',
        }
        unit = precision_of_expr.left
        interval_expr = precision_of_expr.right
        unit_str = unit.value.lower() if isinstance(unit, Literal) else 'day'
        func_name = precision_map.get(unit_str, 'DaysBetween')

        # Check if the parser absorbed a trailing comparison (e.g., ">= 48")
        trailing_op = None
        trailing_right = None
        if (isinstance(interval_expr, BinaryExpression)
                and interval_expr.operator in ('>=', '<=', '>', '<', '=', '!=')):
            trailing_op = interval_expr.operator
            trailing_right = self.translate(interval_expr.right, usage=ExprUsage.SCALAR)
            interval_expr = interval_expr.left

        interval_sql = self.translate(interval_expr, usage=ExprUsage.SCALAR)
        start_sql = SQLFunctionCall(name="intervalStart", args=[interval_sql])
        end_sql = SQLFunctionCall(name="intervalEnd", args=[interval_sql])
        duration_sql = SQLFunctionCall(name=func_name, args=[start_sql, end_sql])

        if trailing_op is not None:
            sql_op_map = {'>=': '>=', '<=': '<=', '>': '>', '<': '<', '=': '=', '!=': '!='}
            return SQLBinaryOp(
                operator=sql_op_map[trailing_op],
                left=duration_sql,
                right=trailing_right,
            )
        return duration_sql

    def _translate_difference_between(self, node: DifferenceBetween, boolean_context: bool = False) -> SQLExpression:
        """Handle AST node: difference in years between X and Y.

        CQL §22.22: DifferenceBetween counts calendar boundary crossings,
        unlike DurationBetween which counts whole periods. Uses differenceIn*
        UDFs which return integers.

        Handles parser bug where trailing comparison operators are absorbed
        into the right operand (e.g., ``difference in months between X and Y > 5``).
        """
        from ...parser.ast_nodes import BinaryExpression as CQLBinaryExpr

        # Detect absorbed comparison operators (< 24, >= 10, etc.)
        trailing_comparison = None
        actual_right = node.operand_right
        if (isinstance(actual_right, CQLBinaryExpr)
                and actual_right.operator in ('<', '<=', '>', '>=', '=', '!=')):
            trailing_comparison = (actual_right.operator, actual_right.right)
            actual_right = actual_right.left

        precision_map = {
            'year': 'differenceInYears',
            'month': 'differenceInMonths',
            'week': 'differenceInWeeks',
            'day': 'differenceInDays',
            'hour': 'differenceInHours',
            'minute': 'differenceInMinutes',
            'second': 'differenceInSeconds',
            'millisecond': 'differenceInMilliseconds',
        }
        left = self.translate(node.operand_left, usage=ExprUsage.SCALAR)
        right = self.translate(actual_right, usage=ExprUsage.SCALAR)
        func_name = precision_map.get(node.precision.lower(), 'differenceInDays')
        left = SQLCast(expression=left, target_type="VARCHAR")
        right = SQLCast(expression=right, target_type="VARCHAR")
        diff_expr = SQLFunctionCall(name=func_name, args=[left, right])

        if trailing_comparison is not None:
            cmp_op, cmp_right_node = trailing_comparison
            cmp_right = self.translate(cmp_right_node, usage=ExprUsage.SCALAR)
            sql_cmp_op = {"<": "<", "<=": "<=", ">": ">", ">=": ">=", "=": "=", "!=": "!="}.get(cmp_op, cmp_op)
            return SQLBinaryOp(operator=sql_cmp_op, left=diff_expr, right=cmp_right)

        return diff_expr

    def _translate_duration_between_func(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """Translate a duration between function call."""
        name_lower = name.lower()

        unit_map = {
            "yearsbetween": "year",
            "monthsbetween": "month",
            "weeksbetween": "week",
            "daysbetween": "day",
            "hoursbetween": "hour",
            "minutesbetween": "minute",
            "secondsbetween": "second",
            "millisecondsbetween": "millisecond",
        }

        unit = unit_map.get(name_lower, "day")

        if len(args) >= 2:
            return SQLFunctionCall(
                name="date_diff",
                args=[SQLLiteral(value=unit), args[0], args[1]],
            )

        return SQLLiteral(value=0)

    def _translate_difference_between_func(self, name: str, args: List[SQLExpression]) -> SQLExpression:
        """Translate a difference between function call."""
        # Difference between counts boundary crossings, not whole periods
        # For now, use the same implementation as duration
        return self._translate_duration_between_func(name, args)

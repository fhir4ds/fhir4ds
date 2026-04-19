"""
SQL types for CQL to SQL translation.

This module defines dataclasses for representing generated SQL fragments
with proper precedence handling for parenthesization, as well as context
types for tracking translation state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .column_generation import (
    ColumnDefinition,
    build_column_definitions,
    get_default_property_paths,
)


# SQL reserved words that must be quoted when used as identifiers/aliases
_SQL_RESERVED_WORDS = {
    "NULL", "TRUE", "FALSE", "SELECT", "FROM", "WHERE",
    "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN",
    "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
    "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
    "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC",
    "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
    "DISTINCT", "ALL", "AS", "WITH", "RECURSIVE",
    "TYPE", "TABLE", "INDEX", "CREATE", "DROP", "ALTER",
    "INSERT", "UPDATE", "DELETE", "SET", "VALUES",
    "PRIMARY", "KEY", "REFERENCES", "CHECK", "DEFAULT",
    "CAST", "FILTER", "OVER", "PARTITION", "WINDOW",
    "CURRENT", "ROW", "ROWS", "RANGE", "INTERVAL",
}

# Operator precedence levels (higher = binds tighter)
PRECEDENCE = {
    # Set operators (lowest — standard SQL: INTERSECT > UNION/EXCEPT)
    "UNION": 0,  # UNION/UNION ALL
    "UNION_ALL": 0,
    "EXCEPT": 0,
    "INTERSECT": 1,  # INTERSECT binds tighter than UNION/EXCEPT
    # Logical operators (lowest)
    "OR": 2,
    "AND": 3,
    "NOT": 4,
    # Comparison operators
    "=": 5,
    "!=": 5,
    "<>": 5,
    "<": 5,
    "<=": 5,
    ">": 5,
    ">=": 5,
    "IS": 5,
    "IS NOT": 5,
    "IN": 5,
    "NOT IN": 5,
    "LIKE": 5,
    "BETWEEN": 5,
    # Additive operators
    "+": 6,
    "-": 6,
    "||": 6,  # String concatenation
    # Multiplicative operators
    "*": 7,
    "/": 7,
    "%": 7,
    # Unary operators
    "UNARY_MINUS": 8,
    "UNARY_PLUS": 8,
    # Function call, subscript
    "FUNCTION": 9,
    "SUBSCRIPT": 9,
    # Primary (highest)
    "PRIMARY": 11,
}


@dataclass
class SQLExpression:
    """
    Base class for SQL expression fragments.

    All SQL fragments inherit from this class to provide
    common interface for SQL generation.

    Note: precedence should be set by subclasses in __post_init__.
    """

    # Tracks half-open interval boundaries (e.g., "end of" produces exclusive upper bound)
    is_exclusive_boundary: bool = field(default=False, init=False, repr=False)

    # Optional type hint for the expression's result (e.g., "Quantity")
    result_type: Optional[str] = field(default=None, init=False, repr=False)

    # Class-level default, not a dataclass field
    @property
    def precedence(self) -> int:
        """Get precedence level for this expression."""
        return PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        """
        Generate SQL string for this expression.

        Args:
            parent_precedence: The precedence of the parent expression
                              (used to determine if parentheses are needed).

        Returns:
            The SQL string representation.
        """
        raise NotImplementedError("Subclasses must implement to_sql()")

    def needs_parentheses(self, parent_precedence: int) -> bool:
        """Check if this expression needs parentheses based on parent precedence."""
        return self.precedence < parent_precedence

    def is_date_typed(self) -> bool:
        """Check if this expression produces a DATE-typed value.

        Returns True for SQLCast(..., target_type="DATE") or SQLRaw containing
        a DATE literal (e.g. "DATE '2024-01-01'"). Used to detect when
        intervalFromBounds arguments need CAST to VARCHAR.
        """
        return False


@dataclass
class SQLLiteral(SQLExpression):
    """
    Represents a literal value in SQL.

    Examples:
        123
        'hello'
        TRUE
        NULL
    """

    value: Union[str, int, float, bool, None]
    sql_type: Optional[str] = None  # 'string', 'integer', 'decimal', 'boolean', 'null'
    precedence: int = field(default=PRECEDENCE["PRIMARY"], init=False)

    def __post_init__(self):
        self.precedence = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        if self.value is None:
            return "NULL"
        elif isinstance(self.value, bool):
            return "TRUE" if self.value else "FALSE"
        elif isinstance(self.value, str):
            # Escape single quotes
            escaped = self.value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(self.value, float):
            # Handle special float values
            if self.value == float("inf"):
                return "'Infinity'"
            elif self.value == float("-inf"):
                return "'-Infinity'"
            elif self.value != self.value:  # NaN
                return "'NaN'"
            return str(self.value)
        else:
            return str(self.value)


@dataclass
class SQLRaw(SQLExpression):
    """
    Represents raw SQL that should not be escaped or quoted.

    Use for SQL fragments that need to be passed through verbatim,
    such as INTERVAL literals: INTERVAL '1 day'

    WARNING: Use with caution - this bypasses all escaping!
    """

    raw_sql: str
    precedence: int = field(default=PRECEDENCE["PRIMARY"], init=False)

    def __post_init__(self):
        self.precedence = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return self.raw_sql

    def is_date_typed(self) -> bool:
        """Check if this raw SQL is a DATE literal (e.g. DATE '2024-01-01')."""
        return self.raw_sql.startswith("DATE ")


@dataclass
class SQLNamedArg(SQLExpression):
    """
    Represents a named argument in a function call: name := value.
    Used for DuckDB's struct_pack(key := value, ...) syntax.
    """

    name: str
    value: "SQLExpression" = None
    precedence: int = field(default=PRECEDENCE["PRIMARY"], init=False)

    def __post_init__(self):
        self.precedence = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"{self.name} := {self.value.to_sql()}"


@dataclass
class SQLExtract(SQLExpression):
    """
    Represents SQL EXTRACT(field FROM expr) which has special syntax
    (no comma between field and FROM).

    Examples:
        EXTRACT(YEAR FROM date_col)
        EXTRACT(MONTH FROM timestamp_col)
    """

    extract_field: str  # YEAR, MONTH, DAY, etc.
    source: "SQLExpression" = None
    precedence: int = 0

    def __post_init__(self):
        self.precedence = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"EXTRACT({self.extract_field} FROM {self.source.to_sql()})"


@dataclass
class SQLIdentifier(SQLExpression):
    """
    Represents an identifier (column, table, alias) in SQL.

    Examples:
        patient_id
        resource
        t1.name
    """

    name: str
    quoted: bool = False
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Auto-quote if name contains spaces, special characters, or is a reserved word
        needs_quoting = (
            self.quoted or
            ' ' in self.name or
            any(c in self.name for c in '-()') or
            self.name.upper() in _SQL_RESERVED_WORDS
        )
        if needs_quoting:
            # Use double quotes for quoted identifiers (escape internal quotes)
            escaped = self.name.replace('"', '""')
            return f'"{escaped}"'
        return self.name


@dataclass
class SQLQualifiedIdentifier(SQLExpression):
    """
    Represents a qualified identifier (table.column) in SQL.

    Examples:
        t1.resource
        patients.id
    """

    parts: List[str] = field(default_factory=list)
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        def _quote_part(part: str) -> str:
            """Quote a part if it contains special characters needing quoting."""
            if part.startswith('"') and part.endswith('"'):
                return part  # already quoted
            needs_quoting = (
                ' ' in part or ':' in part or '-' in part or
                '(' in part or ')' in part
            )
            if needs_quoting:
                return f'"{part}"'
            return part
        return ".".join(_quote_part(p) for p in self.parts)


@dataclass
class SQLFunctionCall(SQLExpression):
    """
    Represents a function call in SQL.

    Examples:
        fhirpath_text(resource, 'name')
        COALESCE(a, b)
        COUNT(*)
    """

    name: str
    args: List[SQLExpression] = field(default_factory=list)
    distinct: bool = False
    order_by: Optional[List[tuple]] = None  # [(expr, 'ASC'|'DESC')] for ordered aggregates
    precedence: int = PRECEDENCE["FUNCTION"]

    def normalize(self) -> "SQLExpression":
        """Pre-serialization normalization: apply domain-specific transforms.

        Returns a new expression (possibly different type) that is safe for
        pure SQL serialization.  Callers who need special handling should
        call ``normalize().to_sql()`` instead of ``to_sql()`` directly.
        The default ``to_sql()`` calls this internally for backward compatibility.
        """
        # array_length on non-array arguments → CASE IS NOT NULL / CASE WHEN
        # SQLRaw used here: normalize() is called only from to_sql() (final rendering).
        if self.name.lower() == "array_length" and len(self.args) >= 1:
            arg = self.args[0]
            if isinstance(arg, SQLCase):
                arg_sql = arg.to_sql()
                return SQLRaw(f"(CASE WHEN ({arg_sql}) IS NOT NULL THEN 1 ELSE 0 END)")
            if isinstance(arg, SQLBinaryOp) and arg.operator in ("IS NOT", "IS", "=", "<>", "!=", "<", ">", "<=", ">="):
                arg_sql = arg.to_sql()
                return SQLRaw(f"(CASE WHEN ({arg_sql}) THEN 1 ELSE 0 END)")

        # fhirpath functions with SQLUnion first arg → distribute via COALESCE
        if self.name.lower() in ("fhirpath_text", "fhirpath_bool", "fhirpath_date") and len(self.args) >= 1:
            first_arg = self.args[0]
            if isinstance(first_arg, SQLUnion):
                coalesce_args = [
                    SQLFunctionCall(name=self.name, args=[op] + self.args[1:], distinct=self.distinct)
                    for op in first_arg.operands
                ]
                return SQLFunctionCall(name="COALESCE", args=coalesce_args)

        # intervalFromBounds: cast first two args to VARCHAR
        if self.name == "intervalFromBounds":
            arg_sqls: list[str] = []
            for i, arg in enumerate(self.args):
                arg_sql = arg.to_sql()
                if i < 2:
                    needs_cast = True
                    if isinstance(arg, SQLLiteral) and isinstance(arg.value, str):
                        needs_cast = False
                    elif isinstance(arg, SQLFunctionCall) and arg.name and arg.name.lower() in ('fhirpath_text', 'coalesce'):
                        needs_cast = False
                    elif isinstance(arg, SQLLiteral) and arg.value is None:
                        needs_cast = False
                    if needs_cast:
                        arg_sql = f"CAST({arg_sql} AS VARCHAR)"
                arg_sqls.append(arg_sql)
            return SQLRaw(f"{self.name}({', '.join(arg_sqls)})")

        return self

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Apply pre-serialization normalization
        normalized = self.normalize()
        if normalized is not self:
            return normalized.to_sql(parent_precedence)

        if not self.args:
            return f"{self.name}()"

        # Build argument SQL, wrapping subqueries/selects/unions in parentheses
        arg_sqls = []
        for arg in self.args:
            arg_sql = arg.to_sql()
            # Wrap SQLSelect, SQLSubquery, or set operations in parentheses when used as function argument
            if isinstance(arg, SQLSelect):
                # SQLSelect needs wrapping
                arg_sql = f"({arg_sql})"
            elif isinstance(arg, (SQLIntersect, SQLExcept)):
                # INTERSECT/EXCEPT with parenthesized operands can't be used
                # directly as a scalar subquery.  Wrap as a scalar selecting
                # only the resource column (operands have patient_id, resource).
                arg_sql = f"(SELECT resource FROM ({arg_sql}) _setop)"
            elif isinstance(arg, SQLUnion):
                # Set operations in scalar context need parentheses
                arg_sql = f"({arg_sql})"
            # SQLSubquery.to_sql() already returns (SELECT...), so use as-is
            arg_sqls.append(arg_sql)

        if self.distinct:
            return f"{self.name}(DISTINCT {', '.join(arg_sqls)})"

        if self.order_by:
            order_parts = []
            for expr, direction in self.order_by:
                order_parts.append(f"{expr.to_sql()} {direction}")
            return f"{self.name}({', '.join(arg_sqls)} ORDER BY {', '.join(order_parts)})"

        return f"{self.name}({', '.join(arg_sqls)})"



@dataclass
class SQLBinaryOp(SQLExpression):
    """
    Represents a binary operator expression in SQL.

    Examples:
        a + b
        x = y
        name LIKE '%smith%'
    """

    operator: str
    left: SQLExpression
    right: SQLExpression
    precedence: int = 5  # Default to multiplicative

    def __post_init__(self):
        # Set precedence based on operator
        op_upper = self.operator.upper()
        if op_upper in PRECEDENCE:
            self.precedence = PRECEDENCE[op_upper]

    def to_sql(self, parent_precedence: int = 0) -> str:
        left_sql = self.left.to_sql(self.precedence)

        # Handle BETWEEN specially - right side should be "low AND high"
        if self.operator.upper() == "BETWEEN":
            # If right is a __between_args__ function, expand it
            if isinstance(self.right, SQLFunctionCall) and self.right.name == "__between_args__":
                if len(self.right.args) >= 2:
                    low_sql = self.right.args[0].to_sql(self.precedence)
                    high_sql = self.right.args[1].to_sql(self.precedence)
                    result = f"{left_sql} BETWEEN {low_sql} AND {high_sql}"
                    if self.needs_parentheses(parent_precedence):
                        return f"({result})"
                    return result
            # Otherwise, use the standard format
            right_sql = self.right.to_sql(self.precedence)
            result = f"{left_sql} BETWEEN {right_sql}"
            if self.needs_parentheses(parent_precedence):
                return f"({result})"
            return result

        right_sql = self.right.to_sql(self.precedence)

        result = f"{left_sql} {self.operator} {right_sql}"

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


@dataclass
class SQLUnaryOp(SQLExpression):
    """
    Represents a unary operator expression in SQL.

    Examples:
        NOT x
        -5
        IS NULL
    """

    operator: str
    operand: SQLExpression
    prefix: bool = True  # True for NOT x, False for x IS NULL
    precedence: int = 3  # Default to NOT

    def __post_init__(self):
        # Set precedence based on operator
        op_upper = self.operator.upper()
        if op_upper == "NOT":
            self.precedence = PRECEDENCE["NOT"]
        elif op_upper == "-":
            self.precedence = PRECEDENCE["UNARY_MINUS"]
        elif op_upper == "+":
            self.precedence = PRECEDENCE["UNARY_PLUS"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        operand_sql = self.operand.to_sql(self.precedence)

        if self.prefix:
            result = f"{self.operator} {operand_sql}"
        else:
            result = f"{operand_sql} {self.operator}"

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


@dataclass
class SQLStructFieldAccess(SQLExpression):
    """Access a named field on a struct expression.

    Serializes as: (expr).field_name

    Used primarily to extract the boolean ``.result`` field from audit-macro
    structs (``audit_and``, ``audit_not``, ``audit_leaf``) when those
    expressions must be used as SQL WHERE / CASE WHEN predicates.
    """

    expr: SQLExpression
    field_name: str
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"struct_extract({self.expr.to_sql()}, '{self.field_name}')"


@dataclass
class SQLCase(SQLExpression):
    """
    Represents a CASE expression in SQL.

    Examples:
        CASE WHEN x = 1 THEN 'one' ELSE 'other' END
        CASE x WHEN 1 THEN 'one' ELSE 'other' END
    """

    when_clauses: List[tuple] = field(default_factory=list)  # List of (condition, result)
    else_clause: Optional[SQLExpression] = None
    operand: Optional[SQLExpression] = None  # For simple CASE
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        parts = ["CASE"]

        if self.operand:
            # Simple CASE expression
            parts.append(self.operand.to_sql())

        for condition, result in self.when_clauses:
            result_sql = result.to_sql()
            # Set operations (INTERSECT/EXCEPT) in THEN position are parsed
            # as applying to the CASE result, not as the THEN value.
            # Wrap them in a scalar subquery to disambiguate.
            if isinstance(result, (SQLIntersect, SQLExcept)):
                result_sql = f"(SELECT resource FROM ({result_sql}) _setop)"
            if self.operand:
                parts.append(f"WHEN {condition.to_sql()} THEN {result_sql}")
            else:
                parts.append(f"WHEN {condition.to_sql()} THEN {result_sql}")

        if self.else_clause:
            else_sql = self.else_clause.to_sql()
            if isinstance(self.else_clause, (SQLIntersect, SQLExcept)):
                else_sql = f"(SELECT resource FROM ({else_sql}) _setop)"
            parts.append(f"ELSE {else_sql}")

        parts.append("END")

        result = " ".join(parts)

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


@dataclass
class SQLArray(SQLExpression):
    """
    Represents an ARRAY constructor in SQL (DuckDB syntax).

    Examples:
        [1, 2, 3]
        ['a', 'b', 'c']
    """

    elements: List[SQLExpression] = field(default_factory=list)
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        if not self.elements:
            return "[]"

        elem_sqls = [elem.to_sql() for elem in self.elements]
        return f"[{', '.join(elem_sqls)}]"


@dataclass
class SQLList(SQLExpression):
    """
    Represents a list literal (tuple) in SQL.

    Used for IN clauses and list operations.

    Examples:
        ('confirmed', 'provisional')
        (1, 2, 3)
    """

    items: List[SQLExpression] = field(default_factory=list)
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        if not self.items:
            return "()"

        items_sql = ", ".join(item.to_sql() for item in self.items)
        return f"({items_sql})"


@dataclass
class SQLLambda(SQLExpression):
    """
    Represents a lambda expression for list operations in SQL.

    Used in list_filter, list_apply, etc.

    Examples:
        r -> r.status = 'completed'
        x -> fhirpath_text(x, 'code')
    """

    param: str
    body: SQLExpression
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"{self.param} -> {self.body.to_sql()}"


@dataclass
class SQLLambda2(SQLExpression):
    """
    Represents a two-parameter lambda expression for list_reduce.

    Examples:
        (x, y) -> x + y
        (acc, elem) -> acc * elem
    """

    params: List[str]
    body: SQLExpression
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"({', '.join(self.params)}) -> {self.body.to_sql()}"


@dataclass
class SQLAlias(SQLExpression):
    """
    Represents an alias for an expression (expr AS alias).

    Examples:
        COUNT(*) AS total
        resource->>'id' AS patient_id
        resources r  (implicit_alias=True, for FROM clauses)
    """

    expr: SQLExpression
    alias: str
    implicit_alias: bool = False  # If True, render without AS keyword (for FROM clauses)
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Quote alias if it contains special characters or is a reserved word
        needs_quoting = (
            ' ' in self.alias or
            any(c in self.alias for c in '-()') or
            self.alias.upper() in _SQL_RESERVED_WORDS
        )
        keyword = "" if self.implicit_alias else " AS"
        expr_sql = self.expr.to_sql()
        # Wrap UNION/INTERSECT/EXCEPT in parens when used as FROM source
        if type(self.expr).__name__ in ('SQLUnion', 'SQLIntersect', 'SQLExcept'):
            expr_sql = f"({expr_sql})"
        # Wrap CASE in a subquery when used as FROM source with alias
        elif isinstance(self.expr, SQLCase):
            expr_sql = f"(SELECT {expr_sql})"
        if needs_quoting:
            escaped = self.alias.replace('"', '""')
            return f"{expr_sql}{keyword} \"{escaped}\""
        return f"{expr_sql}{keyword} {self.alias}"


@dataclass
class SQLInterval(SQLExpression):
    """
    Represents an interval literal or constructor in SQL.

    For DuckDB, we use a JSON representation for CQL intervals.
    """

    low: Optional[SQLExpression] = None
    high: Optional[SQLExpression] = None
    low_closed: bool = True
    high_closed: bool = True
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Build interval using intervalFromBounds UDF (expects VARCHAR inputs)
        low_sql = self.low.to_sql() if self.low else "NULL"
        high_sql = self.high.to_sql() if self.high else "NULL"
        low_closed_sql = "TRUE" if self.low_closed else "FALSE"
        high_closed_sql = "TRUE" if self.high_closed else "FALSE"

        # intervalFromBounds expects VARCHAR; wrap typed args (DATE, TIMESTAMP, etc.)
        # Always cast non-NULL, non-string-literal args to avoid type mismatches
        if self.low and not isinstance(self.low, SQLNull):
            if self.low.is_date_typed() or self._needs_varchar_cast(self.low):
                low_sql = f"CAST({low_sql} AS VARCHAR)"
        if self.high and not isinstance(self.high, SQLNull):
            if self.high.is_date_typed() or self._needs_varchar_cast(self.high):
                high_sql = f"CAST({high_sql} AS VARCHAR)"

        return f"intervalFromBounds({low_sql}, {high_sql}, {low_closed_sql}, {high_closed_sql})"

    @staticmethod
    def _needs_varchar_cast(expr: "SQLExpression") -> bool:
        """Check if an expression might produce a non-VARCHAR type that needs casting.

        intervalFromBounds requires VARCHAR inputs.  Rather than enumerating
        all non-VARCHAR producers, whitelist known VARCHAR forms and cast the rest.
        """
        # String literals are already VARCHAR
        if isinstance(expr, SQLLiteral) and isinstance(expr.value, str):
            return False
        # fhirpath_text / COALESCE of fhirpath_text already return VARCHAR
        if isinstance(expr, SQLFunctionCall) and expr.name and expr.name.lower() in (
            "fhirpath_text", "coalesce",
        ):
            return False
        # NULL is type-agnostic
        if isinstance(expr, SQLNull):
            return False
        # Everything else (subqueries, CAST, timestamps, qualified refs) needs casting
        return True


@dataclass
class SQLCast(SQLExpression):
    """
    Represents a CAST expression in SQL.

    Examples:
        CAST(x AS VARCHAR)
        TRY_CAST(value AS DOUBLE)
    """

    expression: SQLExpression
    target_type: str
    try_cast: bool = False
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        expr_sql = self.expression.to_sql()
        keyword = "TRY_CAST" if self.try_cast else "CAST"
        return f"{keyword}({expr_sql} AS {self.target_type})"

    def is_date_typed(self) -> bool:
        """Check if this CAST targets DATE type."""
        return self.target_type == "DATE"


@dataclass
class SQLJoin(SQLExpression):
    """
    Represents a JOIN clause in SQL.

    Examples:
        LEFT JOIN resources r ON r.patient_ref = p.patient_id
        INNER JOIN conditions c ON c.subject = p.id
    """

    join_type: str  # "LEFT", "INNER", "RIGHT", "CROSS"
    table: SQLExpression  # Table name or subquery
    alias: Optional[str] = None
    on_condition: Optional[SQLExpression] = None
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        jt = self.join_type.upper()
        # If join_type already contains "JOIN" (e.g. "CROSS JOIN LATERAL"), don't append "JOIN"
        parts = [jt] if "JOIN" in jt else [jt, "JOIN"]

        # Table reference
        table_sql = self.table.to_sql()
        if isinstance(self.table, SQLSelect):
            # Wrap subqueries in parentheses
            if not table_sql.startswith('('):
                table_sql = f"({table_sql})"

        if self.alias:
            parts.append(f"{table_sql} AS {self.alias}")
        else:
            parts.append(table_sql)

        # ON condition
        if self.on_condition:
            parts.append(f"ON {self.on_condition.to_sql()}")

        return " ".join(parts)


@dataclass
class SQLSelect(SQLExpression):
    """
    Represents a SELECT statement.

    Attributes:
        columns: List of column expressions (can be SQLExpression or (SQLExpression, alias) tuple)
        from_clause: The FROM clause (table name or subquery)
        joins: Optional list of JOIN clauses
        where: Optional WHERE clause expression
        group_by: Optional GROUP BY columns
        having: Optional HAVING clause
        order_by: Optional ORDER BY columns
        limit: Optional LIMIT value
    """

    columns: List[Union[SQLExpression, tuple]] = field(default_factory=list)
    from_clause: Optional[SQLExpression] = None
    joins: List["SQLJoin"] = field(default_factory=list)
    where: Optional[SQLExpression] = None
    group_by: Optional[List[SQLExpression]] = None
    having: Optional[SQLExpression] = None
    order_by: Optional[List[tuple]] = None  # List of (expr, 'ASC'|'DESC')
    limit: Optional[int] = None
    distinct: bool = False
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        parts = ["SELECT"]

        if self.distinct:
            parts.append("DISTINCT")

        # Columns
        if not self.columns:
            parts.append("*")
        else:
            col_parts = []
            for col in self.columns:
                if isinstance(col, tuple):
                    expr, alias = col
                    # Quote alias to handle reserved words like NULL, TRUE, FALSE
                    quoted_alias = f'"{alias}"' if alias.upper() in (
                        "NULL", "TRUE", "FALSE", "SELECT", "FROM", "WHERE",
                        "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN",
                        "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
                        "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
                        "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC",
                        "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
                        "DISTINCT", "ALL", "AS", "WITH", "RECURSIVE"
                    ) else alias
                    col_parts.append(f"{expr.to_sql()} AS {quoted_alias}")
                else:
                    col_parts.append(col.to_sql())
            parts.append(", ".join(col_parts))

        # FROM
        if self.from_clause:
            from_sql = self.from_clause.to_sql()
            # Wrap in parentheses if it's a subquery (SELECT) that isn't already parenthesized
            if isinstance(self.from_clause, SQLSelect):
                if not from_sql.startswith('('):
                    from_sql = f"({from_sql})"
            # Wrap SQLUnion in parentheses with alias when used as FROM source
            elif isinstance(self.from_clause, SQLUnion):
                from_sql = f"({from_sql}) AS _union"
            # Wrap SQLCase in a subquery — CASE cannot be a direct FROM source
            elif isinstance(self.from_clause, SQLCase):
                from_sql = f"(SELECT {from_sql}) AS _case"
            parts.append(f"FROM {from_sql}")

        # JOINs
        if self.joins:
            for join in self.joins:
                parts.append(join.to_sql())

        # WHERE
        if self.where:
            parts.append(f"WHERE {self.where.to_sql()}")

        # GROUP BY
        if self.group_by:
            group_parts = [g.to_sql() for g in self.group_by]
            parts.append(f"GROUP BY {', '.join(group_parts)}")

        # HAVING
        if self.having:
            parts.append(f"HAVING {self.having.to_sql()}")

        # ORDER BY
        if self.order_by:
            order_parts = []
            for expr, direction in self.order_by:
                order_parts.append(f"{expr.to_sql()} {direction}")
            parts.append(f"ORDER BY {', '.join(order_parts)}")

        # LIMIT
        if self.limit is not None:
            parts.append(f"LIMIT {self.limit}")

        return " ".join(parts)



@dataclass
class SQLSubquery(SQLExpression):
    """
    Represents a subquery in SQL.

    Used for EXISTS, IN subqueries, scalar subqueries, etc.
    """

    query: SQLSelect
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"({self.query.to_sql()})"


@dataclass
class SQLExists(SQLExpression):
    """
    Represents an EXISTS expression.

    Examples:
        EXISTS (SELECT 1 FROM t WHERE ...)
    """

    subquery: SQLSubquery
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return f"EXISTS {self.subquery.to_sql()}"


@dataclass
class CTEDefinition:
    """
    Represents a Common Table Expression (CTE) definition.

    CTEs are used to build up complex queries with named subqueries.
    """

    name: str
    query: SQLSelect
    columns: Optional[List[str]] = None  # Optional column aliases

    def to_sql(self) -> str:
        query_sql = self.query.to_sql()
        if self.columns:
            cols = f"({', '.join(self.columns)})"
            return f"{self.name}{cols} AS (\n{query_sql}\n)"
        return f"{self.name} AS (\n{query_sql}\n)"


def _build_precomputed_column_expression(col_def: ColumnDefinition) -> SQLAlias:
    path_exprs = [
        SQLFunctionCall(
            name=col_def.fhirpath_function,
            args=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                SQLLiteral(value=path),
            ],
        )
        for path in col_def.paths
    ]
    expr = path_exprs[0] if len(path_exprs) == 1 else SQLFunctionCall(name="COALESCE", args=path_exprs)
    return SQLAlias(expr=expr, alias=col_def.column_name)


@dataclass
class SQLRetrieveCTE:
    """
    Represents a CTE for a FHIR resource retrieval with ValueSet filter.

    This is used to generate optimized CTEs that pre-compute commonly used
    columns and can be referenced multiple times in a query.

    Example output:
        "Condition: Essential Hypertension" AS MATERIALIZED (
            SELECT
                r.patient_ref,
                r.resource,
                COALESCE(...) AS effective_date
            FROM resources r
            WHERE r.resourceType = 'Condition'
              AND in_valueset(r.resource, 'code', 'http://...')
        )
    """

    name: str                          # CTE name: "{resourceType}: {valueset_alias}"
    resource_type: str                 # FHIR resource type (e.g., "Condition", "Observation")
    valueset_url: Optional[str] = None           # ValueSet URL for code filtering
    valueset_alias: Optional[str] = None         # Short alias from CQL (e.g., "Essential Hypertension")
    profile_url: Optional[str] = None            # Optional US-Core/QICore profile URL
    precomputed_columns: Dict[str, SQLExpression] = field(default_factory=dict)  # column_name -> SQL expression
    materialized: bool = True          # Use MATERIALIZED hint for DuckDB optimization

    # Choice-type columns that may contain different types
    _CHOICE_TYPE_COLUMN_NAMES: set = field(default_factory=lambda: {"value", "onset", "effective"})

    def get_column_info(self) -> Dict[str, "ColumnInfo"]:
        """
        Get ColumnInfo for all precomputed columns.

        Returns:
            Dict mapping column_name -> ColumnInfo for each precomputed column.
        """
        from ..translator.column_registry import ColumnInfo

        result = {}
        for col_name, col_expr in self.precomputed_columns.items():
            fhirpath = self._extract_fhirpath(col_expr)
            result[col_name] = ColumnInfo(
                column_name=col_name,
                fhirpath=fhirpath,
                sql_type=self._infer_sql_type(col_expr),
                is_choice_type=self._is_choice_type_column(col_name),
            )
        return result

    def _extract_fhirpath(self, col_expr: SQLExpression) -> str:
        """
        Extract FHIRPath expression from column definition.

        Parses fhirpath_text(r.resource, 'path') -> 'path'
        Handles COALESCE of multiple fhirpath calls.
        """
        from ..translator import ast_utils
        
        # Use AST-based extraction instead of regex on SQL string
        fhirpath = ast_utils.extract_fhirpath_from_ast(col_expr)
        if fhirpath:
            # For COALESCE, returns comma-separated paths - take first
            if ',' in fhirpath:
                return fhirpath.split(',')[0].strip()
            return fhirpath
        
        return ""

    def _infer_sql_type(self, col_expr: SQLExpression) -> str:
        """
        Infer SQL type from expression.

        Looks at the fhirpath function name to determine the return type.
        """
        from ..translator import ast_utils
        
        # Use AST-based type inference instead of string matching
        return ast_utils.infer_sql_type_from_ast(col_expr)

    def _is_choice_type_column(self, col_name: str) -> bool:
        """
        Check if a column is a choice-type column.

        Choice-type columns may contain different types depending on
        which FHIR path is populated.
        """
        # Check if the column name matches known choice-type patterns
        col_lower = col_name.lower()
        for choice_type in self._CHOICE_TYPE_COLUMN_NAMES:
            if col_lower.startswith(choice_type) or col_lower == choice_type:
                return True
        return False

    @classmethod
    def create_with_precomputed_columns(
        cls,
        resource_type: str,
        valueset_url: str | None = None,
        valueset_alias: str | None = None,
        profile_url: str | None = None,
        name: str | None = None,
        fhir_schema: Optional["FHIRSchemaRegistry"] = None,
        profile_registry: Optional["ProfileRegistry"] = None,
        column_mappings: Optional[Dict[str, str]] = None,
        choice_type_prefixes: Optional[set] = None,
    ) -> "SQLRetrieveCTE":
        """
        Create a SQLRetrieveCTE with automatically populated pre-computed columns.

        Args:
            resource_type: FHIR resource type
            valueset_url: Optional ValueSet URL
            valueset_alias: Short alias from CQL
            profile_url: Optional profile URL
            name: Optional CTE name (auto-generated if not provided)

        Returns:
            SQLRetrieveCTE with pre-computed columns for the resource type
        """
        # Generate name if not provided
        if name is None:
            if valueset_alias:
                name = f"{resource_type}: {valueset_alias}"
            else:
                name = resource_type

        property_paths = get_default_property_paths(
            resource_type, profile_url,
            fhir_schema=fhir_schema, profile_registry=profile_registry,
        )
        column_defs = build_column_definitions(
            resource_type, property_paths, fhir_schema=fhir_schema,
            column_mappings=column_mappings, choice_type_prefixes=choice_type_prefixes,
        )

        precomputed = {}
        for col_name in sorted(column_defs):
            precomputed[col_name] = _build_precomputed_column_expression(column_defs[col_name])

        return cls(
            name=name,
            resource_type=resource_type,
            valueset_url=valueset_url,
            valueset_alias=valueset_alias,
            profile_url=profile_url,
            precomputed_columns=precomputed,
        )

    def to_sql(self) -> str:
        """Generate the CTE SQL clause."""
        # Build column list - alias patient_ref AS patient_id for consistent JOIN conditions
        columns: List[SQLExpression] = [
            SQLAlias(
                expr=SQLQualifiedIdentifier(parts=["r", "patient_ref"]),
                alias="patient_id"
            ),
            SQLQualifiedIdentifier(parts=["r", "resource"]),
        ]

        # Add precomputed columns (already aliased)
        for col_name, col_expr in self.precomputed_columns.items():
            columns.append(col_expr)  # col_expr is already an SQLAlias

        # Build WHERE conditions
        conditions: List[SQLExpression] = [
            SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["r", "resourceType"]),
                right=SQLLiteral(value=self.resource_type),
            )
        ]

        # Add valueset filter if present
        if self.valueset_url:
            from ..translator.types import SQLFunctionCall
            from ..translator.patterns.retrieve import _TERMINOLOGY_PROPERTY_DEFAULTS
            effective_code_property = _TERMINOLOGY_PROPERTY_DEFAULTS.get(self.resource_type, "code")
            if self.valueset_url.startswith("urn:cql:code:"):
                # Direct code reference: urn:cql:code:<system>|<code>
                parts = self.valueset_url[len("urn:cql:code:"):].split("|", 1)
                system_url = parts[0] if len(parts) > 0 else ""
                code_val = parts[1] if len(parts) > 1 else ""
                fhirpath_expr = f"{effective_code_property}.coding.where(system='{system_url}' and code='{code_val}').exists()"
                valueset_filter = SQLFunctionCall(
                    name="fhirpath_bool",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral(value=fhirpath_expr),
                    ],
                )
            else:
                valueset_filter = SQLFunctionCall(
                    name="in_valueset",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral(value=effective_code_property),
                        SQLLiteral(value=self.valueset_url),
                    ],
                )
            conditions.append(valueset_filter)

        # Combine conditions with AND
        where_clause: Optional[SQLExpression] = None
        if len(conditions) == 1:
            where_clause = conditions[0]
        elif len(conditions) > 1:
            # Build AND chain
            where_clause = conditions[0]
            for cond in conditions[1:]:
                where_clause = SQLBinaryOp(
                    operator="AND",
                    left=where_clause,
                    right=cond,
                )

        # Build SELECT
        select = SQLSelect(
            columns=columns,
            from_clause=SQLAlias(expr=SQLIdentifier(name="resources"), alias="r", implicit_alias=True),
            where=where_clause,
            distinct=True,
        )

        # Generate CTE clause
        mat_hint = "MATERIALIZED " if self.materialized else ""
        # Quote the CTE name to handle colons and spaces
        quoted_name = f'"{self.name}"' if ':' in self.name or ' ' in self.name else self.name
        return f'{quoted_name} AS {mat_hint}({select.to_sql()})'

def deduplicate_retrieve_ctes(ctes: List[SQLRetrieveCTE]) -> List[SQLRetrieveCTE]:
    """
    Deduplicate CTEs by (resource_type, valueset_url).

    When the same valueset is used multiple times for the same resource type,
    only keep one CTE to avoid redundant computation.

    Args:
        ctes: List of SQLRetrieveCTE objects to deduplicate.

    Returns:
        Deduplicated list of SQLRetrieveCTE objects.
    """
    seen: Dict[tuple, SQLRetrieveCTE] = {}
    for cte in ctes:
        key = (cte.resource_type, cte.valueset_url)
        if key not in seen:
            seen[key] = cte
    return list(seen.values())


@dataclass
class SQLFragment:
    """
    A container for a complete SQL fragment with CTEs.

    Represents a complete SQL statement with optional CTEs (WITH clause).
    """

    main_query: SQLSelect
    ctes: List[CTEDefinition] = field(default_factory=list)

    def to_sql(self) -> str:
        if not self.ctes:
            return self.main_query.to_sql()

        cte_parts = [cte.to_sql() for cte in self.ctes]
        with_clause = "WITH " + ",\n".join(cte_parts)
        return f"{with_clause}\n{self.main_query.to_sql()}"


@dataclass
class SQLParameterRef(SQLExpression):
    """
    Represents a reference to a CQL parameter.

    Parameters are passed as prepared statement parameters.
    """

    name: str
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Normalize parameter name for DuckDB session variable:
        # - Convert spaces to underscores
        # - Convert to lowercase
        # - Use getvariable() for session variables
        # - CAST to VARCHAR since getvariable returns a string literal type
        normalized_name = self.name.replace(" ", "_").lower()
        return f"CAST(getvariable('{normalized_name}') AS VARCHAR)"


VALID_INTERVAL_UNITS = {"year", "month", "week", "day", "hour", "minute", "second"}


@dataclass
class SQLIntervalLiteral(SQLExpression):
    """SQL INTERVAL literal (e.g., INTERVAL '5 day'). Not to be confused with
    SQLInterval which represents FHIR value intervals."""
    value: int
    unit: str

    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        unit = self.unit.lower()
        # Normalize plural forms (e.g., 'days' -> 'day', 'months' -> 'month')
        if unit.endswith("s") and unit[:-1] in VALID_INTERVAL_UNITS:
            unit = unit[:-1]
        if unit not in VALID_INTERVAL_UNITS:
            raise ValueError(f"Invalid interval unit: {self.unit}")
        return f"INTERVAL '{self.value} {unit}'"


@dataclass
class SQLNull(SQLExpression):
    """
    Represents a NULL literal.
    """

    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return "NULL"


@dataclass
class SQLUnion(SQLExpression):
    """
    Represents a UNION or UNION ALL expression in SQL.

    Used for combining multiple SELECT statements.

    CQL semantics: Union should deduplicate by default (UNION, not UNION ALL).
    Only use UNION ALL when sources are provably disjoint (different resource types).
    """

    operands: List[SQLExpression] = field(default_factory=list)
    distinct: bool = True  # UNION by default (CQL semantics - deduplicate)
    precedence: int = PRECEDENCE["UNION"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        if not self.operands:
            return "SELECT NULL WHERE FALSE"

        union_keyword = "UNION" if self.distinct else "UNION ALL"

        def _normalize_operand(op: "SQLExpression") -> str:
            """Render an operand for UNION, normalizing column lists."""
            if isinstance(op, SQLIdentifier) and op.quoted:
                wrapper = SQLSelect(
                    columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="resource")],
                    from_clause=op,
                )
                return wrapper.to_sql(self.precedence)
            elif isinstance(op, SQLSubquery) and isinstance(op.query, SQLIdentifier) and op.query.quoted:
                wrapper = SQLSelect(
                    columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="resource")],
                    from_clause=op.query,
                )
                return wrapper.to_sql(self.precedence)
            elif isinstance(op, SQLSubquery) and isinstance(op.query, SQLSelect):
                inner = op.query
                cols = inner.columns or []
                # Detect SELECT * from a quoted CTE — replace with explicit patient_id, resource
                # to prevent column count mismatches when CTEs have extra precomputed columns
                # (e.g., status). Keep the WHERE clause and FROM alias intact.
                is_star = (len(cols) == 1 and isinstance(cols[0], SQLIdentifier) and cols[0].name == "*")
                if is_star:
                    from_clause = inner.from_clause
                    from_ident = None
                    if isinstance(from_clause, SQLAlias) and isinstance(from_clause.expr, SQLIdentifier) and from_clause.expr.quoted:
                        from_ident = from_clause.expr
                    elif isinstance(from_clause, SQLIdentifier) and from_clause.quoted:
                        from_ident = from_clause
                    if from_ident:
                        normalized = SQLSelect(
                            columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="resource")],
                            from_clause=inner.from_clause,
                            where=inner.where,
                        )
                        return f"({normalized.to_sql(self.precedence)})"
                # Detect single-column SELECT missing patient_id (e.g., tuple
                # expressions that produce only a 'resource' column).  Add patient_id
                # from the source so UNION operands have matching column counts.
                if len(cols) == 1:
                    col = cols[0]
                    col_name = None
                    if isinstance(col, SQLIdentifier):
                        col_name = col.name
                    elif isinstance(col, SQLAlias):
                        col_name = col.alias
                    if col_name and col_name not in ("patient_id", "*"):
                        # Qualify the patient_id from the FROM alias if present
                        pid_col: SQLExpression
                        from_clause = inner.from_clause
                        alias_name = None
                        if isinstance(from_clause, SQLAlias):
                            alias_name = from_clause.alias
                        if alias_name:
                            pid_col = SQLQualifiedIdentifier(parts=[alias_name, "patient_id"])
                        else:
                            pid_col = SQLIdentifier(name="patient_id")
                        normalized = SQLSelect(
                            columns=[pid_col, col],
                            from_clause=inner.from_clause,
                            where=inner.where,
                            order_by=inner.order_by,
                            limit=inner.limit,
                            distinct=inner.distinct,
                        )
                        return f"({normalized.to_sql(self.precedence)})"
                return op.to_sql(self.precedence)
            else:
                return op.to_sql(self.precedence)

        operand_sqls = [_normalize_operand(op) for op in self.operands]
        result = f" {union_keyword} ".join(operand_sqls)

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


def _normalize_set_operand(op: "SQLExpression", precedence: int) -> str:
    """Normalize a UNION/INTERSECT/EXCEPT operand to (patient_id, resource).

    Handles:
    - Bare quoted CTE identifiers → SELECT patient_id, resource FROM "CTE"
    - SELECT * FROM "CTE" → SELECT patient_id, resource FROM "CTE"
    - SELECT resource FROM "CTE" → SELECT patient_id, resource FROM "CTE"
    """
    if isinstance(op, SQLIdentifier) and op.quoted:
        wrapper = SQLSelect(
            columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="resource")],
            from_clause=op,
        )
        return wrapper.to_sql(precedence)
    elif isinstance(op, SQLSubquery) and isinstance(op.query, SQLSelect):
        inner = op.query
        cols = inner.columns or []
        # Detect SELECT * or SELECT resource (single column from CTE).
        # Also handles qualified form SELECT sub.resource (SQLQualifiedIdentifier)
        # which is generated when the DuckDB alias self-reference bug fix is active.
        needs_normalize = False
        if len(cols) == 1:
            col = cols[0]
            if isinstance(col, SQLIdentifier) and col.name in ("*", "resource"):
                needs_normalize = True
            elif isinstance(col, SQLQualifiedIdentifier) and col.parts and col.parts[-1] in ("*", "resource"):
                needs_normalize = True
        if needs_normalize:
            # Strip LIMIT from set operation operands — set operations
            # (UNION/INTERSECT/EXCEPT) need ALL matching rows, not just
            # the first.  LIMIT 1 is added by SCALAR-context translation
            # but is incorrect for set operation arms.
            normalized = SQLSelect(
                columns=[SQLIdentifier(name="patient_id"),
                         SQLIdentifier(name="resource")],
                from_clause=inner.from_clause,
                where=inner.where,
                order_by=inner.order_by,
                distinct=inner.distinct,
            )
            return f"({normalized.to_sql(precedence)})"
        return op.to_sql(precedence)
    else:
        return op.to_sql(precedence)


@dataclass
class SQLIntersect(SQLExpression):
    """
    Represents an INTERSECT expression in SQL.

    Used for CQL list intersect on row-producing queries.
    """

    operands: List[SQLExpression] = field(default_factory=list)
    precedence: int = PRECEDENCE["INTERSECT"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        if not self.operands:
            return "SELECT NULL WHERE FALSE"

        operand_sqls = [_normalize_set_operand(op, self.precedence) for op in self.operands]
        result = " INTERSECT ".join(operand_sqls)

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


@dataclass
class SQLExcept(SQLExpression):
    """
    Represents an EXCEPT expression in SQL.

    Used for CQL list except on row-producing queries.
    """

    operands: List[SQLExpression] = field(default_factory=list)
    precedence: int = PRECEDENCE["UNION"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        if not self.operands:
            return "SELECT NULL WHERE FALSE"

        operand_sqls = [_normalize_set_operand(op, self.precedence) for op in self.operands]
        result = " EXCEPT ".join(operand_sqls)

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


@dataclass
class SQLWindowFunction(SQLExpression):
    """
    Represents a window function call in SQL.

    Examples:
        ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY date DESC)
        SUM(amount) OVER (PARTITION BY customer_id)
        COUNT(*) OVER (PARTITION BY department ORDER BY hire_date)
    """

    function: str  # e.g., "ROW_NUMBER", "SUM", "COUNT"
    function_args: List[SQLExpression] = field(default_factory=list)
    partition_by: List[SQLExpression] = field(default_factory=list)
    order_by: List[tuple] = field(default_factory=list)  # List of (expr, 'ASC'|'DESC')
    frame_clause: Optional[str] = None  # e.g., "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"
    precedence: int = PRECEDENCE["FUNCTION"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Function call
        if self.function_args:
            args_sql = ", ".join(arg.to_sql() for arg in self.function_args)
            func_sql = f"{self.function}({args_sql})"
        else:
            func_sql = f"{self.function}()"

        # OVER clause
        over_parts = []

        if self.partition_by:
            partition_sql = ", ".join(p.to_sql() for p in self.partition_by)
            over_parts.append(f"PARTITION BY {partition_sql}")

        if self.order_by:
            order_parts = []
            for expr, direction in self.order_by:
                order_parts.append(f"{expr.to_sql()} {direction}")
            over_parts.append(f"ORDER BY {', '.join(order_parts)}")

        if self.frame_clause:
            over_parts.append(self.frame_clause)

        over_clause = " ".join(over_parts)
        result = f"{func_sql} OVER ({over_clause})"

        if self.needs_parentheses(parent_precedence):
            return f"({result})"

        return result


# Type alias for any SQL expression
SQLExpressionType = Union[
    SQLLiteral,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLFunctionCall,
    SQLBinaryOp,
    SQLUnaryOp,
    SQLCase,
    SQLArray,
    SQLList,
    SQLLambda,
    SQLLambda2,
    SQLInterval,
    SQLCast,
    SQLSelect,
    SQLJoin,
    SQLSubquery,
    SQLExists,
    SQLUnion,
    SQLWindowFunction,
    SQLParameterRef,
    SQLNull,
]


# =============================================================================
# Context Types for Translation
# =============================================================================


@dataclass
class SymbolInfo:
    """
    Information about a symbol (variable, alias, or definition) in scope.

    Attributes:
        name: Symbol name.
        cql_type: CQL type (e.g., 'Patient', 'List<Condition>').
        sql_ref: SQL reference (column name or expression).
        source_alias: Optional source table alias.
        is_list: Whether this symbol represents a list value.
        nullable: Whether this symbol can be null.
    """

    name: str
    cql_type: str
    sql_ref: str = ""
    source_alias: Optional[str] = None
    is_list: bool = False
    nullable: bool = True


@dataclass
class ParameterBinding:
    """
    Represents a CQL parameter binding.

    Attributes:
        name: Parameter name.
        param_type: CQL type string.
        default_value: Optional default value.
        value: Runtime value (if set).
    """

    name: str
    param_type: str
    default_value: Any = None
    value: Any = None


@dataclass
class FunctionInfo:
    """
    Information about a CQL function definition.

    Attributes:
        name: Function name.
        parameters: List of (name, type) tuples.
        return_type: Return type.
        body: Function body AST node.
        fluent: Whether this is a fluent function.
    """

    name: str
    parameters: List[tuple] = field(default_factory=list)  # List of (name, type)
    return_type: str = "Any"
    body: Any = None  # AST node for function body
    fluent: bool = False


@dataclass
class LibraryInfo:
    """
    Information about an included CQL library.

    Attributes:
        name: Library name.
        version: Library version.
        alias: Local alias for the library.
        definitions: Named definitions from the library.
        functions: Functions defined in the library.
    """

    name: str
    version: Optional[str] = None
    alias: Optional[str] = None
    definitions: Dict[str, Any] = field(default_factory=dict)
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)


@dataclass
class PatientContext:
    """
    Patient context for single-patient evaluation.

    Attributes:
        patient_id: Current patient ID.
        patient_resource: Full patient FHIR resource (if loaded).
    """

    patient_id: Optional[str] = None
    patient_resource: Optional[Dict[str, Any]] = None

    def is_set(self) -> bool:
        """Check if patient context is configured."""
        return self.patient_id is not None


@dataclass
class QuerySource:
    """
    Represents a query source (table, CTE, or subquery).

    Attributes:
        name: Source name (table name, CTE name, or alias).
        sql_expr: SQL expression for the source.
        resource_type: FHIR resource type (if applicable).
        alias: Query alias for this source.
    """

    name: str
    sql_expr: SQLExpression
    resource_type: Optional[str] = None
    alias: str = ""


# ---------------------------------------------------------------------------
# Audit-mode types — used when CQLToSQLTranslator(audit_mode=True)
# ---------------------------------------------------------------------------


@dataclass
class SQLEvidenceItem(SQLExpression):
    """A single evidence item: struct_pack(target, attribute, value, operator, threshold, trace)."""

    target: SQLExpression = field(default_factory=lambda: SQLNull())
    attribute: SQLExpression = field(default_factory=lambda: SQLNull())
    value: SQLExpression = field(default_factory=lambda: SQLNull())
    operator_str: str = ""
    threshold: SQLExpression = field(default_factory=lambda: SQLNull())
    trace: list = field(default_factory=list)
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        # Cast nullable fields to VARCHAR to prevent DuckDB inferring NULL as INTEGER,
        # which causes type-mismatch errors when concatenating evidence lists whose
        # _audit_item structs were created with different NULL-default types.
        def _varchar(expr: "SQLExpression") -> str:
            sql = expr.to_sql()
            if sql == "NULL":
                return "CAST(NULL AS VARCHAR)"
            return sql

        if self.trace:
            trace_items = ", ".join(f"'{v.replace(chr(39), chr(39)+chr(39))}'" for v in self.trace)
            trace_sql = f"CAST(list_value({trace_items}) AS VARCHAR[])"
        else:
            trace_sql = "CAST([] AS VARCHAR[])"

        return (
            f"struct_pack("
            f"target := {self.target.to_sql()}, "
            f"attribute := {_varchar(self.attribute)}, "
            f"value := {_varchar(self.value)}, "
            f"operator := '{self.operator_str}', "
            f"threshold := {_varchar(self.threshold)}, "
            f"trace := {trace_sql}"
            f")"
        )


@dataclass
class SQLAuditStruct(SQLExpression):
    """struct_pack(result := <bool_expr>, evidence := <evidence_item_array>)."""

    result_expr: SQLExpression = field(default_factory=lambda: SQLLiteral(value=False))
    evidence_expr: SQLExpression = field(default_factory=lambda: SQLArray())
    precedence: int = PRECEDENCE["PRIMARY"]

    def to_sql(self, parent_precedence: int = 0) -> str:
        return (
            f"struct_pack("
            f"result := {self.result_expr.to_sql()}, "
            f"evidence := {self.evidence_expr.to_sql()}"
            f")"
        )


__all__ = [
    # Precedence
    "PRECEDENCE",
    # Base class
    "SQLExpression",
    # Literals and identifiers
    "SQLLiteral",
    "SQLRaw",
    "SQLExtract",
    "SQLIdentifier",
    "SQLQualifiedIdentifier",
    "SQLNull",
    "SQLParameterRef",
    # Operators
    "SQLBinaryOp",
    "SQLUnaryOp",
    # Functions and expressions
    "SQLFunctionCall",
    "SQLCase",
    "SQLArray",
    "SQLList",
    "SQLLambda",
    "SQLLambda2",
    "SQLInterval",
    "SQLCast",
    "SQLAlias",
    # Queries
    "SQLSelect",
    "SQLJoin",
    "SQLSubquery",
    "SQLExists",
    "SQLUnion",
    "SQLWindowFunction",
    # CTEs
    "CTEDefinition",
    "SQLRetrieveCTE",
    "deduplicate_retrieve_ctes",
    "SQLFragment",
    # Default sort columns for First()/Last() determinism
    # Type alias
    "SQLExpressionType",
    # Context types
    "SymbolInfo",
    "ParameterBinding",
    "FunctionInfo",
    "LibraryInfo",
    "PatientContext",
    "QuerySource",
    # Audit types
    "SQLEvidenceItem",
    "SQLAuditStruct",
]

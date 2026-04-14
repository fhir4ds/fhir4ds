"""
Function translation for CQL to SQL.

This module provides the FunctionTranslator class that translates
CQL built-in functions to SQL using DuckDB functions.

DEPRECATED: This module is maintained for backward compatibility only.
New development should use the V2 function registry
(translator/function_registry.py and translator/expressions/_functions.py) instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from ..translator.types import (
    PRECEDENCE,
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLLiteral,
    SQLNull,
    SQLUnaryOp,
)

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext


# Named constants for list operations
# Large number for "slice to end" operations - used as upper bound in list_slice
LIST_SLICE_UPPER_BOUND = 1000000


class FunctionTranslator:
    """
    Translates CQL built-in functions to SQL.

    Handles translation of CQL function calls to SQL expression objects
    using DuckDB built-in functions.

    Categories of functions supported:
    - Aggregate: Count, Sum, Avg, Min, Max, Median, Mode
    - List: First, Last, Skip, Take, Distinct, Where, Select, ForEach,
            SingletonFrom, Flatten
    - DateTime: Now(), Today(), TimeOfDay(), DateTime(), Date(), Time()
    - String: Length, Upper, Lower, Substring, Concatenate, Split, Replace,
              Matches, StartsWith, EndsWith, PositionOf
    - Conversion: ToString, ToInteger, ToDecimal, ToBoolean, ToDateTime,
                  ToQuantity, ToInterval
    - Math: Abs, Ceiling, Floor, Round, Truncate, Ln, Log, Power, Sqrt, Exp
    - Null handling: Coalesce, IsNull, IsNotNull
    - Type: ToString, ToConcept, ToCode
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the function translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def translate_function_call(
        self,
        name: str,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate a CQL function call to SQL.

        Args:
            name: The function name.
            args: The list of translated argument expressions.
            context: The translation context.

        Returns:
            The SQL expression representing the function call.
        """
        name_lower = name.lower()

        # Categorize and dispatch to appropriate handler

        # Aggregate functions
        aggregate_funcs = {"count", "sum", "avg", "min", "max", "median", "mode"}
        if name_lower in aggregate_funcs:
            return self._translate_aggregate(name_lower, args)

        # List functions
        list_funcs = {
            "first", "last", "skip", "take", "distinct", "where", "select",
            "foreach", "singletonfrom", "flatten", "exists"
        }
        if name_lower in list_funcs:
            return self._translate_list_func(name_lower, args, context)

        # DateTime functions
        datetime_funcs = {
            "now", "today", "timeofday", "datetime", "date", "time",
            "year", "month", "day", "hour", "minute", "second",
            "yearsbetween", "monthsbetween", "weeksbetween", "daysbetween",
            "hoursbetween", "minutesbetween", "secondsbetween", "millisecondsbetween",
            "differenceinyears", "differenceinmonths", "differenceindays",
            "differenceinhours", "differenceinminutes", "differenceinseconds"
        }
        if name_lower in datetime_funcs:
            return self._translate_datetime_func(name_lower, args)

        # Clinical functions
        clinical_funcs = {"latest", "earliest"}
        if name_lower in clinical_funcs:
            return self._translate_clinical_func(name_lower, args)

        # String functions
        string_funcs = {
            "length", "upper", "lower", "substring", "concatenate",
            "split", "replace", "matches", "startswith", "endswith",
            "positionof", "contains", "trim", "ltrim", "rtrim"
        }
        if name_lower in string_funcs:
            return self._translate_string_func(name_lower, args)

        # Math functions
        math_funcs = {
            "abs", "ceiling", "floor", "round", "truncate",
            "ln", "log", "power", "sqrt", "exp", "pi", "mod"
        }
        if name_lower in math_funcs:
            return self._translate_math_func(name_lower, args)

        # Conversion functions
        conversion_funcs = {
            "tostring", "tointeger", "todecimal", "toboolean",
            "todatetime", "todate", "totime", "toquantity", "tointerval",
            "toconcept", "tocode"
        }
        if name_lower in conversion_funcs:
            return self._translate_conversion_func(name_lower, args, context)

        # Null handling functions
        if name_lower == "coalesce":
            return SQLFunctionCall(name="COALESCE", args=args)

        if name_lower == "nullif":
            return SQLFunctionCall(name="NULLIF", args=args)

        if name_lower in ("isnull", "is null"):
            if args:
                return SQLUnaryOp(operator="IS NULL", operand=args[0], prefix=False)
            return SQLLiteral(value=True)

        if name_lower in ("isnotnull", "is not null"):
            if args:
                return SQLUnaryOp(operator="IS NOT NULL", operand=args[0], prefix=False)
            return SQLLiteral(value=False)

        # Age functions
        age_funcs = {
            "age", "ageinyears", "ageinmonths", "ageindays",
            "ageinhours", "ageinminutes", "ageinseconds"
        }
        if name_lower in age_funcs:
            return self._translate_age_func(name_lower, args)

        # AgeAt functions (take patient resource and as_of date)
        age_at_funcs = {
            "ageinyearsat", "ageinmonthsat", "ageindaysat"
        }
        if name_lower in age_at_funcs:
            return self._translate_age_at_func(name_lower, args)

        # Default: pass through as function call
        return SQLFunctionCall(name=name, args=args)

    # =========================================================================
    # Aggregate Functions
    # =========================================================================

    def _translate_aggregate(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate aggregate functions.

        SQL patterns:
        - COUNT(*), COUNT(DISTINCT x)
        - SUM(x), AVG(x), MIN(x), MAX(x)
        - MEDIAN(x), MODE(x)
        """
        if name == "count":
            if not args:
                return SQLFunctionCall(name="COUNT", args=[SQLLiteral(value="*")])
            # Use COUNT(DISTINCT) for list counting
            return SQLFunctionCall(name="COUNT", args=args, distinct=True)

        if name == "sum":
            return SQLFunctionCall(name="SUM", args=args)

        if name == "avg":
            return SQLFunctionCall(name="AVG", args=args)

        if name == "min":
            # For scalar min of multiple values, use LEAST
            if len(args) > 1:
                return SQLFunctionCall(name="LEAST", args=args)
            return SQLFunctionCall(name="MIN", args=args)

        if name == "max":
            # For scalar max of multiple values, use GREATEST
            if len(args) > 1:
                return SQLFunctionCall(name="GREATEST", args=args)
            return SQLFunctionCall(name="MAX", args=args)

        if name == "median":
            return SQLFunctionCall(name="MEDIAN", args=args)

        if name == "mode":
            return SQLFunctionCall(name="MODE", args=args)

        # Fallback
        return SQLFunctionCall(name=name.upper(), args=args)

    # =========================================================================
    # List Functions
    # =========================================================================

    def _translate_list_func(
        self,
        name: str,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate list functions.

        SQL patterns:
        - list_extract(arr, 1)  -- First (1-indexed)
        - arr[-1]  -- Last
        - list_slice(arr, offset+1, NULL)  -- Skip
        - list_slice(arr, 1, n)  -- Take
        - array_distinct(arr)  -- Distinct
        - Where/Select -> UNNEST with WHERE clause (requires subquery)
        - flatten(arr)  -- Flatten nested arrays
        """
        if not args:
            return SQLNull()

        source = args[0]

        if name == "first":
            # DuckDB uses 1-based indexing for list_extract
            return SQLFunctionCall(name="list_extract", args=[source, SQLLiteral(value=1)])

        if name == "last":
            # Use negative index for last element
            return SQLFunctionCall(name="list_extract", args=[source, SQLLiteral(value=-1)])

        if name == "skip":
            if len(args) < 2:
                return source
            skip_count = args[1]
            # DuckDB list_slice is 1-based, skip n means start at n+1
            start_index = SQLBinaryOp(
                operator="+",
                left=skip_count,
                right=SQLLiteral(value=1),
            )
            return SQLFunctionCall(name="list_slice", args=[source, start_index, SQLLiteral(value=LIST_SLICE_UPPER_BOUND)])

        if name == "take":
            if len(args) < 2:
                return source
            take_count = args[1]
            # Take first n elements
            return SQLFunctionCall(name="list_slice", args=[source, SQLLiteral(value=1), take_count])

        if name == "distinct":
            return SQLFunctionCall(name="array_distinct", args=[source])

        if name == "where":
            # Where requires a lambda - use list_filter with proper lambda syntax
            # DuckDB: list_filter(list, x -> predicate(x))
            # The second argument should be a lambda expression
            if len(args) >= 2:
                # args[1] should be the lambda/predicate
                # If it's already a SQL expression, wrap it properly
                predicate = args[1]
                # Use list_filter with lambda - the predicate should work with list_filter
                return SQLFunctionCall(name="list_filter", args=[source, predicate])
            return source

        if name == "select":
            # Select requires a lambda - return a placeholder for query translator
            if len(args) >= 2:
                # Use list_transform for lambda projections
                return SQLFunctionCall(name="list_transform", args=[source, args[1]])
            return source

        if name == "foreach":
            # Same as select for our purposes
            if len(args) >= 2:
                return SQLFunctionCall(name="list_transform", args=[source, args[1]])
            return source

        if name == "singletonfrom":
            # Get single element from list (assumes list has exactly one element)
            # Use list_extract with index 1
            return SQLFunctionCall(name="list_extract", args=[source, SQLLiteral(value=1)])

        if name == "flatten":
            # Flatten nested arrays
            return SQLFunctionCall(name="flatten", args=[source])

        if name == "exists":
            # Check if list has any elements
            # For scalar expressions (CASE, etc.), check IS NOT NULL
            from ..translator.types import SQLCase, SQLNull
            if isinstance(source, (SQLCase, SQLBinaryOp)):
                return SQLBinaryOp(
                    operator="IS NOT",
                    left=source,
                    right=SQLNull(),
                )
            return SQLBinaryOp(
                operator=">",
                left=SQLFunctionCall(name="array_length", args=[source]),
                right=SQLLiteral(value=0),
            )

        # Fallback
        return SQLFunctionCall(name=name, args=args)

    # =========================================================================
    # DateTime Functions
    # =========================================================================

    def _translate_datetime_func(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate datetime functions.

        SQL patterns:
        - CURRENT_TIMESTAMP  -- Now()
        - CURRENT_DATE  -- Today()
        - CURRENT_TIME  -- TimeOfDay()
        - make_timestamp(year, month, day, hour, min, sec)  -- DateTime()
        - make_date(year, month, day)  -- Date()
        - make_time(hour, minute, second)  -- Time()
        - date_diff(unit, start, end)  -- Between functions
        """
        if name == "now":
            return SQLFunctionCall(name="CURRENT_TIMESTAMP", args=[])

        if name == "today":
            return SQLFunctionCall(name="CURRENT_DATE", args=[])

        if name == "timeofday":
            return SQLFunctionCall(name="CURRENT_TIME", args=[])

        if name == "datetime":
            return self._build_timestamp(args)

        if name == "date":
            return self._build_date(args)

        if name == "time":
            return self._build_time(args)

        # Component extraction
        if name == "year":
            return SQLFunctionCall(name="YEAR", args=args)

        if name == "month":
            return SQLFunctionCall(name="MONTH", args=args)

        if name == "day":
            return SQLFunctionCall(name="DAY", args=args)

        if name == "hour":
            return SQLFunctionCall(name="HOUR", args=args)

        if name == "minute":
            return SQLFunctionCall(name="MINUTE", args=args)

        if name == "second":
            return SQLFunctionCall(name="SECOND", args=args)

        # Duration between functions
        duration_funcs = {
            "yearsbetween": "year",
            "monthsbetween": "month",
            "weeksbetween": "week",
            "daysbetween": "day",
            "hoursbetween": "hour",
            "minutesbetween": "minute",
            "secondsbetween": "second",
            "millisecondsbetween": "millisecond",
        }
        if name in duration_funcs and len(args) >= 2:
            unit = SQLLiteral(value=duration_funcs[name])
            return SQLFunctionCall(name="date_diff", args=[unit, args[0], args[1]])

        # Difference functions (boundary crossings)
        diff_funcs = {
            "differenceinyears": "year",
            "differenceinmonths": "month",
            "differenceindays": "day",
            "differenceinhours": "hour",
            "differenceinminutes": "minute",
            "differenceinseconds": "second",
        }
        if name in diff_funcs and len(args) >= 2:
            unit = SQLLiteral(value=diff_funcs[name])
            # Difference counts boundary crossings
            return SQLFunctionCall(name="date_diff", args=[unit, args[0], args[1]])

        # Fallback
        return SQLFunctionCall(name=name, args=args)

    def _build_timestamp(self, args: List[SQLExpression]) -> SQLExpression:
        """Build a timestamp from components."""
        if not args:
            return SQLNull()

        if len(args) >= 3:
            year = args[0]
            month = args[1] if len(args) > 1 else SQLLiteral(value=1)
            day = args[2] if len(args) > 2 else SQLLiteral(value=1)
            hour = args[3] if len(args) > 3 else SQLLiteral(value=0)
            minute = args[4] if len(args) > 4 else SQLLiteral(value=0)
            second = args[5] if len(args) > 5 else SQLLiteral(value=0)

            return SQLFunctionCall(
                name="make_timestamp",
                args=[year, month, day, hour, minute, second],
            )

        # Single arg - assume it's a string to parse
        return SQLCast(expression=args[0], target_type="TIMESTAMP")

    def _build_date(self, args: List[SQLExpression]) -> SQLExpression:
        """Build a date from components."""
        if not args:
            return SQLNull()

        if len(args) >= 3:
            year = args[0]
            month = args[1]
            day = args[2]

            return SQLFunctionCall(name="make_date", args=[year, month, day])

        # Single arg - assume it's a string to parse
        return SQLCast(expression=args[0], target_type="DATE")

    def _build_time(self, args: List[SQLExpression]) -> SQLExpression:
        """Build a time from components."""
        if not args:
            return SQLNull()

        if len(args) >= 2:
            hour = args[0]
            minute = args[1]
            second = args[2] if len(args) > 2 else SQLLiteral(value=0)

            return SQLFunctionCall(name="make_time", args=[hour, minute, second])

        # Single arg - assume it's a string to parse
        return SQLCast(expression=args[0], target_type="TIME")

    # =========================================================================
    # String Functions
    # =========================================================================

    def _translate_string_func(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate string functions.

        SQL patterns:
        - LENGTH(s)
        - UPPER(s), LOWER(s)
        - SUBSTRING(s, start, len)
        - s1 || s2  -- Concatenate
        - STR_SPLIT(s, delim)
        - REPLACE(s, old, new)
        - REGEXP_MATCHES(s, pattern)
        - s LIKE 'prefix%'  -- StartsWith
        - s LIKE '%suffix'  -- EndsWith
        - STRPOS(s, substr)  -- PositionOf
        """
        if not args:
            return SQLLiteral(value="")

        if name == "length":
            return SQLFunctionCall(name="LENGTH", args=args)

        if name == "upper":
            return SQLFunctionCall(name="UPPER", args=args)

        if name == "lower":
            return SQLFunctionCall(name="LOWER", args=args)

        if name == "substring":
            return self._translate_substring(args)

        if name == "concatenate":
            return self._translate_concatenate(args)

        if name == "split":
            return SQLFunctionCall(name="STR_SPLIT", args=args)

        if name == "replace":
            return SQLFunctionCall(name="REPLACE", args=args)

        if name == "matches":
            # Regex matching - returns boolean
            # DuckDB's regexp_matches returns BOOLEAN directly (v1.3+)
            if len(args) >= 2:
                return SQLFunctionCall(name="regexp_matches", args=[args[0], args[1]])
            return SQLLiteral(value=False)

        if name == "startswith":
            if len(args) >= 2:
                # s LIKE 'prefix%'
                pattern = SQLBinaryOp(
                    operator="||",
                    left=args[1],
                    right=SQLLiteral(value="%"),
                    precedence=PRECEDENCE["||"],
                )
                return SQLBinaryOp(
                    operator="LIKE",
                    left=args[0],
                    right=pattern,
                    precedence=PRECEDENCE["LIKE"],
                )
            return SQLLiteral(value=False)

        if name == "endswith":
            if len(args) >= 2:
                # s LIKE '%suffix'
                pattern = SQLBinaryOp(
                    operator="||",
                    left=SQLLiteral(value="%"),
                    right=args[1],
                    precedence=PRECEDENCE["||"],
                )
                return SQLBinaryOp(
                    operator="LIKE",
                    left=args[0],
                    right=pattern,
                    precedence=PRECEDENCE["LIKE"],
                )
            return SQLLiteral(value=False)

        if name == "positionof":
            # PositionOf returns 0-based index in CQL, STRPOS is 1-based
            if len(args) >= 2:
                # Adjust to 0-based to match CQL semantics
                strpos_result = SQLFunctionCall(name="STRPOS", args=[args[0], args[1]])
                return SQLBinaryOp(
                    operator="-",
                    left=strpos_result,
                    right=SQLLiteral(value=1),
                )
            return SQLLiteral(value=-1)

        if name == "contains":
            if len(args) >= 2:
                # Check if substring exists (position >= 0)
                strpos_result = SQLFunctionCall(name="STRPOS", args=[args[0], args[1]])
                return SQLBinaryOp(
                    operator=">",
                    left=strpos_result,
                    right=SQLLiteral(value=0),
                )
            return SQLLiteral(value=False)

        if name == "trim":
            return SQLFunctionCall(name="TRIM", args=args)

        if name == "ltrim":
            return SQLFunctionCall(name="LTRIM", args=args)

        if name == "rtrim":
            return SQLFunctionCall(name="RTRIM", args=args)

        # Fallback
        return SQLFunctionCall(name=name.upper(), args=args)

    def _translate_substring(self, args: List[SQLExpression]) -> SQLExpression:
        """
        Translate substring function.

        CQL substring is 0-indexed, SQL is 1-indexed.
        substring(s, start) -> SUBSTRING(s, start+1)
        substring(s, start, length) -> SUBSTRING(s, start+1, length)
        """
        if len(args) < 2:
            return args[0] if args else SQLLiteral(value="")

        # Adjust start index (CQL 0-based -> SQL 1-based)
        start_index = SQLBinaryOp(
            operator="+",
            left=args[1],
            right=SQLLiteral(value=1),
        )

        if len(args) >= 3:
            return SQLFunctionCall(name="SUBSTRING", args=[args[0], start_index, args[2]])

        return SQLFunctionCall(name="SUBSTRING", args=[args[0], start_index])

    def _translate_concatenate(self, args: List[SQLExpression]) -> SQLExpression:
        """Translate concatenate function using || operator."""
        if not args:
            return SQLLiteral(value="")

        if len(args) == 1:
            return args[0]

        # Build left-associative concatenation
        result = args[0]
        for arg in args[1:]:
            result = SQLBinaryOp(
                operator="||",
                left=result,
                right=arg,
                precedence=PRECEDENCE["||"],
            )

        return result

    # =========================================================================
    # Math Functions
    # =========================================================================

    def _translate_math_func(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate math functions.

        SQL patterns:
        - ABS(x)
        - CEIL(x), FLOOR(x)
        - ROUND(x, digits)
        - TRUNCATE(x) -> TRUNC(x)
        - LN(x), LOG(x, base), POW(x, y), SQRT(x), EXP(x)
        - PI()
        """
        if name == "abs":
            return SQLFunctionCall(name="ABS", args=args)

        if name == "ceiling":
            return SQLFunctionCall(name="CEIL", args=args)

        if name == "floor":
            return SQLFunctionCall(name="FLOOR", args=args)

        if name == "round":
            return SQLFunctionCall(name="ROUND", args=args)

        if name == "truncate":
            return SQLFunctionCall(name="TRUNC", args=args)

        if name == "ln":
            return SQLFunctionCall(name="LN", args=args)

        if name == "log":
            if len(args) >= 2:
                # LOG(base, value) in DuckDB
                return SQLFunctionCall(name="LOG", args=[args[1], args[0]])
            # Natural log if no base provided
            return SQLFunctionCall(name="LN", args=args)

        if name == "power":
            if len(args) >= 2:
                return SQLFunctionCall(name="POW", args=[args[0], args[1]])
            return args[0] if args else SQLNull()

        if name == "sqrt":
            return SQLFunctionCall(name="SQRT", args=args)

        if name == "exp":
            return SQLFunctionCall(name="EXP", args=args)

        if name == "pi":
            return SQLFunctionCall(name="PI", args=[])

        if name == "mod":
            if len(args) >= 2:
                return SQLBinaryOp(operator="%", left=args[0], right=args[1])
            return SQLNull()

        # Fallback
        return SQLFunctionCall(name=name.upper(), args=args)

    # =========================================================================
    # Conversion Functions
    # =========================================================================

    def _translate_conversion_func(
        self,
        name: str,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Translate type conversion functions.

        SQL patterns:
        - CAST(x AS VARCHAR)
        - CAST(x AS INTEGER)
        - CAST(x AS DOUBLE)
        - CAST(x AS BOOLEAN)
        - CAST(x AS TIMESTAMP)
        - CAST(x AS DATE)
        - CAST(x AS TIME)
        """
        if not args:
            return SQLNull()

        source = args[0]

        type_map = {
            "tostring": "VARCHAR",
            "tointeger": "INTEGER",
            "todecimal": "DOUBLE",
            "toboolean": "BOOLEAN",
            "todatetime": "TIMESTAMP",
            "todate": "DATE",
            "totime": "TIME",
        }

        if name in type_map:
            target_type = type_map[name]
            return SQLCast(expression=source, target_type=target_type)

        if name == "toquantity":
            # Quantity conversion - return as JSON struct
            # For now, just return the source
            return source

        if name == "tointerval":
            # Interval conversion - return as interval struct
            # For now, just return the source
            return source

        if name == "toconcept":
            # Concept conversion - return as JSON struct
            return source

        if name == "tocode":
            # Code conversion - return as JSON struct
            return source

        # Fallback
        return source

    # =========================================================================
    # Clinical Functions
    # =========================================================================

    def _translate_clinical_func(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate clinical functions.

        SQL patterns:
        - Latest(list, date_path) - Returns most recent item by date
        - Earliest(list, date_path) - Returns earliest item by date
        """
        if name == "latest":
            # Latest(values, date_path) -> returns most recent value
            return SQLFunctionCall(name="Latest", args=args)

        if name == "earliest":
            # Earliest(values, date_path) -> returns earliest value
            return SQLFunctionCall(name="Earliest", args=args)

        # Fallback
        return SQLFunctionCall(name=name, args=args)

    # =========================================================================
    # Age Functions
    # =========================================================================

    def _translate_age_func(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate age calculation functions.

        Uses date_diff with appropriate unit.
        """
        unit_map = {
            "ageinyears": "year",
            "ageinmonths": "month",
            "ageindays": "day",
            "ageinhours": "hour",
            "ageinminutes": "minute",
            "ageinseconds": "second",
        }

        unit = unit_map.get(name, "year")

        # If birthDate provided as argument, use it
        if args:
            birth_date = args[0]
        else:
            # Default: use birthDate from current resource
            resource_col = "resource"
            if self.context.resource_alias:
                resource_col = f"{self.context.resource_alias}.resource"
            birth_date = SQLFunctionCall(
                name="fhirpath_text",
                args=[SQLLiteral(value=resource_col), SQLLiteral(value="birthDate")],
            )

        return SQLFunctionCall(
            name="date_diff",
            args=[
                SQLLiteral(value=unit),
                birth_date,
                SQLFunctionCall(name="CURRENT_DATE", args=[]),
            ],
        )

    def _translate_age_at_func(
        self,
        name: str,
        args: List[SQLExpression],
    ) -> SQLExpression:
        """
        Translate age calculation functions with explicit as_of date.

        These functions call DuckDB UDFs directly:
        - AgeInYearsAt(patient_resource, as_of_date)
        - AgeInMonthsAt(patient_resource, as_of_date)
        - AgeInDaysAt(patient_resource, as_of_date)
        """
        # Map function names to UDF names (proper casing)
        udf_name_map = {
            "ageinyearsat": "AgeInYearsAt",
            "ageinmonthsat": "AgeInMonthsAt",
            "ageindaysat": "AgeInDaysAt",
        }

        udf_name = udf_name_map.get(name, "AgeInYearsAt")

        # Args should be (patient_resource, as_of_date)
        # If only one arg provided, assume it's the as_of_date and use current resource
        if len(args) == 1:
            # Use current patient resource from context
            if self.context.resource_alias:
                patient_resource = SQLQualifiedIdentifier(parts=[self.context.resource_alias, "resource"])
            else:
                patient_resource = SQLCast(
                    expression=SQLFunctionCall(name="getvariable", args=[SQLLiteral(value="patient_resource")]),
                    target_type="VARCHAR"
                )
            as_of_date = args[0]
        elif len(args) >= 2:
            patient_resource = args[0]
            as_of_date = args[1]
        else:
            return SQLNull()

        return SQLFunctionCall(name=udf_name, args=[patient_resource, as_of_date])

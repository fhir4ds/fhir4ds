"""
FHIRPath Functions Module

This module contains implementations of FHIRPath functions organized by category.
"""

from ..functions.string import (
    length,
    substring,
    starts_with,
    ends_with,
    contains,
    upper,
    lower,
    replace,
    matches,
    replace_matches,
    split,
    join,
    trim,
    concatenate,
    STRING_FUNCTIONS,
)

from ..functions.datetime import (
    DateTimeLiteral,
    DateTimeDuration,
    DateTimeArithmetic,
    DateTimeFunctions,
    DateTimeComparisons,
)

from ..functions.conversion import (
    # Type operators
    is_type,
    as_type,
    of_type,
    type_of,
    # Conversion functions
    to_string,
    to_integer,
    to_decimal,
    to_date_time,
    to_date,
    to_time,
    to_boolean,
    to_quantity,
)

from ..functions.math import (
    # Arithmetic operators
    add,
    subtract,
    multiply,
    divide,
    div,
    mod,
    # Unary operators
    negate,
    positive,
    # Aggregate functions
    sum_fn,
    min_fn,
    max_fn,
    avg,
    # Math functions
    abs_fn,
    ceiling,
    floor,
    round_fn,
    sqrt,
    power,
    log,
    exp,
    ln,
    trunc,
    # Class and registries
    MathFunctions,
    MATH_FUNCTIONS,
    MATH_OPERATORS,
)

from ..functions.existence import (
    # Existence functions
    empty,
    exists,
    exists_with_criteria,
    # Quantifier functions
    all_criteria,
    all_true,
    all_false,
    any_true,
    any_false,
    # Counting functions
    count,
    distinct,
    # Function registry
    EXISTENCE_FUNCTIONS,
)

from ..functions.filter import (
    # Filter functions
    where,
    select,
    repeat,
    # Subsetting functions
    first,
    last,
    tail,
    take,
    skip,
    of_type as filter_of_type,
    # Type utilities
    infer_fhir_type,
    FHIR_TYPE_MAP,
    PYTHON_TO_FHIR_TYPE,
)

__all__ = [
    # String functions
    "length",
    "substring",
    "starts_with",
    "ends_with",
    "contains",
    "upper",
    "lower",
    "replace",
    "matches",
    "replace_matches",
    "split",
    "join",
    "trim",
    "concatenate",
    "STRING_FUNCTIONS",
    # DateTime functions
    "DateTimeLiteral",
    "DateTimeDuration",
    "DateTimeArithmetic",
    "DateTimeFunctions",
    "DateTimeComparisons",
    # Type operators
    "is_type",
    "as_type",
    "of_type",
    "type_of",
    # Conversion functions
    "to_string",
    "to_integer",
    "to_decimal",
    "to_date_time",
    "to_date",
    "to_time",
    "to_boolean",
    "to_quantity",
    # Math operators
    "add",
    "subtract",
    "multiply",
    "divide",
    "div",
    "mod",
    "negate",
    "positive",
    # Math aggregate functions
    "sum_fn",
    "min_fn",
    "max_fn",
    "avg",
    # Math functions
    "abs_fn",
    "ceiling",
    "floor",
    "round_fn",
    "sqrt",
    "power",
    "log",
    "exp",
    "ln",
    "trunc",
    # Class and registries
    "MathFunctions",
    "MATH_FUNCTIONS",
    "MATH_OPERATORS",
    # Existence functions
    "empty",
    "exists",
    "exists_with_criteria",
    # Quantifier functions
    "all_criteria",
    "all_true",
    "all_false",
    "any_true",
    "any_false",
    # Counting functions
    "count",
    "distinct",
    # Existence function registry
    "EXISTENCE_FUNCTIONS",
    # Filter functions
    "where",
    "select",
    "repeat",
    # Subsetting functions
    "first",
    "last",
    "tail",
    "take",
    "skip",
    "filter_of_type",
    # Type utilities
    "infer_fhir_type",
    "FHIR_TYPE_MAP",
    "PYTHON_TO_FHIR_TYPE",
]

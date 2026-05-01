"""
CQL Abstract Syntax Tree (AST) Node Definitions.

This module defines dataclass-based AST nodes for CQL R1.5 (Clinical Quality Language).
These nodes represent the parsed structure of CQL expressions and library definitions.

Reference: https://cql.hl7.org/05-libraries.html
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union


# ==============================================================================
# Base Classes
# ==============================================================================


@dataclass
class ASTNode:
    """
    Base class for all AST nodes in the CQL parse tree.

    All CQL AST nodes inherit from this class to provide a common interface
    for traversal and transformation.
    """

    pass


@dataclass
class Expression(ASTNode):
    """
    Base class for all CQL expression nodes.

    Expressions are the core building blocks of CQL that evaluate to values.
    This includes literals, identifiers, function calls, queries, etc.
    """

    pass


@dataclass
class TypeSpecifier(ASTNode):
    """
    Base class for CQL type specifiers.

    Type specifiers define the type of values in CQL expressions,
    including named types, intervals, lists, tuples, and choices.
    """

    pass


# ==============================================================================
# Library Structure Nodes
# ==============================================================================


@dataclass
class Library(ASTNode):
    """
    Represents a CQL library definition.

    A library is the top-level container for CQL code, containing
    definitions, includes, and other declarations.

    Example:
        library MyLibrary version '1.0.0'
        using FHIR version '4.0.1'
        include FHIRHelpers version '4.0.1'

    Attributes:
        identifier: The library name/identifier.
        version: The library version string.
        using: List of using definitions (data model references).
        includes: List of include definitions (library references).
        codesystems: List of code system definitions.
        valuesets: List of value set definitions.
        codes: List of code definitions.
        concepts: List of concept definitions.
        parameters: List of parameter definitions.
        context: The current context definition (e.g., Patient).
        statements: List of expression/function definitions.
    """

    identifier: str
    version: Optional[str] = None
    using: List[UsingDefinition] = field(default_factory=list)
    includes: List[IncludeDefinition] = field(default_factory=list)
    codesystems: List[CodeSystemDefinition] = field(default_factory=list)
    valuesets: List[ValueSetDefinition] = field(default_factory=list)
    codes: List[CodeDefinition] = field(default_factory=list)
    concepts: List[ConceptDefinition] = field(default_factory=list)
    parameters: List[ParameterDefinition] = field(default_factory=list)
    context: Optional[ContextDefinition] = None
    statements: List[Union[Definition, FunctionDefinition]] = field(
        default_factory=list
    )


@dataclass
class UsingDefinition(ASTNode):
    """
    Represents a using definition that references a data model.

    Example:
        using FHIR version '4.0.1'

    Attributes:
        model: The data model name (e.g., 'FHIR', 'QDM').
        version: The model version string.
    """

    model: str
    version: Optional[str] = None


@dataclass
class IncludeDefinition(ASTNode):
    """
    Represents an include definition that references another library.

    Example:
        include FHIRHelpers version '4.0.1' called FHIRHelpers

    Attributes:
        path: The library path/identifier.
        version: The library version string.
        alias: The local alias for the included library.
    """

    path: str
    version: Optional[str] = None
    alias: Optional[str] = None


@dataclass
class ContextDefinition(ASTNode):
    """
    Represents a context definition that sets the execution context.

    Example:
        context Patient

    Attributes:
        name: The context name (e.g., 'Patient', 'Population').
    """

    name: str


@dataclass
class ParameterDefinition(ASTNode):
    """
    Represents a parameter definition for passing values into the library.

    Example:
        parameter "Measurement Period" Interval<DateTime>

    Attributes:
        name: The parameter name.
        type: The type specifier for the parameter.
        default: Optional default value expression.
    """

    name: str
    type: Optional[TypeSpecifier] = None
    default: Optional[Expression] = None


@dataclass
class Definition(ASTNode):
    """
    Represents a named expression definition within a library.

    Example:
        define "In Demographic": Patient.age >= 18

    Attributes:
        name: The definition name.
        expression: The expression being defined.
        context: Optional context name (if different from current context).
        access_level: Access level ('public' or 'private').
    """

    name: str
    expression: Expression
    context: Optional[str] = None
    access_level: Optional[str] = None


# ==============================================================================
# Literal and Value Expressions
# ==============================================================================


@dataclass
class Literal(Expression):
    """
    Represents a literal value in CQL.

    Literals are fixed values directly written in the code,
    such as numbers, strings, booleans, and null.

    Examples:
        123           -- Integer literal
        3.14          -- Decimal literal
        'hello'       -- String literal
        true          -- Boolean literal
        null          -- Null literal

    Attributes:
        value: The literal value (Python type).
        type: Optional CQL type name for the literal.
    """

    value: Any
    type: Optional[str] = None
    raw_str: Optional[str] = None


@dataclass
class Quantity(Expression):
    """
    Represents a quantity value with a unit in CQL.

    Quantities combine a numeric value with a unit of measure,
    particularly useful for date/time arithmetic.

    Examples:
        5 years       -- 5 year quantity
        10 days       -- 10 day quantity
        3.5 hours     -- 3.5 hour quantity
        1 'cm'        -- 1 centimeter quantity

    Attributes:
        value: The numeric value.
        unit: The unit string (e.g., 'year', 'years', 'day', 'days').
    """

    value: float
    unit: str


@dataclass
class CodeSelector(Expression):
    """
    Represents an inline Code selector in CQL expressions.

    Code selectors define specific clinical codes inline in expressions,
    as opposed to CodeDefinition which defines named codes in the library header.

    Examples:
        Code '73211009' from "SNOMED-CT"
        Code '73211009' from "SNOMED-CT" display 'Diabetes mellitus'

    Attributes:
        code: The code value string.
        system: The code system name (identifier reference or string).
        display: Optional display string for the code.
    """

    code: str
    system: str
    display: Optional[str] = None


@dataclass
class DateTimeLiteral(Expression):
    """
    Represents a date/time literal in CQL.

    DateTime literals are prefixed with @ and represent
    specific points in time.

    Example:
        @2024-01-15T12:30:00
        @2024-01-15

    Attributes:
        value: The date/time value as a string.
    """

    value: str


@dataclass
class TimeLiteral(Expression):
    """
    Represents a time literal in CQL.

    Time literals are prefixed with @T and represent
    times without date components.

    Example:
        @T12:30:00
        @T14:00

    Attributes:
        value: The time value as a string.
    """

    value: str


@dataclass
class Interval(Expression):
    """
    Represents an interval expression in CQL.

    Intervals define a range of values with optional open/closed bounds.

    Examples:
        Interval[1, 10]       -- Closed interval (includes endpoints)
        Interval(1, 10)       -- Open interval (excludes endpoints)
        Interval[1, 10)       -- Half-open interval

    Attributes:
        low: The lower bound expression (None for unbounded).
        high: The upper bound expression (None for unbounded).
        low_closed: Whether the lower bound is closed/inclusive.
        high_closed: Whether the upper bound is closed/inclusive.
    """

    low: Optional[Expression] = None
    high: Optional[Expression] = None
    low_closed: bool = True
    high_closed: bool = True


# ==============================================================================
# Identifier and Property Expressions
# ==============================================================================


@dataclass
class Identifier(Expression):
    """
    Represents a simple identifier reference in CQL.

    Identifiers reference variables, parameters, or definitions
    by their simple name.

    Example:
        Patient
        Age

    Attributes:
        name: The identifier name.
        quoted: True if the identifier was double-quoted in CQL source.
    """

    name: str
    quoted: bool = False


@dataclass
class QualifiedIdentifier(Expression):
    """
    Represents a qualified (dotted) identifier reference.

    Qualified identifiers reference items from included libraries
    or nested properties.

    Example:
        FHIRHelpers.ToDateTime
        FHIR.Patient

    Attributes:
        parts: List of identifier parts forming the qualified path.
    """

    parts: List[str] = field(default_factory=list)


@dataclass
class Property(Expression):
    """
    Represents a property access expression.

    Properties access fields or attributes of a source expression.

    Examples:
        Patient.name
        P.birthDate
        condition.code

    Attributes:
        source: The source expression (None for implicit context).
        path: The property path/name.
    """

    source: Optional[Expression] = None
    path: str = ""


@dataclass
class MethodInvocation(Expression):
    """
    Method invocation expression.

    CQL: Patient.ageInYears()
    CQL: observations.where(O.status = 'final')

    This is syntactic sugar for the function form.
    Patient.ageInYears() is equivalent to AgeInYears(Patient)
    """

    source: Expression
    method: str
    arguments: List[Expression] = field(default_factory=list)


@dataclass
class AliasRef(Expression):
    """
    Represents a reference to a query alias.

    Used within query expressions to reference source aliases.

    Example:
        In "P.age", P is an alias reference.

    Attributes:
        name: The alias name.
    """

    name: str


# ==============================================================================
# Function and Operator Expressions
# ==============================================================================


@dataclass
class FunctionRef(Expression):
    """
    Represents a function call expression.

    Function calls invoke named functions with arguments.

    Example:
        ToString(123)
        FHIRHelpers.ToQuantity(value)

    Attributes:
        name: The function name (may be qualified).
        arguments: List of argument expressions.
    """

    name: str
    arguments: List[Expression] = field(default_factory=list)


@dataclass
class BinaryExpression(Expression):
    """
    Represents a binary operator expression.

    Binary expressions combine two operands with an operator.

    Examples:
        1 + 2
        Patient.age >= 18
        name = 'John'

    Attributes:
        operator: The operator symbol or name.
        left: The left operand expression.
        right: The right operand expression.
    """

    operator: str
    left: Expression
    right: Expression


@dataclass
class UnaryExpression(Expression):
    """
    Represents a unary operator expression.

    Unary expressions apply an operator to a single operand.

    Examples:
        -5
        not true
        exists elements

    Attributes:
        operator: The operator symbol or name.
        operand: The operand expression.
    """

    operator: str
    operand: Expression


@dataclass
class DurationBetween(Expression):
    """
    Represents a duration calculation between two date/time values.

    Duration calculations return the number of whole calendar periods
    between two dates.

    Examples:
        years between @2014 and @2016
        months between @2024-01-01 and @2024-06-15
        days between A and B

    Attributes:
        precision: The precision/unit (year, month, week, day, hour, minute, second, millisecond).
        operand_left: The left operand (start date/time).
        operand_right: The right operand (end date/time).
    """

    precision: str
    operand_left: Expression
    operand_right: Expression


@dataclass
class DifferenceBetween(Expression):
    """
    Represents a difference calculation between two date/time values.

    Difference calculations return the number of boundaries crossed
    between two dates.

    Examples:
        difference in years between @2014 and @2016
        difference in days between A and B

    Attributes:
        precision: The precision/unit (year, month, week, day, hour, minute, second, millisecond).
        operand_left: The left operand (start date/time).
        operand_right: The right operand (end date/time).
    """

    precision: str
    operand_left: Expression
    operand_right: Expression


@dataclass
class DateComponent(Expression):
    """
    Represents extraction of a date/time component from a value.

    Component extraction retrieves a specific part of a date/time.

    Examples:
        year from @2024-01-15
        month from DateTime(2024, 6, 15)
        day from Patient.birthDate
        hour from @T12:30:00

    Attributes:
        component: The component to extract (year, month, day, hour, minute, second, millisecond).
        operand: The date/time expression to extract from.
    """

    component: str
    operand: Expression


@dataclass
class ConditionalExpression(Expression):
    """
    Represents a conditional (if-then-else) expression.

    Conditional expressions evaluate to one of two branches
    based on a condition.

    Example:
        if X then 1 else 0

    Attributes:
        condition: The condition expression.
        then_expr: The expression if condition is true.
        else_expr: The expression if condition is false.
    """

    condition: Expression
    then_expr: Expression
    else_expr: Expression


@dataclass
class CaseItem(ASTNode):
    """
    Represents a single case item in a case expression.

    Each case item has a when condition and a then result.

    Attributes:
        when: The when condition expression.
        then: The then result expression.
    """

    when: Expression
    then: Expression


@dataclass
class CaseExpression(Expression):
    """
    Represents a case expression.

    Case expressions provide multi-way conditional branching.

    Example:
        case
            when X < 0 then 'negative'
            when X > 0 then 'positive'
            else 'zero'
        end

    Attributes:
        case_items: List of case items (when-then pairs).
        else_expr: The else expression (default case).
        comparand: Optional comparand for simple case expressions.
    """

    case_items: List[CaseItem] = field(default_factory=list)
    else_expr: Optional[Expression] = None
    comparand: Optional[Expression] = None


# ==============================================================================
# Query Expressions
# ==============================================================================


@dataclass
class QuerySource(ASTNode):
    """
    Represents a source clause in a query expression.

    A query source defines an alias for a data source.

    Example:
        [Patient] P
        conditions C

    Attributes:
        alias: The alias name for the source.
        expression: The source expression (retrieve or identifier).
    """

    alias: str
    expression: Expression


@dataclass
class Retrieve(Expression):
    """
    Represents a retrieve expression for accessing clinical data.

    Retrieve expressions query data from the data model,
    optionally filtered by terminology.

    Examples:
        [Patient]                    -- All patients
        [Condition]                  -- All conditions
        [Condition: "Diabetes"]      -- Conditions with specific code
        [Observation: "LOINC|1234"]  -- Observations with LOINC code
        [Condition -> subject]       -- Related context retrieve via subject property

    Attributes:
        type: The resource/data type name.
        terminology: Optional terminology filter (value set, code, etc.).
        terminology_property: Property to match terminology against (e.g., 'code').
        navigation_path: Optional property path for related context retrieve (-> syntax).
    """

    type: str
    terminology: Optional[Expression] = None
    terminology_property: Optional[str] = None
    navigation_path: Optional[str] = None


@dataclass
class WithClause(ASTNode):
    """
    Represents a 'with' or 'without' clause in a query expression.

    With clauses define relationships between the main source
    and related data that must exist.
    Without clauses define relationships where related data must NOT exist.

    Example:
        with [Encounter] E such that E.status = 'finished'
        without [Condition] C such that C.subject = P.id

    Attributes:
        alias: The alias for the related source.
        expression: The related source expression.
        such_that: The relationship condition.
        is_without: If True, this is a 'without' clause (notExists), else 'with' (exists).
    """

    alias: str
    expression: Expression
    such_that: Expression
    is_without: bool = False


@dataclass
class LetClause(ASTNode):
    """
    Represents a 'let' clause in a query expression.

    Let clauses define local variables within a query scope.

    Example:
        let ageInYears: AgeInYears()

    Attributes:
        alias: The variable name.
        expression: The expression to bind to the variable.
    """

    alias: str
    expression: Expression


@dataclass
class SortByItem(ASTNode):
    """
    Represents a single sort criterion in a sort clause.

    Attributes:
        direction: Sort direction ('asc' or 'desc').
        expression: The expression to sort by.
    """

    direction: str = "asc"
    expression: Optional[Expression] = None


@dataclass
class SortClause(ASTNode):
    """
    Represents a sort clause in a query expression.

    Sort clauses specify the ordering of query results.

    Example:
        sort by birthDate asc

    Attributes:
        by: List of sort items specifying sort criteria.
    """

    by: List[SortByItem] = field(default_factory=list)


@dataclass
class ReturnClause(ASTNode):
    """
    Represents a return clause in a query expression.

    Return clauses specify the shape of query results.

    Example:
        return P.name
        return all P.name
        return distinct P.name

    Attributes:
        expression: The expression to return for each element.
        distinct: If True, apply distinct. If False, return all (default).
    """

    expression: Expression
    distinct: bool = False


@dataclass
class WhereClause(ASTNode):
    """
    Represents a where clause in a query expression.

    Where clauses filter query results based on conditions.

    Example:
        where P.active = true

    Attributes:
        expression: The filter condition.
    """

    expression: Expression


@dataclass
class AggregateClause(ASTNode):
    """
    Represents an aggregate clause in a query expression.

    Aggregate clauses perform custom aggregation over query results.

    Example:
        aggregate Result starting 1: Result + X
        aggregate distinct Result: Coalesce(Result, 0) + X
        aggregate all Result: Result + X

    Attributes:
        identifier: The accumulator variable name (e.g., "Result").
        expression: The aggregation expression.
        starting: Optional starting value expression.
        distinct: Whether to use distinct modifier.
        all_: Whether to use all modifier.
    """

    identifier: str
    expression: Expression
    starting: Optional[Expression] = None
    distinct: bool = False
    all_: bool = False


@dataclass
class Query(Expression):
    """
    Represents a complete CQL query expression.

    Queries are the primary mechanism for retrieving and
    transforming data in CQL.

    Example:
        [Patient] P
            where P.active = true
            sort by birthDate asc

    Attributes:
        source: The primary query source(s).
        where: Optional where clause for filtering.
        return_clause: Optional return clause for projection.
        sort: Optional sort clause for ordering.
        with_clauses: List of with clauses for relationships.
        let_clauses: List of let clauses for local variables.
        relationships: Additional relationship clauses (without, etc.).
    """

    source: Union[QuerySource, List[QuerySource]]
    where: Optional[WhereClause] = None
    return_clause: Optional[ReturnClause] = None
    sort: Optional[SortClause] = None
    with_clauses: List[WithClause] = field(default_factory=list)
    let_clauses: List[LetClause] = field(default_factory=list)
    relationships: List[Any] = field(default_factory=list)
    aggregate: Optional["AggregateClause"] = None


# ==============================================================================
# Type Specifiers
# ==============================================================================


@dataclass
class NamedTypeSpecifier(TypeSpecifier):
    """
    Represents a named type reference.

    Named types reference built-in or model-defined types.

    Examples:
        Integer
        String
        DateTime
        FHIR.Patient

    Attributes:
        name: The type name (may be qualified).
    """

    name: str


@dataclass
class IntervalTypeSpecifier(TypeSpecifier):
    """
    Represents an interval type specifier.

    Interval types define ranges of a point type.

    Example:
        Interval<Integer>
        Interval<DateTime>

    Attributes:
        point_type: The type of values in the interval.
    """

    point_type: TypeSpecifier


@dataclass
class ListTypeSpecifier(TypeSpecifier):
    """
    Represents a list type specifier.

    List types define collections of elements of a specific type.

    Example:
        List<String>
        List<Observation>

    Attributes:
        element_type: The type of list elements.
    """

    element_type: TypeSpecifier


@dataclass
class TupleElement(ASTNode):
    """
    Represents a single element in a tuple type specifier.

    Attributes:
        name: The element name.
        type: The element type specifier.
    """

    name: str
    type: TypeSpecifier


@dataclass
class TupleTypeSpecifier(TypeSpecifier):
    """
    Represents a tuple type specifier.

    Tuple types define structured records with named fields.

    Example:
        Tuple { name: String, age: Integer }

    Attributes:
        elements: List of tuple element definitions.
    """

    elements: List[TupleElement] = field(default_factory=list)


@dataclass
class ChoiceTypeSpecifier(TypeSpecifier):
    """
    Represents a choice type specifier.

    Choice types allow a value to be one of several types.

    Example:
        Choice<Integer, String>
        Choice<DateTime, Date>

    Attributes:
        choices: List of possible type choices.
    """

    choices: List[TypeSpecifier] = field(default_factory=list)


# ==============================================================================
# Terminology Definitions
# ==============================================================================


@dataclass
class CodeSystemDefinition(ASTNode):
    """
    Represents a code system definition.

    Code systems define vocabularies of codes used in clinical contexts.

    Example:
        codesystem "LOINC": 'http://loinc.org' version '2.67'

    Attributes:
        name: The local name for the code system.
        id: The code system identifier (URI).
        version: The code system version.
    """

    name: str
    id: str
    version: Optional[str] = None


@dataclass
class ValueSetDefinition(ASTNode):
    """
    Represents a value set definition.

    Value sets define collections of codes from one or more code systems.

    Example:
        valueset "Diabetes Codes": 'http://example.org/fhir/ValueSet/diabetes'

    Attributes:
        name: The local name for the value set.
        id: The value set identifier (URI).
        version: The value set version.
        codesystem: Optional reference to the source code system.
    """

    name: str
    id: str
    version: Optional[str] = None
    codesystem: Optional[str] = None


@dataclass
class CodeDefinition(ASTNode):
    """
    Represents a code definition.

    Codes define individual clinical concepts from a code system.

    Example:
        code "Diabetes": '73211009' from "SNOMED-CT" display 'Diabetes mellitus'

    Attributes:
        name: The local name for the code.
        codesystem: The code system reference.
        code: The code value.
        display: Optional display string for the code.
    """

    name: str
    codesystem: str
    code: str
    display: Optional[str] = None


@dataclass
class ConceptDefinition(ASTNode):
    """
    Represents a concept definition.

    Concepts define clinical meanings as collections of codes.

    Example:
        concept "Blood Pressure": {
            code "Systolic": '8480-6' from "LOINC",
            code "Diastolic": '8462-4' from "LOINC"
        } display 'Blood pressure'

    Attributes:
        name: The local name for the concept.
        codes: List of code references or definitions.
        display: Optional display string for the concept.
    """

    name: str
    codes: List[Union[CodeDefinition, str]] = field(default_factory=list)
    display: Optional[str] = None


# ==============================================================================
# Function Definitions
# ==============================================================================


@dataclass
class ParameterDef(ASTNode):
    """
    Represents a parameter in a function definition.

    Attributes:
        name: The parameter name.
        type: The parameter type specifier.
        default: Optional default value.
    """

    name: str
    type: Optional[TypeSpecifier] = None
    default: Optional[Expression] = None


@dataclass
class FunctionDefinition(ASTNode):
    """
    Represents a function definition within a library.

    Functions define reusable computations with parameters.

    Example:
        define function AgeInYears(birthDate Date):
            years between birthDate and Today()

    Attributes:
        name: The function name.
        parameters: List of parameter definitions.
        return_type: Optional return type specifier.
        expression: The function body expression.
        access_level: Access level ('public' or 'private').
        fluent: Whether this is a fluent function.
    """

    name: str
    parameters: List[ParameterDef] = field(default_factory=list)
    return_type: Optional[TypeSpecifier] = None
    expression: Optional[Expression] = None
    access_level: Optional[str] = None
    fluent: bool = False


# ==============================================================================
# Additional Expression Types
# ==============================================================================


@dataclass
class ListExpression(Expression):
    """
    Represents a list literal expression.

    List literals define collections of values.

    Example:
        { 1, 2, 3, 4, 5 }
        { 'a', 'b', 'c' }

    Attributes:
        elements: List of element expressions.
    """

    elements: List[Expression] = field(default_factory=list)


@dataclass
class TupleExpression(Expression):
    """
    Represents a tuple literal expression.

    Tuple literals define structured records with named fields.

    Example:
        Tuple { name: 'John', age: 30 }

    Attributes:
        elements: List of tuple element expressions (name, value pairs).
    """

    elements: List[TupleElement] = field(default_factory=list)


@dataclass
class InstanceExpression(Expression):
    """
    Represents an instance expression for creating typed values.

    Instance expressions create values of a specific type.

    Example:
        Interval[1, 10]
        Quantity { value: 5, unit: 'mg' }

    Attributes:
        type: The type name being instantiated.
        elements: List of element values (for structured types).
    """

    type: str
    elements: List[TupleElement] = field(default_factory=list)


@dataclass
class ExistsExpression(Expression):
    """
    Represents an exists expression (tests if list is non-empty).

    Example:
        exists [Condition]

    Attributes:
        source: The source expression to test.
    """

    source: Expression


@dataclass
class AggregateExpression(Expression):
    """
    Represents an aggregate expression (sum, count, min, max, etc.).

    Example:
        Sum([1, 2, 3])
        Count([Patient])

    Attributes:
        source: The source expression to aggregate.
        operator: The aggregate operator name.
        initializer: Optional initializer value.
    """

    source: Expression
    operator: str
    initializer: Optional[Expression] = None


@dataclass
class IndexerExpression(Expression):
    """
    Represents an indexer expression (array/list access).

    Example:
        names[0]

    Attributes:
        source: The source expression (list/tuple).
        index: The index expression.
    """

    source: Expression
    index: Expression


@dataclass
class SkipExpression(Expression):
    """Skip first N elements from source."""
    source: Expression
    count: Expression


@dataclass
class TakeExpression(Expression):
    """Take first N elements from source."""
    source: Expression
    count: Expression


@dataclass
class FirstExpression(Expression):
    """Get first element from source."""
    source: Expression


@dataclass
class LastExpression(Expression):
    """Get last element from source."""
    source: Expression


@dataclass
class AnyExpression(Expression):
    """True if any element matches condition."""
    source: Expression
    alias: str
    condition: Expression


@dataclass
class AllExpression(Expression):
    """True if all elements match condition."""
    source: Expression
    alias: str
    condition: Expression


@dataclass
class SingletonExpression(Expression):
    """Return single element or null if empty/multiple."""
    source: Expression


@dataclass
class DistinctExpression(Expression):
    """Remove duplicate elements."""
    source: Expression


# ==============================================================================
# Type Aliases for Union Types
# ==============================================================================

# Expression union type for type hints
ExpressionNode = Union[
    Literal,
    DateTimeLiteral,
    TimeLiteral,
    Interval,
    Identifier,
    QualifiedIdentifier,
    Property,
    AliasRef,
    FunctionRef,
    BinaryExpression,
    UnaryExpression,
    ConditionalExpression,
    CaseExpression,
    Query,
    Retrieve,
    ListExpression,
    TupleExpression,
    InstanceExpression,
    ExistsExpression,
    AggregateExpression,
    IndexerExpression,
]

# Type specifier union type for type hints
TypeSpecifierNode = Union[
    NamedTypeSpecifier,
    IntervalTypeSpecifier,
    ListTypeSpecifier,
    TupleTypeSpecifier,
    ChoiceTypeSpecifier,
]


# ==============================================================================
# Exports
# ==============================================================================

__all__ = [
    # Base classes
    "ASTNode",
    "Expression",
    "TypeSpecifier",
    # Library structure
    "Library",
    "UsingDefinition",
    "IncludeDefinition",
    "ContextDefinition",
    "ParameterDefinition",
    "Definition",
    # Literals
    "Literal",
    "DateTimeLiteral",
    "TimeLiteral",
    "Interval",
    # Identifiers
    "Identifier",
    "QualifiedIdentifier",
    "Property",
    "MethodInvocation",
    "AliasRef",
    # Functions and operators
    "FunctionRef",
    "BinaryExpression",
    "UnaryExpression",
    "ConditionalExpression",
    "CaseExpression",
    "CaseItem",
    # Query expressions
    "Query",
    "QuerySource",
    "Retrieve",
    "WithClause",
    "LetClause",
    "SortClause",
    "SortByItem",
    "ReturnClause",
    "WhereClause",
    # Type specifiers
    "NamedTypeSpecifier",
    "IntervalTypeSpecifier",
    "ListTypeSpecifier",
    "TupleTypeSpecifier",
    "TupleElement",
    "ChoiceTypeSpecifier",
    # Terminology
    "CodeSystemDefinition",
    "ValueSetDefinition",
    "CodeDefinition",
    "ConceptDefinition",
    # Function definitions
    "FunctionDefinition",
    "ParameterDef",
    # Additional expressions
    "ListExpression",
    "TupleExpression",
    "InstanceExpression",
    "ExistsExpression",
    "AggregateExpression",
    "IndexerExpression",
    "Quantity",
    # Query operators
    "SkipExpression",
    "TakeExpression",
    "FirstExpression",
    "LastExpression",
    "AnyExpression",
    "AllExpression",
    "SingletonExpression",
    "DistinctExpression",
    # Duration expressions
    "DurationBetween",
    "DifferenceBetween",
    # Component extraction
    "DateComponent",
    # Type aliases
    "ExpressionNode",
    "TypeSpecifierNode",
]

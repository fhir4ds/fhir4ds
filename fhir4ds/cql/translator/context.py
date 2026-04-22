"""
Translation context for CQL to SQL translation.

This module provides the SQLTranslationContext class for managing
symbol tables, scope, parameters, and library resolution state.
"""

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from ..translator.queries import SQLQueryBuilder
    from ..translator.profile_registry import ProfileRegistry

from ..translator.column_registry import ColumnRegistry
from ..translator.warnings import TranslationWarnings


class ExprUsage(Enum):
    """
    How an expression's result will be used.

    This determines how Retrieve expressions are translated:
    - LIST: Return a collection (correlated subquery)
    - SCALAR: Return a single value (JOIN + column reference)
    - BOOLEAN: Truth test in WHERE/AND/OR (JOIN + IS NOT NULL)
    - EXISTS: Existence check (JOIN + IS NOT NULL, same as BOOLEAN)
    """
    LIST = auto()      # Default CQL semantics - return collection
    SCALAR = auto()    # Need single value (property access, comparison, FHIRPath arg)
    BOOLEAN = auto()   # Truth test (WHERE clause, AND/OR operands, NOT operand)
    EXISTS = auto()    # Existence test (exists() function) - treated same as BOOLEAN


class RowShape(Enum):
    """
    What a definition produces in terms of rows per patient.

    This determines the SQL pattern for joining/aggregating:
    - PATIENT_SCALAR: Exactly 1 row per patient (boolean, number, string)
    - PATIENT_MULTI_VALUE: 0..N scalar value rows per patient (no resource column)
    - RESOURCE_ROWS: 0..N resource rows per patient (has resource column)
    - UNKNOWN: Forward reference or complex expression
    """
    PATIENT_SCALAR = auto()       # Exactly 1 row per patient
    PATIENT_MULTI_VALUE = auto()  # 0..N scalar value rows per patient (no resource column)
    RESOURCE_ROWS = auto()        # 0..N resource rows per patient (has resource column)
    UNKNOWN = auto()              # Forward reference or complex expression


@dataclass
class SymbolInfo:
    """
    Information about a symbol in the translation context.

    Attributes:
        name: The symbol name.
        symbol_type: The type of symbol ('parameter', 'let', 'definition', 'alias', 'valueset', 'codesystem', 'code', 'include').
        sql_expr: The SQL expression for this symbol - can be str or SQLExpression AST node during migration (A-1).
        cql_type: The CQL type of the symbol (if known).
        scope_level: The scope level where this symbol was defined.
        union_expr: For aliases that are SQLUnion, store the actual object to avoid scalar context issues.
        source_alias: The source alias for the symbol.
        sql_ref: Alternative SQL reference (for translator.py compatibility).
    """

    name: str
    symbol_type: str
    sql_expr: Optional[Any] = None  # str or SQLExpression during migration (A-1)
    cql_type: Optional[str] = "Any"
    scope_level: int = 0
    union_expr: Any = None  # SQLUnion object when sql_expr == "__UNION__"
    source_alias: Optional[str] = None
    sql_ref: Optional[str] = None  # Alternative to sql_expr for translator.py compatibility
    ast_expr: Any = None  # AST expression object (set during Phase 1, converted to sql_expr in Phase 3)
    table_alias: Optional[str] = None  # Table alias for CTE references (e.g., "ESRDEncounter" -> table alias)
    cte_name: Optional[str] = None  # CTE name this alias points to (e.g., "Encounter: ValueSet")


@dataclass
class Scope:
    """
    A single scope level in the translation context.

    Scopes are nested to handle let clauses, query sources, etc.
    A barrier scope blocks upward symbol lookup (used for function inlining
    to prevent caller aliases from leaking into the inlined function body).
    """

    level: int
    symbols: Dict[str, SymbolInfo] = field(default_factory=dict)
    aliases: Set[str] = field(default_factory=set)
    barrier: bool = False


@dataclass
class ParameterInfo:
    """
    Information about a CQL parameter.

    Attributes:
        name: The parameter name.
        cql_type: The CQL type of the parameter.
        default_value: Optional default value expression.
        sql_param_index: The 1-based index for prepared statement parameters.
        placeholder: The SQL placeholder for this parameter (e.g., ":Measurement Period").
    """

    name: str
    cql_type: Optional[str] = None
    default_value: Optional[Any] = None
    sql_param_index: Optional[int] = None
    placeholder: Optional[str] = None


def _match_overload(
    overloads: List[Any], resource_type: str
) -> Optional[Any]:
    """Match a fluent function overload by resource type.

    Checks the first parameter's name and type specifier against the
    provided resource_type.  Supports exact match, prefix match (for
    profile names like 'ConditionProblemsHealthConcerns' matching 'Condition'),
    and ChoiceTypeSpecifier matching.

    Returns the best-matching FunctionInfo or None.
    """
    if not overloads or not resource_type:
        return None
    rt_lower = resource_type.lower()

    # Pass 1: exact match on type specifier (most specific)
    for func in overloads:
        params = getattr(func, "parameters", None)
        if not params:
            continue
        first_param = params[0]
        ptype = getattr(first_param, "type", None)
        if ptype is None:
            continue
        # NamedTypeSpecifier: exact name match
        type_name = getattr(ptype, "name", None)
        if type_name and type_name.lower() == rt_lower:
            return func
        # ChoiceTypeSpecifier: check each choice
        choices = getattr(ptype, "choices", None)
        if choices:
            for choice in choices:
                choice_name = getattr(choice, "name", None)
                if choice_name and choice_name.lower() == rt_lower:
                    return func

    # Pass 2: exact match on parameter name
    for func in overloads:
        params = getattr(func, "parameters", None)
        if not params:
            continue
        param_name = getattr(params[0], "name", "")
        if param_name and param_name.lower() == rt_lower:
            return func

    # Pass 3: prefix match — profile names often start with the base type
    # e.g., "ConditionProblemsHealthConcerns" starts with "Condition"
    for func in overloads:
        params = getattr(func, "parameters", None)
        if not params:
            continue
        param_name = getattr(params[0], "name", "")
        if param_name and rt_lower.startswith(param_name.lower()):
            return func

    return None


@dataclass
class LibraryInfo:
    """
    Information about an included library.

    Attributes:
        name: The library name/alias.
        path: The library path.
        version: The library version.
        alias: The local alias for the library.
        definitions: Dictionary of definition names to their expressions.
        functions: Dictionary of function names to FunctionInfo.
        function_overloads: Dictionary of function names to list of all overloads.
    """

    name: str
    path: str = ""
    version: Optional[str] = None
    alias: Optional[str] = None
    definitions: Dict[str, Any] = field(default_factory=dict)
    functions: Dict[str, Any] = field(default_factory=dict)
    function_overloads: Dict[str, List[Any]] = field(default_factory=dict)
    library_ast: Optional[Any] = None


@dataclass
class FunctionInfo:
    """
    Information about a CQL function definition.

    Attributes:
        name: The function name.
        parameters: List of parameter definitions.
        return_type: The return type of the function.
        expression: The function body expression.
        is_fluent: Whether this is a fluent function.
        library_alias: The alias of the library defining this function.
    """

    name: str
    parameters: List[Any] = field(default_factory=list)
    return_type: Optional[str] = None
    expression: Optional[Any] = None
    is_fluent: bool = False
    library_alias: Optional[str] = None


@dataclass
class PatientContext:
    """
    Patient context for single-patient evaluation.

    Attributes:
        patient_id: The current patient ID.
        patient_resource: The full patient resource.
    """

    patient_id: Optional[str] = None
    patient_resource: Optional[Dict[str, Any]] = None


@dataclass
class MeasurementPeriod:
    """
    Measurement period for quality measures.

    Attributes:
        start: The start date/time of the measurement period.
        end: The end date/time of the measurement period.
    """

    start: Optional[str] = None
    end: Optional[str] = None


@dataclass
class ParameterBinding:
    """
    Parameter binding with optional default value.

    Attributes:
        name: The parameter name.
        param_type: The parameter type.
        default_value: Optional default value.
        value: The current bound value.
    """

    name: str
    param_type: str = "Any"
    default_value: Optional[Any] = None
    value: Optional[Any] = None

    @property
    def placeholder(self) -> str:
        """Get the parameter placeholder for SQL."""
        return f":{self.name}"


@dataclass
class DefinitionMeta:
    """
    Metadata about a translated definition.

    Attributes:
        name: The definition name.
        shape: The RowShape of the definition's output.
        cql_type: The CQL type (Boolean, Integer, String, Resource, List<T>).
        has_resource: Whether the CTE includes a resource column.
        value_column: The column containing the scalar result.
        patient_key_col: The patient key column name.
        tracked_refs: CTE references tracked during expression translation (for JOIN generation).
    """

    name: str
    shape: RowShape
    cql_type: str = "Any"
    has_resource: bool = False
    value_column: str = "value"
    patient_key_col: str = "patient_id"
    tracked_refs: Dict[Tuple[str, str], Any] = field(default_factory=dict)
    uses_demographics: bool = False
    projects_value: bool = False  # True when CTE projects a value/resource column
    is_tuple: bool = False  # True when CTE returns a tuple (to_json(struct_pack(...)))
    sql_result_type: Optional[str] = None  # Result type hint from translated SQL (e.g., "Quantity")
    quantity_fields: Optional[set] = None  # Tuple field names known to carry Quantity values
    source_resource_ctes: list = field(default_factory=list)
    # Transitive list of RESOURCE_ROWS CTE names this PATIENT_SCALAR non-boolean
    # definition depends on (e.g. "Lowest Systolic Reading" → Observation retrieve CTE).
    # Populated by CTEManager for non-boolean PATIENT_SCALAR definitions.
    # Consumed by _collect_audit_evidence_exprs (Strategy 3) to propagate evidence
    # through scalar intermediaries into comparison-based boolean definitions.
    audit_target_expr: Optional[Any] = None
    # Stored audit target SQL expression (SQLSubquery) from First/Last attribution.
    # When a definition like "Lowest Systolic Reading" uses First() on a RESOURCE_ROWS
    # source, the winning resource's ID subquery is stored here so that downstream
    # comparisons can populate the `target` field even after CTE serialization.

    @property
    def is_scalar(self) -> bool:
        """True if definition produces exactly one value per patient."""
        return self.shape == RowShape.PATIENT_SCALAR

    @property
    def is_multi_row(self) -> bool:
        """True if definition produces 0..N rows per patient."""
        return self.shape in (RowShape.RESOURCE_ROWS, RowShape.PATIENT_MULTI_VALUE)


@dataclass
class SQLTranslationContext:
    """
    Context for CQL to SQL translation.

    Manages symbol tables, scope management, parameter tracking,
    and library resolution state.

    Attributes:
        current_context: The current CQL context ('Patient', 'Population', etc.).
        library_name: The name of the current library being translated.
        library_version: The version of the current library.
        parameters: Dictionary of parameter name to ParameterInfo.
        definitions: Dictionary of definition name to SQL expression (string).
        definition_asts: Dictionary of definition name to SQLExpression AST nodes.
        includes: Dictionary of library alias to LibraryInfo.
        valuesets: Dictionary of valueset name to URL.
        codesystems: Dictionary of codesystem name to URL.
        codes: Dictionary of code name to code info.
        scopes: Stack of scope levels.
        current_scope_level: The current scope nesting level.
        resource_alias: The current resource alias (for query context).
        cte_counter: Counter for generating unique CTE names.
        param_counter: Counter for assigning parameter indices.
    """

    current_context: str = "Patient"
    library_name: Optional[str] = None
    library_version: Optional[str] = None

    # Symbol tables
    parameters: Dict[str, ParameterInfo] = field(default_factory=dict)
    definitions: Dict[str, str] = field(default_factory=dict)
    definition_asts: Dict[str, Any] = field(default_factory=dict)  # Store AST nodes alongside SQL strings
    includes: Dict[str, LibraryInfo] = field(default_factory=dict)
    valuesets: Dict[str, str] = field(default_factory=dict)
    codesystems: Dict[str, str] = field(default_factory=dict)
    codes: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Function definitions in current library
    _functions: Dict[str, FunctionInfo] = field(default_factory=dict)
    # Overloaded function storage: name -> list of all overloads
    _function_overloads: Dict[str, List[FunctionInfo]] = field(default_factory=dict)

    # All definition names (for forward reference resolution)
    _definition_names: Set[str] = field(default_factory=set)

    # Scope management
    scopes: List[Scope] = field(default_factory=list)
    current_scope_level: int = 0

    # Query context
    resource_alias: Optional[str] = None
    resource_type: Optional[str] = None
    # Maps query alias names to their FHIR resource types for overload resolution
    _alias_resource_types: Dict[str, str] = field(default_factory=dict)

    # Patient context tracking for correlated subqueries
    patient_alias: Optional[str] = None  # e.g., "p" when in "FROM patients p"
    current_patient_id: Optional[str] = None  # For single-patient evaluation

    # Single-patient evaluation context
    _patient_context: PatientContext = field(default_factory=PatientContext)

    # Dedicated field retained for backward API compatibility; always kept
    # in sync with _parameter_bindings["Measurement Period"] by set_measurement_period().
    _measurement_period: MeasurementPeriod = field(default_factory=MeasurementPeriod)

    # Generic parameter bindings: maps parameter name → (start, end) tuple for
    # interval parameters, or scalar value for non-interval parameters.
    # Populated from both runtime arguments and CQL default values.
    _parameter_bindings: Dict[str, Any] = field(default_factory=dict)

    # Execution context type
    _context_type: str = "Unfiltered"

    # Configuration
    _use_fhirpath_udfs: bool = True
    _connection: Optional[Any] = None
    _audit_mode: bool = False
    _audit_expressions: bool = True  # False → population-only audit (no expression wrapping)
    _audit_or_strategy: str = "true_branch"

    # Counters
    cte_counter: int = 0
    param_counter: int = 0
    _subquery_cte_counter: int = 0

    # CTE name tracking
    _used_cte_names: Set[str] = field(default_factory=set)

    # Let variables (for query-scope bindings) - maps name to SQL AST expression
    let_variables: Dict[str, Any] = field(default_factory=dict)

    # Expression definitions (named expressions in CQL)
    expression_definitions: Dict[str, Any] = field(default_factory=dict)

    # CTEs accumulated during translation
    _ctes: List[Any] = field(default_factory=list)

    # Query builder for tracking CTE references and generating JOINs
    query_builder: Optional["SQLQueryBuilder"] = None

    # Definition metadata
    definition_meta: Dict[str, DefinitionMeta] = field(default_factory=dict)

    # Warnings
    warnings: TranslationWarnings = field(default_factory=TranslationWarnings)

    # Strict mode - treat warnings as errors
    strict_mode: bool = False

    # Included definition tracking
    _included_definition_names: Set[str] = field(default_factory=set)

    # Alias scope stack for Any/All expressions
    _alias_scopes: List[str] = field(default_factory=list)

    # Column registry for precomputed columns
    column_registry: ColumnRegistry = field(default_factory=ColumnRegistry)

    # FHIR Schema registry for dynamic type queries (Task B1)
    fhir_schema: Optional["FHIRSchemaRegistry"] = None

    # Extension paths for profile virtual properties (versioned)
    extension_paths: Optional[Dict[str, Any]] = None

    # Profile registry for QI Core profile/model knowledge (Layer 2)
    profile_registry: Optional["ProfileRegistry"] = None

    # Precomputed column name mappings (FHIRPath → SQL column), from versioned FHIR R4 dir
    column_mappings: Optional[Dict[str, str]] = None

    # Choice type column prefixes (e.g., {"value", "onset", "effective"}), from versioned FHIR R4 dir
    choice_type_prefixes: Optional[Set[str]] = None

    # Dynamic component code to column mapping (Tier 7: E2)
    # Maps LOINC codes or code names to precomputed column names
    # E.g., "8480-6" -> "systolic_value"
    component_code_to_column: Dict[str, str] = field(default_factory=dict)

    # Patient demographics CTE available for age calculations
    has_patient_demographics_cte: bool = False

    # Shared FunctionInliner for expand-then-translate architecture
    # Initialized once in translator.py, reused across all expression translations
    function_inliner: Optional[Any] = None

    # Cached FluentFunctionTranslator for the hardcoded registry path
    _fluent_translator: Optional[Any] = None

    def __post_init__(self):
        """Initialize the root scope, default parameter bindings, and profile registry."""
        if not self.scopes:
            self.scopes.append(Scope(level=0))
        # Pre-register "Measurement Period" with (None, None) so that expression
        # translation emits {mp_start}/{mp_end} template placeholders even when no
        # concrete dates have been set.  This mirrors what _process_parameters does
        # for CQL-declared interval parameters.
        if "Measurement Period" not in self._parameter_bindings:
            self._parameter_bindings["Measurement Period"] = (None, None)

        # Guarantee profile_registry is always available (Context SSOT invariant).
        # Downstream code must never fall back to get_default_profile_registry().
        if self.profile_registry is None:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "SQLTranslationContext created without profile_registry; "
                "falling back to default. This should be fixed at the call site."
            )
            from ..translator.profile_registry import get_default_profile_registry
            self.profile_registry = get_default_profile_registry()

    def push_scope(self) -> int:
        """
        Push a new scope onto the scope stack.

        Returns:
            The new scope level.
        """
        self.current_scope_level += 1
        self.scopes.append(Scope(level=self.current_scope_level))
        return self.current_scope_level

    def pop_scope(self) -> Optional[Scope]:
        """
        Pop the current scope from the scope stack.

        Returns:
            The popped scope, or None if at root scope.
        """
        if len(self.scopes) <= 1:
            return None

        scope = self.scopes.pop()
        self.current_scope_level -= 1
        return scope

    def add_symbol(self, name: str, symbol_type: str, sql_expr: Optional[str] = None, cql_type: Optional[str] = None, union_expr: Any = None, ast_expr: Any = None, table_alias: Optional[str] = None, cte_name: Optional[str] = None) -> None:
        """
        Add a symbol to the current scope.

        Args:
            name: The symbol name.
            symbol_type: The type of symbol.
            sql_expr: The SQL expression for this symbol (string, used in Phase 3).
            cql_type: The CQL type of the symbol.
            union_expr: Optional SQLUnion object when the source is a union (to avoid scalar context issues).
            ast_expr: AST expression object (set during Phase 1, should not call to_sql() until Phase 3).
            table_alias: Table alias for CTE references (e.g., "ESRDEncounter" -> table alias in JOIN).
            cte_name: CTE name this alias points to (e.g., "Encounter: ValueSet").
        """
        symbol = SymbolInfo(
            name=name,
            symbol_type=symbol_type,
            sql_expr=sql_expr,
            cql_type=cql_type,
            scope_level=self.current_scope_level,
            union_expr=union_expr,
            ast_expr=ast_expr,
            table_alias=table_alias,
            cte_name=cte_name,
        )
        self.scopes[-1].symbols[name] = symbol

    def lookup_symbol(self, name: str) -> Optional[SymbolInfo]:
        """
        Look up a symbol in the scope chain.

        Searches from the current scope outward to the root scope.
        Stops at barrier scopes to prevent caller aliases from leaking
        into inlined function bodies.

        Args:
            name: The symbol name to look up.

        Returns:
            The symbol info, or None if not found.
        """
        # Search scopes from innermost to outermost
        for scope in reversed(self.scopes):
            if name in scope.symbols:
                return scope.symbols[name]
            # Stop at barrier scopes (function inlining boundary)
            if scope.barrier:
                break

        # Check parameters
        if name in self.parameters:
            param = self.parameters[name]
            return SymbolInfo(
                name=name,
                symbol_type="parameter",
                cql_type=param.cql_type,
            )

        # Check definitions
        if name in self.definitions:
            return SymbolInfo(
                name=name,
                symbol_type="definition",
                sql_expr=self.definitions[name],
            )

        return None

    def add_alias(self, alias: str, sql_expr: Optional[str] = None, union_expr: Any = None, ast_expr: Any = None, table_alias: Optional[str] = None, cte_name: Optional[str] = None) -> None:
        """
        Add a query alias to the current scope.

        Args:
            alias: The alias name.
            sql_expr: Optional SQL expression for the alias (for complex sources, string form).
            union_expr: Optional SQLUnion object when the source is a union (to avoid scalar context issues).
            ast_expr: AST expression object (set during Phase 1, should not call to_sql() until Phase 3).
            table_alias: Table alias for CTE references (e.g., "ESRDEncounter" -> table alias in JOIN).
            cte_name: CTE name this alias points to (e.g., "Encounter: ValueSet").
        """
        self.scopes[-1].aliases.add(alias)
        self.add_symbol(alias, "alias", sql_expr=sql_expr, union_expr=union_expr, ast_expr=ast_expr, table_alias=table_alias, cte_name=cte_name)

    def is_alias(self, name: str) -> bool:
        """
        Check if a name is a query alias.

        Respects barrier scopes to prevent caller aliases from leaking
        into inlined function bodies.

        Args:
            name: The name to check.

        Returns:
            True if the name is an alias in any scope (up to the nearest barrier).
        """
        for scope in reversed(self.scopes):
            if name in scope.aliases:
                return True
            if scope.barrier:
                break
        return False

    def push_alias_scope(self, alias: str) -> None:
        """
        Push a new scope with an alias for lambda expression evaluation.

        This is used for Any/All expressions where an alias needs to be
        temporarily available during condition translation.

        Args:
            alias: The alias name to add to the new scope.
        """
        self.push_scope()
        self.add_alias(alias)

    def pop_alias_scope(self) -> None:
        """
        Pop the scope created by push_alias_scope.

        This removes the temporary alias scope after lambda condition evaluation.
        """
        self.pop_scope()

    def add_parameter(self, name: str, cql_type: Optional[str] = None, default_value: Optional[Any] = None) -> ParameterInfo:
        """
        Add a parameter definition.

        Args:
            name: The parameter name.
            cql_type: The CQL type of the parameter.
            default_value: Optional default value.

        Returns:
            The created ParameterInfo.
        """
        self.param_counter += 1
        param = ParameterInfo(
            name=name,
            cql_type=cql_type,
            default_value=default_value,
            sql_param_index=self.param_counter,
            placeholder=f":{name}",
        )
        self.parameters[name] = param
        return param

    def add_include(self, alias: str, path: str, version: Optional[str] = None) -> LibraryInfo:
        """
        Add an included library.

        Args:
            alias: The local alias for the library.
            path: The library path.
            version: The library version.

        Returns:
            The created LibraryInfo.
        """
        lib = LibraryInfo(name=alias, path=path, version=version)
        self.includes[alias] = lib
        return lib

    def add_valueset(self, name: str, url: str) -> None:
        """
        Add a valueset definition.

        Args:
            name: The valueset name.
            url: The valueset URL.
        """
        self.valuesets[name] = url

    def define_valueset(self, name: str, url: str) -> None:
        """
        Define a valueset (alias for add_valueset for compatibility).

        Args:
            name: The valueset name.
            url: The valueset URL.
        """
        self.valuesets[name] = url

    def add_codesystem(self, name: str, url: str) -> None:
        """
        Add a codesystem definition.

        Args:
            name: The codesystem name.
            url: The codesystem URL.
        """
        self.codesystems[name] = url

    def add_code(self, name: str, codesystem: str, code: str, display: Optional[str] = None) -> None:
        """
        Add a code definition.

        Args:
            name: The code name.
            codesystem: The codesystem name.
            code: The code value.
            display: Optional display string.
        """
        self.codes[name] = {
            "codesystem": codesystem,
            "code": code,
            "display": display,
        }

    def add_definition(self, name: str, sql_expr: Optional[str] = None, ast_expr: Optional[Any] = None) -> None:
        """
        Add a named definition with optional AST node.

        Store AST nodes directly to preserve structure. Only render at final output.

        Args:
            name: The definition name.
            sql_expr: Optional SQL expression string (legacy - will be phased out).
            ast_expr: Optional SQLExpression AST node for structural analysis.
        """
        if ast_expr is not None:
            self.definition_asts[name] = ast_expr
        if sql_expr is not None:
            self.definitions[name] = sql_expr
        elif ast_expr is not None:
            # Store the AST node directly — render only at final output (A-1)
            self.definitions[name] = ast_expr

    def get_definition(self, name: str) -> Optional[Any]:
        """
        Get a named definition by name.

        Args:
            name: The definition name.

        Returns:
            The SQL expression (str or SQLExpression AST node), or None if not found.
            During migration, this may return either a string or an AST node.
            Callers should handle both types.
        """
        return self.definitions.get(name)

    def get_definition_ast(self, name: str) -> Optional[Any]:
        """
        Get a named definition's AST node by name.

        Args:
            name: The definition name.

        Returns:
            The SQLExpression AST node, or None if not found.
        """
        return self.definition_asts.get(name)

    def get_definition_meta(self, name: str) -> Optional["DefinitionMeta"]:
        """
        Get metadata for a named definition.

        Args:
            name: The definition name.

        Returns:
            The DefinitionMeta, or None if not found.
        """
        return self.definition_meta.get(name)

    def generate_cte_name(self, prefix: str = "cte") -> str:
        """
        Generate a unique CTE name.

        Args:
            prefix: The prefix for the CTE name.

        Returns:
            A unique CTE name.
        """
        self.cte_counter += 1
        return f"{prefix}_{self.cte_counter}"

    def add_cte(self, cte: Any) -> None:
        """
        Add a CTE definition.

        Args:
            cte: The CTEDefinition to add.
        """
        # Avoid duplicates by name
        existing_names = {c.name for c in self._ctes}
        if cte.name not in existing_names:
            self._ctes.append(cte)

    def get_ctes(self) -> List[Any]:
        """
        Get all accumulated CTEs.

        Returns:
            List of CTEDefinition objects.
        """
        return list(self._ctes)

    def clear_ctes(self) -> None:
        """Clear all accumulated CTEs."""
        self._ctes.clear()

    def set_resource_context(self, alias: str, resource_type: str) -> None:
        """
        Set the current resource context for a query.

        Args:
            alias: The resource alias.
            resource_type: The FHIR resource type.
        """
        self.resource_alias = alias
        self.resource_type = resource_type

    def clear_resource_context(self) -> None:
        """Clear the current resource context."""
        self.resource_alias = None
        self.resource_type = None

    def get_resource_column(self, alias: Optional[str] = None) -> str:
        """
        Get the resource column reference for the given alias.

        Args:
            alias: The alias (uses current resource_alias if None).

        Returns:
            The column reference (e.g., "P.resource").
        """
        alias = alias or self.resource_alias
        if alias:
            return f"{alias}.resource"
        return "resource"

    def is_patient_context(self) -> bool:
        """Check if we're in Patient context."""
        return self.current_context == "Patient"

    def is_population_context(self) -> bool:
        """Check if we're in Population context."""
        return self.current_context == "Population"

    def set_context(self, context_name: str) -> None:
        """
        Set the current CQL context.

        Args:
            context_name: The context name ('Patient', 'Population', etc.).
        """
        self.current_context = context_name

    # -------------------------------------------------------------------------
    # Additional methods for compatibility with translator.py version
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """Reset the context to initial state."""
        self.definitions.clear()
        self.parameters.clear()
        self.includes.clear()
        self._functions.clear()
        self._function_overloads.clear()
        self.valuesets.clear()
        self.codesystems.clear()
        self.codes.clear()
        self._ctes.clear()
        self._patient_context = PatientContext()
        self._measurement_period = MeasurementPeriod()
        self._parameter_bindings = {}
        self._context_type = "Unfiltered"
        self._definition_names.clear()
        self._included_definition_names.clear()
        self._alias_scopes.clear()
        self._alias_resource_types.clear()
        self._used_cte_names.clear()
        self._subquery_cte_counter = 0
        self.scopes.clear()
        self.scopes.append(Scope(level=0))
        self.current_scope_level = 0
        self.function_inliner = None
        self._fluent_translator = None
        # Reset audit retrieve CTE names so stale names don't persist across calls
        if hasattr(self, '_audit_retrieve_cte_names'):
            self._audit_retrieve_cte_names = set()
        # Reset audit definition CTE names (definition CTEs with _audit_item passthrough)
        if hasattr(self, '_audit_definition_cte_names'):
            self._audit_definition_cte_names = set()

    # -------------------------------------------------------------------------
    # Configuration methods
    # -------------------------------------------------------------------------

    @property
    def fluent_translator(self):
        """Lazily create and cache a FluentFunctionTranslator for registry functions."""
        if self._fluent_translator is None:
            from ..translator.fluent_functions import FluentFunctionTranslator
            self._fluent_translator = FluentFunctionTranslator(self, lightweight=True)
        return self._fluent_translator

    @property
    def use_fhirpath_udfs(self) -> bool:
        """Whether to use FHIRPath UDFs for property access."""
        return self._use_fhirpath_udfs

    def set_use_fhirpath_udfs(self, value: bool) -> None:
        """Set whether to use FHIRPath UDFs."""
        self._use_fhirpath_udfs = value

    @property
    def audit_mode(self) -> bool:
        """Whether to emit audit structs wrapping boolean results."""
        return self._audit_mode

    def set_audit_mode(self, value: bool) -> None:
        """Set whether to use audit mode."""
        self._audit_mode = value

    @property
    def audit_expressions(self) -> bool:
        """Whether to wrap individual boolean expressions in audit macros.

        When True (default), AND/OR/NOT/comparisons are wrapped in audit_and,
        audit_or, etc.  When False (population-only audit), only retrieve CTEs
        carry _audit_item and the final population SELECT collects evidence —
        no expression-depth explosion.
        """
        return self._audit_expressions

    def set_audit_expressions(self, value: bool) -> None:
        """Set whether to wrap expressions in audit macros."""
        self._audit_expressions = value

    @property
    def audit_or_strategy(self) -> str:
        """The audit OR strategy: 'true_branch' or 'all'."""
        return self._audit_or_strategy

    def set_audit_or_strategy(self, value: str) -> None:
        """Set the audit OR strategy."""
        self._audit_or_strategy = value

    @property
    def connection(self) -> Optional[Any]:
        """Get the DuckDB connection if set."""
        return self._connection

    def set_connection(self, connection: Any) -> None:
        """Set the DuckDB connection."""
        self._connection = connection

    @property
    def context_type(self) -> str:
        """Get the current execution context type."""
        return self._context_type

    def set_context_type(self, context_type: str) -> None:
        """Set the execution context type."""
        self._context_type = context_type

    def set_resource_type(self, resource_type: Optional[str]) -> None:
        """Set the current resource type for fluent function context."""
        self.resource_type = resource_type

    # -------------------------------------------------------------------------
    # Backward compatibility properties
    # -------------------------------------------------------------------------

    @property
    def _definitions(self) -> Dict[str, Any]:
        """Alias for definitions for backward compatibility with translator.py."""
        return self.definitions

    @_definitions.setter
    def _definitions(self, value: Dict[str, Any]) -> None:
        """Setter for backward compatibility."""
        self.definitions = value

    # -------------------------------------------------------------------------
    # Patient context methods
    # -------------------------------------------------------------------------

    @property
    def patient_context(self) -> PatientContext:
        """Get the current patient context."""
        return self._patient_context

    def set_patient_id(self, patient_id: str) -> None:
        """Set the current patient ID."""
        self._patient_context.patient_id = patient_id

    def set_patient_resource(self, resource: Dict[str, Any]) -> None:
        """Set the full patient resource."""
        self._patient_context.patient_resource = resource

    # -------------------------------------------------------------------------
    # Measurement period methods (synced with generic _parameter_bindings)
    # -------------------------------------------------------------------------

    @property
    def measurement_period(self) -> MeasurementPeriod:
        """Get the measurement period."""
        return self._measurement_period

    def set_measurement_period(
        self, start: Optional[str] = None, end: Optional[str] = None
    ) -> None:
        """Set the measurement period and mirror it into generic parameter bindings."""
        if start:
            self._measurement_period.start = start
        if end:
            self._measurement_period.end = end
        # Always keep generic bindings in sync for "Measurement Period".
        # Registers (None, None) even when no dates are set so that template
        # placeholders ({mp_start}/{mp_end}) are emitted by the expression translator.
        self._parameter_bindings["Measurement Period"] = (
            self._measurement_period.start,
            self._measurement_period.end,
        )

    def set_parameter_binding(self, name: str, value: Any) -> None:
        """Store a generic parameter binding (e.g. interval tuple, scalar).

        For interval parameters, ``value`` should be a ``(start, end)`` tuple of
        strings.  For scalar parameters, any JSON-serialisable value is accepted.
        """
        self._parameter_bindings[name] = value

    def get_parameter_binding(self, name: str) -> Optional[Any]:
        """Return the binding for a parameter, or None if not set.

        Checks the generic bindings dict.  Interval parameters are pre-registered
        with ``(None, None)`` by ``_process_parameters`` so that template
        placeholders ({mp_start}/{mp_end} for "Measurement Period", or equivalent
        for other interval params) are emitted when no concrete dates have been set.
        """
        if name in self._parameter_bindings:
            return self._parameter_bindings[name]
        return None
        # No fallback needed: interval parameters are pre-registered with (None, None)
        # by _process_parameters when the CQL parameter declaration is processed.

    # -------------------------------------------------------------------------
    # Function management methods
    # -------------------------------------------------------------------------

    def define_function(self, func: FunctionInfo) -> None:
        """Define a function in the current library.
        
        Overloaded fluent functions are stored in _function_overloads
        to support type-aware resolution.
        """
        self._functions[func.name] = func
        # Track all overloads for type-aware dispatch
        if func.name not in self._function_overloads:
            self._function_overloads[func.name] = []
        self._function_overloads[func.name].append(func)

    def get_function(self, name: str, resource_type: Optional[str] = None) -> Optional[FunctionInfo]:
        """Get a function from the current library.
        
        If resource_type is provided, attempts to find the correct overload
        by matching the first parameter's name or type against the resource type.
        """
        if resource_type:
            overloads = self._function_overloads.get(name, [])
            match = _match_overload(overloads, resource_type)
            if match:
                return match
        return self._functions.get(name)

    def get_all_functions(self) -> Dict[str, FunctionInfo]:
        """Get all functions in the current library."""
        return dict(self._functions)

    def resolve_library_function(
        self, library_alias: str, function_name: str,
        resource_type: Optional[str] = None,
    ) -> Optional[FunctionInfo]:
        """Resolve a function from an included library.
        
        If resource_type is provided and the function has overloads,
        attempts to find the correct overload by matching parameter types.
        """
        library = self.includes.get(library_alias)
        if not library:
            return None
        # Try overload-aware resolution first
        if resource_type:
            overloads = library.function_overloads.get(function_name, [])
            match = _match_overload(overloads, resource_type)
            if match:
                return match
        return library.functions.get(function_name)

    # -------------------------------------------------------------------------
    # Definition management methods
    # -------------------------------------------------------------------------

    def define_expression(self, name: str, expr: Any) -> None:
        """Register a named expression/definition."""
        self._definition_names.add(name)
        self.expression_definitions[name] = expr

    def get_all_definitions(self) -> Dict[str, Any]:
        """Get all definitions in the current library."""
        return dict(self.expression_definitions)

    def get_all_parameters(self) -> Dict[str, ParameterInfo]:
        """Get all parameters in the current library."""
        return dict(self.parameters)

    def get_all_libraries(self) -> Dict[str, "LibraryInfo"]:
        """Get all included libraries."""
        return dict(self.includes)

    def register_included_definition(self, prefixed_name: str) -> None:
        """Register that an included definition was successfully loaded."""
        self._included_definition_names.add(prefixed_name)

    def has_included_definition(self, prefixed_name: str) -> bool:
        """Check if an included definition was successfully loaded."""
        return prefixed_name in self._included_definition_names

    # -------------------------------------------------------------------------
    # Terminology getter methods
    # -------------------------------------------------------------------------

    def get_valueset(self, name: str) -> Optional[str]:
        """Get a valueset URL by name."""
        return self.valuesets.get(name)

    def get_codesystem(self, name: str) -> Optional[str]:
        """Get a codesystem URL by name."""
        return self.codesystems.get(name)

    def get_code(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a code definition by name."""
        return self.codes.get(name)

    # -------------------------------------------------------------------------
    # Symbol management methods (additional for translator.py compatibility)
    # -------------------------------------------------------------------------

    def define_symbol(self, name: str, symbol_info: SymbolInfo) -> None:
        """Define a symbol in the current scope."""
        self.scopes[-1].symbols[name] = symbol_info

    def resolve_symbol(self, name: str) -> Optional[SymbolInfo]:
        """Resolve a symbol by name (alias for lookup_symbol)."""
        return self.lookup_symbol(name)

    def get_all_symbols(self) -> Dict[str, SymbolInfo]:
        """Get all defined symbols in current scope."""
        return dict(self.scopes[-1].symbols) if self.scopes else {}

    # -------------------------------------------------------------------------
    # CTE name tracking methods
    # -------------------------------------------------------------------------

    def generate_subquery_cte_name(self, prefix: str = "subq") -> str:
        """Generate a unique subquery CTE name."""
        self._subquery_cte_counter += 1
        name = f"{prefix}_{self._subquery_cte_counter}"
        while name in self._used_cte_names:
            self._subquery_cte_counter += 1
            name = f"{prefix}_{self._subquery_cte_counter}"
        self._used_cte_names.add(name)
        return name


__all__ = [
    "SymbolInfo",
    "Scope",
    "ParameterInfo",
    "LibraryInfo",
    "FunctionInfo",
    "PatientContext",
    "MeasurementPeriod",
    "ParameterBinding",
    "SQLTranslationContext",
    "ExprUsage",
    "RowShape",
    "DefinitionMeta",
    "TranslationWarnings",
]

"""
Main CQL to SQL Translator.

This module provides the main CQLToSQLTranslator class that orchestrates
the translation of CQL libraries to DuckDB SQL using FHIRPath UDFs.

Population-First Approach:
    All translations follow a population-first pattern where queries return
    one row per patient. This is optimized for quality measure evaluation
    where you need to evaluate many patients simultaneously.

    The generated SQL structure:
    1. patients CTE - distinct patient IDs from resources table
    2. Definition CTEs - one per CQL definition, filtered per patient
    3. Final SELECT - LEFT JOINs to produce one row per patient

Key Classes:
    - CQLToSQLTranslator: Main translator class
    - SQLTranslationContext: Context for tracking symbols, parameters, CTEs
    - ParameterBinding: Runtime parameter with optional default
    - PatientContext: Single-patient evaluation context

Reference: docs/PLAN-CQL-TO-SQL-TRANSLATOR.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

_logger = logging.getLogger(__name__)

# Well-known CQL definition name used as the default final definition
# when no explicit final_definition is provided to translate().
_DEFAULT_FINAL_DEFINITION = "Initial Population"

if TYPE_CHECKING:
    import duckdb
    from ..translator.queries import SQLQueryBuilder

from ..errors import TranslationError
from ..parser.ast_nodes import (
    CodeSystemDefinition,
    ContextDefinition,
    Definition,
    Expression,
    FunctionDefinition,
    FunctionRef,
    Identifier,
    IncludeDefinition,
    Library,
    MethodInvocation,
    ParameterDefinition,
    Query,
    QuerySource,
    ValueSetDefinition,
)

from ..translator.types import (
    CTEDefinition,
    PRECEDENCE,
    SQLAlias,
    SQLArray,
    SQLAuditStruct,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLExpression,
    SQLFragment,
    SQLFunctionCall,
    SQLIdentifier,
    SQLList,
    SQLLiteral,
    SQLNull,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLRetrieveCTE,
    SQLJoin,
    SQLSelect,
    SQLSubquery,
    SQLWindowFunction,
    deduplicate_retrieve_ctes,
)
from ..translator.queries import SQLQueryBuilder, CTEReference
from ..translator.context import (
    MeasurementPeriod,
    SQLTranslationContext as ContextSQLTranslationContext,
)
from ..translator.retrieve_optimizer import run_optimization_phases
from ..translator.ast_utils import (
    ast_references_name,
    collect_cte_references,
    ast_has_correlated_ref,
    ast_has_patient_id_correlation,
    select_has_column,
    select_has_star,
)
from ..translator.cte_manager import CTEManagerMixin
from ..translator.correlation import CorrelationMixin
from ..translator.include_handler import IncludeHandlerMixin
from ..translator.inference import InferenceMixin
from ..translator.ast_helpers import ASTHelpersMixin

@dataclass
class SymbolInfo:
    """Information about a symbol in the translation context."""

    name: str
    symbol_type: str  # 'parameter', 'definition', 'alias', 'variable'
    cql_type: str = "Any"
    source_alias: Optional[str] = None
    sql_ref: Optional[str] = None
    union_expr: Any = None  # SQLUnion object when sql_ref == "__UNION__" or "__UNION_CASE__"

@dataclass
class FunctionInfo:
    """Information about a CQL function definition."""

    name: str
    parameters: List[Any]  # List of parameter definitions
    return_type: Optional[str] = None
    expression: Optional[Expression] = None
    is_fluent: bool = False
    library_alias: Optional[str] = None

@dataclass
class LibraryInfo:
    """Information about an included library."""

    name: str
    version: Optional[str] = None
    alias: Optional[str] = None
    path: Optional[str] = None
    definitions: Dict[str, Any] = field(default_factory=dict)
    functions: Dict[str, FunctionInfo] = field(default_factory=dict)

@dataclass
class PatientContext:
    """Patient context for single-patient evaluation."""

    patient_id: Optional[str] = None
    patient_resource: Optional[Dict[str, Any]] = None

@dataclass
class ParameterBinding:
    """Parameter binding with optional default value."""

    name: str
    param_type: str
    default_value: Optional[Any] = None
    value: Optional[Any] = None

    @property
    def placeholder(self) -> str:
        """Get the parameter placeholder for SQL."""
        return f":{self.name}"

# Use SQLTranslationContext from context.py - the canonical source
SQLTranslationContext = ContextSQLTranslationContext

class CQLToSQLTranslator(CTEManagerMixin, CorrelationMixin, IncludeHandlerMixin, InferenceMixin, ASTHelpersMixin):
    """
    Main translator for converting CQL to DuckDB SQL.

    This class coordinates the translation of CQL libraries, definitions,
    and expressions to SQL. It uses FHIRPath UDFs for property access
    and CQL UDFs/macros for operations.

    Example:
        from ..parser import CQLParser
        from ..translator import CQLToSQLTranslator

        parser = CQLParser()
        library = parser.parse(cql_text)

        translator = CQLToSQLTranslator()
        results = translator.translate_library(library)

        for name, sql_expr in results.items():
            print(f"{name}: {sql_expr.to_sql()}")
    """

    def __init__(
        self,
        connection: Optional[Any] = None,
        use_fhirpath_udfs: bool = True,
        library_loader: Optional[Callable[[str], Optional[Library]]] = None,
        model_config: Optional["ModelConfig"] = None,
        _library_cache: Optional[dict] = None,
        _resolving_stack: Optional[Set[tuple]] = None,
        audit_mode: bool = False,
        audit_expressions: bool = True,
    ) -> None:
        """
        Initialize the translator.

        Args:
            connection: Optional DuckDB connection for direct execution.
            use_fhirpath_udfs: Whether to use FHIRPath UDFs for property access.
            library_loader: Optional callable that takes a library alias/path and returns
                           the parsed Library AST, or None if not found.
            model_config: Optional ModelConfig for versioned schema resolution.
            _resolving_stack: Internal — set of (path, version) tuples for libraries
                currently being resolved, used for circular include detection.
            audit_mode: If True, emit audit structs wrapping boolean results.
            audit_expressions: If False with audit_mode=True, only add _audit_item
                to retrieve CTEs without wrapping expressions (population-only audit).
        """
        from .model_config import ModelConfig, DEFAULT_MODEL_CONFIG
        self._model_config = model_config or DEFAULT_MODEL_CONFIG

        errors = self._model_config.validate()
        if errors:
            import warnings
            for e in errors:
                warnings.warn(f"Schema config issue: {e}", stacklevel=2)

        self._connection = connection
        self._use_fhirpath_udfs = use_fhirpath_udfs
        self._library_loader = library_loader
        # Shared cache across all translator instances in the recursion.
        # Maps (library_path, version) -> cached translation results so that
        # diamond dependencies (e.g. FHIRHelpers included by many libraries)
        # are translated only once instead of once per include path.
        self._library_cache: dict = _library_cache if _library_cache is not None else {}
        self._resolving_stack: Set[tuple] = _resolving_stack if _resolving_stack is not None else set()
        self._included_definitions: Dict[str, SQLExpression] = {}

        # CTE name tracking for subquery deduplication (to avoid duplicate CTE names)
        self._subquery_cte_counter: int = 0
        self._used_cte_names: Set[str] = set()

        # Storage for included library CTEs (P1.2: External Library CTE Generation)
        # Maps CTE name -> (cte_ast, column_info) for retrieve CTEs from included libraries
        self._included_retrieve_ctes: Dict[str, Tuple["SQLSelect", Dict]] = {}

        # SQLRetrieveCTE tracking for optimized CTE generation
        self._retrieve_ctes: List[SQLRetrieveCTE] = []

        # Buffer for pre-compute CTEs that must appear immediately before the
        # definition CTE that requested them. Populated by _wrap_definition_cte
        # (audit mode PATIENT_SCALAR), drained after each _build_definition_cte call.
        self._pending_precte: List["CTEDefinition"] = []

        self._context = SQLTranslationContext()
        self._context.set_use_fhirpath_udfs(use_fhirpath_udfs)
        if audit_mode:
            self._context.set_audit_mode(True)
            if not audit_expressions:
                self._context.set_audit_expressions(False)
        if connection:
            self._context.set_connection(connection)
            
        # Initialize FHIR Schema Registry (Layer 1: base schema)
        from .fhir_schema import FHIRSchemaRegistry
        self._fhir_schema = FHIRSchemaRegistry(model_config=self._model_config)
        self._fhir_schema.load_default_resources()
        self._context.fhir_schema = self._fhir_schema

        # Initialize Profile Registry (Layer 2: profile/model knowledge)
        from .profile_registry import ProfileRegistry
        self._profile_registry = ProfileRegistry.from_model_config(self._model_config)
        self._context.profile_registry = self._profile_registry

        # Thread version-sensitive configs into context (Layer 3)
        self._context.column_mappings = self._fhir_schema.column_mappings
        self._context.choice_type_prefixes = self._fhir_schema.choice_type_prefixes
        self._context.extension_paths = self._profile_registry.extension_paths
        
        # Initialize dynamic library code registry (Tier 7: E1-E2)
        # Maps code names to their LOINC/code values for component code resolution
        self._component_code_to_column: Dict[str, str] = {}

    @property
    def context(self) -> SQLTranslationContext:
        """Get the current translation context."""
        return self._context

    @property
    def fhir_schema(self):
        """Get the FHIR schema registry."""
        return self._fhir_schema

    @fhir_schema.setter
    def fhir_schema(self, schema):
        """Set the FHIR schema registry and sync to translation context."""
        self._fhir_schema = schema
        self._context.fhir_schema = schema
        self._context.column_mappings = schema.column_mappings
        self._context.choice_type_prefixes = schema.choice_type_prefixes

    @property
    def profile_registry(self):
        """Get the profile registry."""
        return self._profile_registry

    @profile_registry.setter
    def profile_registry(self, registry):
        """Set the profile registry and sync to translation context."""
        self._profile_registry = registry
        self._context.profile_registry = registry
        self._context.extension_paths = registry.extension_paths

    def set_library_loader(
        self, loader: Optional[Callable[[str], Optional[Library]]]
    ) -> None:
        """
        Set the library loader function after construction.

        Args:
            loader: A callable that takes a library alias/path and returns
                   the parsed Library AST, or None if not found.
        """
        self._library_loader = loader

    def register_retrieve_cte(
        self,
        resource_type: str,
        valueset_url: Optional[str] = None,
        valueset_alias: Optional[str] = None,
        profile_url: Optional[str] = None,
        name: Optional[str] = None,
    ) -> str:
        """
        Register a retrieve CTE for optimized SQL generation.

        This tracks retrieve operations so they can be deduplicated before
        generating the final SQL. Returns the CTE name that should be used
        to reference this retrieve.

        Args:
            resource_type: FHIR resource type (e.g., "Condition", "Observation").
            valueset_url: Optional ValueSet URL for code filtering.
            valueset_alias: Short alias from CQL (e.g., "Essential Hypertension").
            profile_url: Optional US-Core/QICore profile URL.
            name: Optional CTE name (auto-generated if not provided).

        Returns:
            The CTE name to use for referencing this retrieve.
        """
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type=resource_type,
            valueset_url=valueset_url,
            valueset_alias=valueset_alias,
            profile_url=profile_url,
            name=name,
            fhir_schema=self._fhir_schema,
            profile_registry=self._profile_registry,
            column_mappings=self._context.column_mappings,
            choice_type_prefixes=self._context.choice_type_prefixes,
        )
        self._retrieve_ctes.append(cte)

        # Register columns in column registry
        col_info = cte.get_column_info()
        if col_info:
            self._context.column_registry.register_cte(cte.name, col_info)

        return cte.name

    def translate_library(self, library: Library) -> Dict[str, SQLExpression]:
        """
        Translate an entire CQL library to SQL.

        This method uses the three-phase retrieve optimization:
        1. Translate definitions with retrieve placeholders
        2. Build retrieve CTEs with precomputed columns
        3. Resolve placeholders in definition ASTs

        Args:
            library: The parsed CQL library AST.

        Returns:
            Dictionary mapping definition names to their SQL expressions.

        Raises:
            TranslationError: If translation fails for any definition.
        """
        # Reset context for new library
        self._context.clear()

        # Set up context from library declarations
        self._setup_context(library)

        # Process parameters before includes so that parameter bindings are
        # available even if include resolution fails.
        self._process_parameters(library, self._context)

        # Process includes
        self._process_includes(library, self._context)

        # Build dynamic component code registry (Tier 7: E2)
        # Extract component codes from library and included libraries
        self._build_component_code_registry(library)
        
        # Store in context for ExpressionTranslator access
        self._context.component_code_to_column = self._component_code_to_column

        # First pass: collect function definitions
        for statement in library.statements:
            if isinstance(statement, FunctionDefinition):
                self._register_function(statement)

        # Initialize shared FunctionInliner for expand-then-translate architecture
        self._init_shared_function_inliner()

        # Pre-register all definition names for forward reference resolution
        self._context._definition_names = {
            stmt.name for stmt in library.statements if isinstance(stmt, Definition)
        }

        # Perform global definition promotion scan to identify shared definitions
        self._scan_for_promoted_definitions(library)

        # Perform function-body CTE promotion pre-scan (Phase 1 + Phase 2)
        self._scan_for_promoted_functions(library)
        self._build_function_call_graph(library)
        self._propagate_transitive_counts()
        self._log_function_promotion_report()

        # Pre-register all definition ASTs for forward-reference shape inference.
        for stmt in library.statements:
            if isinstance(stmt, Definition) and not isinstance(stmt, FunctionDefinition):
                self._context.expression_definitions[stmt.name] = getattr(stmt, 'expression', stmt)

        # Use three-phase optimization to translate and resolve placeholders
        resolved_asts, phase1_result, phase2_result, opt_stats = run_optimization_phases(
            library, self._context, self
        )

        # Copy column registry from phase2_result to context for property access optimization
        # This enables property access in expressions.py to use precomputed columns
        for cte_name, columns in phase2_result.column_registry._columns.items():
            self._context.column_registry.register_cte(cte_name, columns)

        # Store resolved definitions in context for reference
        results: Dict[str, SQLExpression] = {}
        for name, ast in resolved_asts.items():
            # Sub-task 4e: Wrap scalar booleans in audit_leaf when audit_mode=True
            # Only wrap PATIENT_SCALAR definitions (booleans), not RESOURCE_ROWS (queries)
            if self._context.audit_mode and self._context.audit_expressions and not isinstance(ast, SQLAuditStruct):
                meta = self._context.definition_meta.get(name)
                is_scalar = meta is None or meta.is_scalar if meta else True
                if is_scalar:
                    ast = SQLFunctionCall(name="audit_leaf", args=[ast])
            results[name] = ast
            # Store for later reference (use add_definition so get_definition can find it)
            # Also store AST for structural analysis (fixes A11)
            self._context.add_definition(name, ast_expr=ast)

        return results

    def translate_library_to_sql(
        self, library: Library, final_definition: Optional[str] = None
    ) -> str:
        """
        Translate an entire CQL library to a single SQL statement with CTEs.

        This method generates a complete SQL query where all definitions are
        expressed as Common Table Expressions (CTEs) in a WITH clause,
        and definition references become subqueries selecting from those CTEs.

        Args:
            library: The parsed CQL library AST.
            final_definition: Optional name of the final definition to SELECT from.
                            If None, looks for "Initial Population" or uses the last definition.

        Returns:
            Complete SQL string with WITH clause and CTEs.

        Raises:
            TranslationError: If translation fails for any definition.

        Example:
            Input CQL:
                define "Essential Hypertension Diagnosis":
                    [Condition: "Essential Hypertension"]
                define "Initial Population":
                    exists "Essential Hypertension Diagnosis"

            Output SQL:
                WITH
                  "Essential Hypertension Diagnosis" AS (
                    SELECT resource FROM resources WHERE resourceType = 'Condition'
                      AND in_valueset(resource, 'code', 'http://...')
                  ),
                  "Initial Population" AS (
                    SELECT array_length((SELECT * FROM "Essential Hypertension Diagnosis")) > 0
                  )
                SELECT * FROM "Initial Population"
        """
        # First, translate the library to get all definitions
        definitions = self.translate_library(library)

        if not definitions:
            return "SELECT NULL"

        # Get definition names in dependency order (topological sort)
        ordered_names = self._topological_sort_definitions(library, definitions)

        # Build CTE definitions as AST nodes
        cte_defs = []
        seen_lower: dict[str, str] = {}  # lower(name) -> original name
        for name in ordered_names:
            expr = definitions[name]
            cte_name = self._unique_cte_name(name, seen_lower)
            # Wrap bare expressions in SELECT so they form valid CTE bodies
            if not isinstance(expr, (SQLSelect, SQLSubquery)):
                expr = SQLSelect(columns=[expr])
            elif isinstance(expr, SQLSubquery):
                expr = expr.query
            cte_defs.append(CTEDefinition(name=f'"{cte_name}"', query=expr))

        # Determine the final definition to select from
        if final_definition:
            final_name = final_definition
        elif _DEFAULT_FINAL_DEFINITION in definitions:
            final_name = _DEFAULT_FINAL_DEFINITION
        else:
            # Use the last definition in order
            final_name = ordered_names[-1] if ordered_names else None

        if not final_name or final_name not in definitions:
            # Fallback: select from the last definition
            final_name = ordered_names[-1] if ordered_names else None

        if not final_name:
            return "SELECT NULL"

        # Build the complete SQL with CTEs using AST nodes
        final_select_ast = SQLSelect(
            from_clause=SQLIdentifier(name=final_name, quoted=True),
        )
        fragment = SQLFragment(main_query=final_select_ast, ctes=cte_defs)
        return fragment.to_sql()

    def translate_library_to_population_sql(
        self,
        library: Library,
        output_columns: Optional[Dict[str, str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        patient_ids: Optional[List[str]] = None,
        resource_output: str = "reference",
    ) -> str:
        """
        Translate a CQL library to population-first SQL.

        Generates a single SQL query that returns one row per patient with
        the specified output columns. This is the main entry point for
        population-level measure evaluation.

        The generated SQL follows this pattern:
        1. A 'patients' CTE with all distinct patient IDs
        2. Retrieve CTEs from optimization phase 2
        3. CTEs for each definition that include patient_id
        4. A final SELECT with LEFT JOINs for boolean definitions

        This method uses the three-phase optimization pipeline:
        - Phase 1: Translate + scan for property usage
        - Phase 2: Build retrieve CTEs with precomputed columns
        - Phase 3: Resolve placeholders

        Args:
            library: The parsed CQL library AST.
            output_columns: Mapping of output column name to CQL definition name.
                           If None, includes all definitions.
                           If empty dict, returns patient_id only.
            parameters: Runtime parameter values (not yet implemented).
            patient_ids: Optional list of patient IDs to filter.

        Returns:
            Complete SQL query string for population evaluation.
        """
        # Reset and initialize context from library declarations
        self._context.clear()
        self._setup_context(library)
        self._process_parameters(library, self._context)

        # Apply runtime parameters BEFORE processing includes so included libraries
        # can access the parameter values (e.g. Measurement Period dates).
        if parameters:
            for param_name, param_value in parameters.items():
                if isinstance(param_value, dict) and "start" in param_value:
                    # Interval parameter supplied as {"start": ..., "end": ...}
                    start = param_value.get("start")
                    end = param_value.get("end")
                    self._context.set_parameter_binding(param_name, (start, end))
                    # set_parameter_binding handles all interval parameters uniformly
                elif isinstance(param_value, tuple) and len(param_value) == 2:
                    # Interval parameter supplied as (start, end)
                    start, end = param_value
                    self._context.set_parameter_binding(param_name, (str(start), str(end)))
                    # set_parameter_binding handles all interval parameters uniformly
                else:
                    self._context.set_parameter_binding(param_name, param_value)

        self._process_includes(library, self._context)

        # Validate that all declared parameters have bindings
        for param in library.parameters:
            binding = self._context._parameter_bindings.get(param.name)
            if binding is None or (isinstance(binding, tuple) and all(v is None for v in binding)):
                if not param.default:
                    raise TranslationError(
                        f"Required CQL parameter '{param.name}' has no supplied value and no default. "
                        f"Supply the parameter via evaluate_measure(parameters={{...}})."
                    )

        # Build dynamic component code registry (Tier 7: E2)
        self._build_component_code_registry(library)
        self._context.component_code_to_column = self._component_code_to_column

        # First pass: collect function definitions
        for statement in library.statements:
            if isinstance(statement, FunctionDefinition):
                self._register_function(statement)

        # Initialize shared FunctionInliner for expand-then-translate architecture
        self._init_shared_function_inliner()

        # Pre-register all definition names for forward reference resolution
        self._context._definition_names = {
            stmt.name for stmt in library.statements if isinstance(stmt, Definition)
        }

        # Pre-register all definition ASTs for forward-reference shape inference.
        for stmt in library.statements:
            if isinstance(stmt, Definition) and not isinstance(stmt, FunctionDefinition):
                self._context.expression_definitions[stmt.name] = getattr(stmt, 'expression', stmt)

        # Function promotion pre-scan
        self._scan_for_promoted_definitions(library)
        self._scan_for_promoted_functions(library)
        self._build_function_call_graph(library)
        self._propagate_transitive_counts()
        self._select_promoted_functions()
        if self._context.promoted_functions:
            _logger.info("Function CTE promotion enabled: %s", self._context.promoted_functions)
            assert all(isinstance(k, tuple) and len(k) == 2 for k in self._context.promoted_functions), \
                "promoted_functions keys must be (func_name, source_cte) tuples"
        self._log_function_promotion_report()

        # Build function promotion CTEs BEFORE optimization so
        # _promoted_cte_keys is populated for Phase 1 translation.
        # CTE bodies may contain retrieve placeholders that will be
        # resolved together with other placeholders during Phase 3.
        if self._context.promoted_functions:
            self._build_all_function_promotion_ctes(library)

        # ====================================================================
        # Three-Phase Optimization Pipeline
        # ====================================================================
        # Phase 1: Translate definitions with placeholders, scan for properties
        # Phase 2: Build retrieve CTEs with precomputed columns
        # Phase 3: Resolve placeholders in definition ASTs
        try:
            resolved_asts, phase1_result, phase2_result, opt_stats = run_optimization_phases(
                library, self._context, self
            )
        except RecursionError:
            resolving = list(self._context._resolving_definitions)
            if resolving:
                raise TranslationError(
                    f"Circular definition reference detected (stack overflow). "
                    f"Definitions being resolved: {' → '.join(resolving)}"
                )
            else:
                raise TranslationError(
                    "CQL expression exceeds maximum nesting depth (stack overflow). "
                    "Simplify deeply nested expressions or break them into named definitions."
                )

        # Copy column registry from phase2_result to context for property access optimization.
        # Only overwrite if the new entry has at least as many columns — included-library
        # column registries may already contain richer column sets from their property scans.
        for cte_name, columns in phase2_result.column_registry._columns.items():
            existing = self._context.column_registry._columns.get(cte_name, {})
            if len(columns) >= len(existing):
                self._context.column_registry.register_cte(cte_name, columns)

        # Always build patient demographics CTE if it wasn't built during Phase 2 optimization.
        # This ensures _patient_demographics is available for any definition that might
        # reference it via AgeInYearsAt() or other demographics-aware functions.
        if phase2_result.patient_demographics_cte is None:
            from ..translator.cte_builder import build_patient_demographics_cte
            cte_name, cte_ast, column_info = build_patient_demographics_cte()
            phase2_result.register_patient_demographics_cte(cte_ast, column_info)
            self._context.has_patient_demographics_cte = True

        # Check if any definitions were produced
        if not resolved_asts:
            # No definitions - return just patient IDs
            return self._build_patients_only_sql(patient_ids)

        # Get definition names in dependency order (use resolved ASTs)
        ordered_names = self._topological_sort_definitions(library, resolved_asts)

        # Determine which definitions to include in output
        if output_columns is None:
            # Include all definitions
            column_mapping = {name: name for name in ordered_names}
            output_definition_names = ordered_names
        elif len(output_columns) == 0:
            # Empty dict - return patient_id only
            column_mapping = {}
            output_definition_names = []
        else:
            # Use specified mapping
            column_mapping = output_columns
            output_definition_names = list(output_columns.values())

        # Build CTE definitions as AST nodes
        cte_defs: List[CTEDefinition] = []
        seen_cte_names: set = set()

        # 1. Build patients CTE
        patients_query = self._build_patients_cte(patient_ids)
        cte_defs.append(CTEDefinition(name='_patients', query=patients_query))
        seen_cte_names.add('_patients')

        # 2. Build patient demographics CTE if needed for age calculations
        if phase2_result.patient_demographics_cte is not None:
            cte_defs.append(CTEDefinition(
                name='_patient_demographics',
                query=phase2_result.patient_demographics_cte,
            ))
            seen_cte_names.add('_patient_demographics')

        # 3. Build retrieve CTEs from optimization phase 2
        # These must come BEFORE definition CTEs because definitions reference them
        for cte_name, cte_ast in phase2_result.ctes.items():
            quoted = f'"{cte_name}"'
            if quoted not in seen_cte_names:
                cte_defs.append(CTEDefinition(name=quoted, query=cte_ast))
                seen_cte_names.add(quoted)

        # 3.5. P1.2: Build retrieve CTEs from included libraries
        # These must come BEFORE included library definitions so those definitions
        # can reference their own retrieve CTEs.
        # When both the main and included library produce a CTE for the same
        # retrieve, prefer the version with more precomputed columns.
        for cte_name, (cte_ast, col_info) in self._included_retrieve_ctes.items():
            quoted = f'"{cte_name}"'
            if quoted not in seen_cte_names:
                cte_defs.append(CTEDefinition(name=quoted, query=cte_ast))
                seen_cte_names.add(quoted)
            elif col_info:
                # Included library has precomputed columns — check if main has fewer
                main_cols = phase2_result.column_registry._columns.get(cte_name, {})
                if len(col_info) > len(main_cols):
                    # Replace the main library's version with the richer one
                    for i, cdef in enumerate(cte_defs):
                        if cdef.name == quoted:
                            cte_defs[i] = CTEDefinition(name=quoted, query=cte_ast)
                            break

        # 3.7. Build mapping from provisional CTE names (valueset URLs) to actual
        # CTE names (display names) for let-variable CTE resolution.
        _prov_to_actual: dict[str, str] = {}
        for (_rt, _vs, _prof), _actual in phase2_result.cte_name_map.items():
            _prov = f"{_rt}: {_vs}" if _vs else _rt
            _prov_to_actual[_prov] = _actual

        # 4. Build CTEs for included library definitions (prefixed names)
        # These must come before main definitions so they can be referenced
        # Topologically sort included definitions so dependencies come first
        included_ordered = self._sort_included_definitions(self._included_definitions)
        # Reset the pre-compute name map so it accumulates fresh for this SQL generation.
        # Compound boolean definitions reference constituent boolean CTEs by name; the map
        # lets the pre-compute body substitute audit-CTE names with pre-compute equivalents,
        # keeping the filter chain on the fast WHERE-EXISTS semi-join path.
        self._precte_name_map: Dict[str, str] = {}  # type: ignore[assignment]
        for prefixed_name in included_ordered:
            sql_expr = self._included_definitions[prefixed_name]
            self._pending_precte.clear()
            cte_ast = self._build_included_definition_cte(prefixed_name, sql_expr)
            # Drain any pre-compute CTEs generated by the two-CTE audit approach
            for precte in self._pending_precte:
                cte_defs.append(precte)
            self._pending_precte.clear()
            cte_defs.append(CTEDefinition(name=f'"{prefixed_name}"', query=cte_ast))

        # 5. Build CTEs for each definition (in dependency order)
        # definition_ctes maps name -> (quoted_name, has_resource)
        definition_ctes: Dict[str, tuple] = {}

        # Include retrieve CTEs so identity passthrough works for bare retrieves
        for cte_name in phase2_result.ctes:
            quoted_name = f'"{cte_name}"'
            definition_ctes[cte_name] = (quoted_name, True)

        # Include included library definitions in existing_ctes so identity passthrough works
        for prefixed_name in included_ordered:
            quoted_name = f'"{prefixed_name}"'
            inc_meta = self._context.definition_meta.get(prefixed_name)
            inc_has_resource = inc_meta.has_resource if inc_meta else False
            definition_ctes[prefixed_name] = (quoted_name, inc_has_resource)

        # Track CTE names case-insensitively (DuckDB CTE names are case-insensitive)
        seen_lower: dict[str, str] = {}
        for cte in cte_defs:
            seen_lower[cte.name.lower()] = cte.name

        for name in ordered_names:
            expr = resolved_asts[name]
            self._pending_precte.clear()
            cte_ast, has_resource = self._build_definition_cte_with_patient_id(
                name, expr, definition_ctes
            )
            # Drain any pre-compute CTEs generated by the two-CTE audit approach
            for precte in self._pending_precte:
                precte_lower = precte.name.lower()
                if precte_lower not in seen_lower:
                    seen_lower[precte_lower] = precte.name
                    cte_defs.append(precte)
            self._pending_precte.clear()
            # Inject let-variable CTEs for this definition right before its CTE.
            # This ensures they come after any earlier definition CTEs they reference.
            if name in self._context._let_variable_ctes:
                for let_cte_name, let_cte_body in self._context._let_variable_ctes[name].items():
                    _fixed_body = self._resolve_let_cte_source(let_cte_body, _prov_to_actual)
                    quoted = f'"{let_cte_name}"'
                    if quoted.lower() not in seen_lower:
                        seen_lower[quoted.lower()] = quoted
                        cte_defs.append(CTEDefinition(name=quoted, query=_fixed_body))
            cte_name = self._unique_cte_name(name, seen_lower)
            quoted_name = f'"{cte_name}"'
            cte_defs.append(CTEDefinition(name=quoted_name, query=cte_ast))
            definition_ctes[name] = (quoted_name, has_resource)
            # Sync metadata so downstream references use correct column
            meta = self._context.definition_meta.get(name)
            if meta is not None:
                meta.has_resource = has_resource

            # Inject function promotion CTEs whose source is this definition.
            # These must come right after their source definition so that
            # downstream definition CTEs can reference the _fn_ CTEs.
            for (fn_name, fn_src), fn_ctes in self._context._function_promotion_ctes.items():
                if fn_src == name:
                    for fn_cte_name, fn_cte_body in fn_ctes.items():
                        _fixed_body = self._resolve_function_cte_source(fn_cte_body, definition_ctes)
                        quoted_fn = f'"{fn_cte_name}"'
                        if quoted_fn.lower() not in seen_lower:
                            seen_lower[quoted_fn.lower()] = quoted_fn
                            cte_defs.append(CTEDefinition(name=quoted_fn, query=_fixed_body))

        # 6. Build final SELECT with LEFT JOINs
        final_select_ast = self._build_population_final_select(
            column_mapping, output_definition_names, resource_output=resource_output
        )

        # Assemble the complete SQL using AST - call to_sql() only here at final assembly
        fragment = SQLFragment(main_query=final_select_ast, ctes=cte_defs)
        sql_text = fragment.to_sql()
        # Text-level fix for CASE WHEN audit_xxx(...) patterns that survived
        # AST-level demotion (subexpressions serialised to SQLRaw early).
        if self.context.audit_mode:
            from ..translator.expressions._query import demote_audit_in_text
            sql_text = demote_audit_in_text(sql_text)
        return sql_text

    def _build_patients_cte(self, patient_ids: Optional[List[str]] = None) -> SQLSelect:
        """
        Build the patients CTE query.

        Args:
            patient_ids: Optional list of patient IDs to filter.

        Returns:
            SQLSelect AST node for the patients CTE body.

        Note:
            Uses "_patients" (with underscore prefix) to avoid collision with
            user-defined CTEs like "Patients". DuckDB treats "patients" and
            "Patients" as the same identifier, so we use "_patients" as the
            internal name for the base patient reference table.
        """
        where_condition: SQLExpression = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="IS NOT",
                left=SQLQualifiedIdentifier(parts=["_outer", "patient_ref"]),
                right=SQLNull(),
            ),
            right=SQLExists(subquery=SQLSubquery(query=SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="resources"),
                    alias="_pt",
                ),
                where=SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_pt", "resourceType"]),
                        right=SQLLiteral(value="Patient"),
                    ),
                    right=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_pt", "id"]),
                        right=SQLQualifiedIdentifier(parts=["_outer", "patient_ref"]),
                    ),
                ),
            ))),
        )
        if patient_ids is not None and len(patient_ids) > 0:
            id_literals = [
                SQLLiteral(value=pid) for pid in patient_ids
            ]
            where_condition = SQLBinaryOp(
                operator="AND",
                left=where_condition,
                right=SQLBinaryOp(
                    operator="IN",
                    left=SQLQualifiedIdentifier(parts=["_outer", "patient_ref"]),
                    right=SQLList(items=id_literals),
                ),
            )
        return SQLSelect(
            distinct=True,
            columns=[SQLAlias(expr=SQLQualifiedIdentifier(parts=["_outer", "patient_ref"]), alias="patient_id")],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="resources"),
                alias="_outer",
            ),
            where=where_condition,
        )

    def _build_patients_only_sql(self, patient_ids: Optional[List[str]] = None) -> str:
        """
        Build SQL that returns only patient IDs.

        Args:
            patient_ids: Optional list of patient IDs to filter.

        Returns:
            SQL string.
        """
        patients_query = self._build_patients_cte(patient_ids)
        cte = CTEDefinition(name='_patients', query=patients_query)
        final = SQLSelect(
            columns=[SQLIdentifier(name="patient_id")],
            from_clause=SQLIdentifier(name="_patients"),
            order_by=[(SQLIdentifier(name="patient_id"), "ASC")],
        )
        fragment = SQLFragment(main_query=final, ctes=[cte])
        return fragment.to_sql()

    def _has_unresolved_refs(self, expr: "SQLExpression") -> bool:
        """Check if AST has obvious unresolved references (single-letter identifiers).
        
        Checks for patterns like fhirpath_text(A, ...) where A is a single-letter
        identifier that should have been resolved to a proper table alias.
        Excludes known valid SQL aliases: p (_patients), r (resources), etc.,
        as well as any single-letter alias defined within the expression itself
        (e.g., FROM "SomeCTE" AS E creates a valid alias E).
        """
        # Known valid single-letter SQL aliases used in generated CTEs
        _VALID_ALIASES = {'p', 'r', 's'}
        # Also collect aliases defined within this expression so that
        # inlined function bodies with short aliases (E, C, D, etc.) that
        # appear in subquery FROM clauses are not flagged as unresolved.
        _VALID_ALIASES = _VALID_ALIASES | self._collect_defined_aliases(expr)
        # Check if expression contains any single-letter identifier (A-Z)
        # These indicate failed query source translation
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if letter.lower() in _VALID_ALIASES:
                continue
            if ast_references_name(expr, letter):
                return True
        return False

    def _fallback_cte_sql(self, name: str, meta) -> SQLExpression:
        """Generate a safe fallback CTE for definitions that couldn't be properly translated.
        
        Matches the expected column shape: RESOURCE_ROWS definitions get a
        ``resource`` column so downstream CTEs that reference it don't fail.
        """
        from ..translator.context import RowShape

        columns = [SQLQualifiedIdentifier(parts=["_pt", "patient_id"])]
        if meta is not None and meta.shape == RowShape.RESOURCE_ROWS:
            columns.append(SQLAlias(
                expr=SQLCast(expression=SQLNull(), target_type="JSON"),
                alias="resource",
            ))
        else:
            columns.append(SQLAlias(expr=SQLNull(), alias="value"))
        return SQLSelect(
            columns=columns,
            from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="_pt"),
            where=SQLLiteral(value=False),
        )

    def _build_optimized_retrieve_cte(
        self,
        resource_type: str,
        valueset_url: Optional[str] = None,
        valueset_alias: Optional[str] = None,
        profile_url: Optional[str] = None,
        name: Optional[str] = None,
    ) -> SQLExpression:
        """
        Build an optimized CTE for a FHIR resource retrieve.

        Uses SQLRetrieveCTE to generate SQL with pre-computed columns for
        commonly accessed choice-type fields (e.g., effective_date, onset_date).

        Args:
            resource_type: FHIR resource type (e.g., "Condition", "Observation").
            valueset_url: Optional ValueSet URL for code filtering.
            valueset_alias: Short alias from CQL (e.g., "Essential Hypertension").
            profile_url: Optional US-Core/QICore profile URL.
            name: Optional CTE name (auto-generated if not provided).

        Returns:
            SQLExpression AST for the CTE body (without the CTE name and AS).

        Example output:
            SELECT
                r.patient_ref AS patient_id,
                r.resource,
                COALESCE(fhirpath_date(r.resource, 'onsetDateTime'),
                         fhirpath_date(r.resource, 'onsetPeriod.start')) AS onset_date
            FROM resources r
            WHERE r.resourceType = 'Condition'
              AND in_valueset(r.resource, 'code', 'http://...')
        """
        cte = SQLRetrieveCTE.create_with_precomputed_columns(
            resource_type=resource_type,
            valueset_url=valueset_url,
            valueset_alias=valueset_alias,
            profile_url=profile_url,
            name=name,
            fhir_schema=self._fhir_schema,
            profile_registry=self._profile_registry,
            column_mappings=self._context.column_mappings,
            choice_type_prefixes=self._context.choice_type_prefixes,
        )

        # Register columns in column registry
        col_info = cte.get_column_info()
        if col_info:
            self._context.column_registry.register_cte(cte.name, col_info)

        return cte

    def _build_population_final_select(
        self,
        column_mapping: Dict[str, str],
        output_definition_names: List[str],
        resource_output: str = "reference",
    ) -> SQLSelect:
        """
        Build the final SELECT statement for population evaluation.

        Uses LEFT JOINs for scalar defines and correlated subqueries for
        multi-value and resource defines, producing one row per patient
        with columns for each definition.

        Args:
            column_mapping: Mapping of output column name to definition name.
            output_definition_names: List of definition names to include.
            resource_output: "reference" for ResourceType/id strings, "json" for full JSON.

        Returns:
            SQLSelect AST node for the final SELECT.
        """
        from ..translator.context import RowShape

        # Build SELECT columns
        columns: List[SQLExpression] = [
            SQLQualifiedIdentifier(parts=["_pt", "patient_id"])
        ]

        # Track which defines need LEFT JOINs
        join_def_names = set()

        for output_col, def_name in column_mapping.items():
            meta = self._context.definition_meta.get(def_name)
            shape = meta.shape if meta else RowShape.UNKNOWN
            cql_type = (meta.cql_type or "Any") if meta else "Any"
            quoted = f'"{def_name}"'

            if shape == RowShape.PATIENT_SCALAR:
                # Scalar defines: use LEFT JOIN
                join_def_names.add(def_name)
                if cql_type == "Boolean":
                    if self._context.audit_mode and self._context.audit_expressions:
                        # Full audit mode: the CTE carries _audit_result (a struct with
                        # {result: bool, evidence: [...]}) built by cte_manager.py.
                        expr = SQLFunctionCall(
                            name="COALESCE",
                            args=[
                                SQLQualifiedIdentifier(parts=[quoted, "_audit_result"]),
                                SQLAuditStruct(
                                    result_expr=SQLLiteral(value=False),
                                    evidence_expr=SQLArray(),
                                ),
                            ],
                        )
                    elif self._context.audit_mode:
                        # Population-only audit: no expression wrapping, but still
                        # build a result+evidence struct from row presence + retrieve CTEs.
                        bool_result = SQLCase(
                            when_clauses=[(
                                SQLBinaryOp(
                                    operator="IS NOT",
                                    left=SQLQualifiedIdentifier(parts=[quoted, "patient_id"]),
                                    right=SQLNull(),
                                ),
                                SQLLiteral(value=True),
                            )],
                            else_clause=SQLLiteral(value=False),
                        )
                        # Collect evidence from resource CTEs referenced by this definition
                        evidence_parts = self._collect_population_evidence(def_name)
                        if evidence_parts:
                            evidence_sql = " || ".join(evidence_parts)
                            expr = SQLAuditStruct(
                                result_expr=bool_result,
                                evidence_expr=SQLRaw(evidence_sql),
                            )
                        else:
                            expr = SQLAuditStruct(
                                result_expr=bool_result,
                                evidence_expr=SQLArray(),
                            )
                    else:
                        # Normal mode: emit TRUE/FALSE based on row presence
                        expr = SQLCase(
                            when_clauses=[(
                                SQLBinaryOp(
                                    operator="IS NOT",
                                    left=SQLQualifiedIdentifier(parts=[quoted, "patient_id"]),
                                    right=SQLNull(),
                                ),
                                SQLLiteral(value=True),
                            )],
                            else_clause=SQLLiteral(value=False),
                        )
                else:
                    # Non-boolean scalar: return .value_column (NULL if no row)
                    col_name = meta.value_column if meta and meta.value_column else "value"
                    expr = SQLQualifiedIdentifier(parts=[quoted, col_name])

            elif shape == RowShape.PATIENT_MULTI_VALUE:
                # Multi-value: correlated subquery returning LIST
                value_col = meta.value_column if meta and meta.value_column else "value"
                inner_select = SQLSelect(
                    columns=[SQLFunctionCall(
                        name="COALESCE",
                        args=[
                            SQLFunctionCall(
                                name="LIST",
                                args=[SQLQualifiedIdentifier(parts=[quoted, value_col])],
                            ),
                            SQLArray(elements=[]),
                        ],
                    )],
                    from_clause=SQLIdentifier(name=def_name, quoted=True),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=[quoted, "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                )
                expr = SQLSubquery(query=inner_select)

            elif shape == RowShape.RESOURCE_ROWS:
                # Resource rows: correlated subquery returning LIST of refs or JSON
                # Filter out NULL resources to avoid [NULL] in LIST aggregation
                # (can occur when INTERSECT/EXCEPT produces empty sets but the
                # CTE still has a row per patient with NULL resource).
                correlated_where = SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=[quoted, "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                    right=SQLBinaryOp(
                        operator="IS NOT",
                        left=SQLQualifiedIdentifier(parts=[quoted, "resource"]),
                        right=SQLNull(),
                    ),
                )

                # Check if the CTE actually contains FHIR resources or scalar values.
                # Multi-source queries with scalar returns (e.g., Max({dates})) are
                # classified as RESOURCE_ROWS but their "resource" column holds a
                # primitive value (date string), not FHIR JSON.
                _RESOURCE_ROW_PRIMITIVE_TYPES = frozenset({
                    "Boolean", "Integer", "Decimal", "String", "DateTime", "Date",
                    "Time", "Quantity", "Code", "Concept", "Ratio",
                })

                def _unwrap_cql_type(t: str) -> str:
                    """Strip List<> or Interval<> wrapper to get inner type name."""
                    for prefix in ("List<", "Interval<"):
                        if t.startswith(prefix) and t.endswith(">"):
                            return t[len(prefix):-1]
                    return t

                _inner_type = _unwrap_cql_type(cql_type or "")
                _is_scalar_resource_rows = (
                    cql_type in _RESOURCE_ROW_PRIMITIVE_TYPES
                    or _inner_type in _RESOURCE_ROW_PRIMITIVE_TYPES
                    or cql_type == "Any"
                )

                if _is_scalar_resource_rows:
                    # Scalar values in resource column: output directly (no JSON extraction)
                    inner_select = SQLSelect(
                        columns=[SQLFunctionCall(
                            name="COALESCE",
                            args=[
                                SQLFunctionCall(
                                    name="LIST",
                                    args=[SQLQualifiedIdentifier(parts=[quoted, "resource"])],
                                ),
                                SQLArray(elements=[]),
                            ],
                        )],
                        from_clause=SQLIdentifier(name=def_name, quoted=True),
                        where=correlated_where,
                    )
                    expr = SQLSubquery(query=inner_select)
                elif resource_output == "json":
                    # Return list of full JSON strings
                    inner_select = SQLSelect(
                        columns=[SQLFunctionCall(
                            name="COALESCE",
                            args=[
                                SQLFunctionCall(
                                    name="LIST",
                                    args=[SQLQualifiedIdentifier(parts=[quoted, "resource"])],
                                ),
                                SQLArray(elements=[]),
                            ],
                        )],
                        from_clause=SQLIdentifier(name=def_name, quoted=True),
                        where=correlated_where,
                    )
                    expr = SQLSubquery(query=inner_select)
                else:
                    # Return list of "ResourceType/id" strings
                    ref_expr = SQLBinaryOp(
                        operator="||",
                        left=SQLBinaryOp(
                            operator="||",
                            left=SQLFunctionCall(
                                name="json_extract_string",
                                args=[
                                    SQLQualifiedIdentifier(parts=[quoted, "resource"]),
                                    SQLLiteral(value="$.resourceType"),
                                ],
                            ),
                            right=SQLLiteral(value="/"),
                        ),
                        right=SQLFunctionCall(
                            name="json_extract_string",
                            args=[
                                SQLQualifiedIdentifier(parts=[quoted, "resource"]),
                                SQLLiteral(value="$.id"),
                            ],
                        ),
                    )
                    inner_select = SQLSelect(
                        columns=[SQLFunctionCall(
                            name="COALESCE",
                            args=[
                                SQLFunctionCall(name="LIST", args=[ref_expr]),
                                SQLArray(elements=[]),
                            ],
                        )],
                        from_clause=SQLIdentifier(name=def_name, quoted=True),
                        where=correlated_where,
                    )
                    expr = SQLSubquery(query=inner_select)

            else:  # RowShape.UNKNOWN
                # Unknown-shape CTEs are always generated with a `value` column
                # (they go through the non-boolean scalar path in cte_manager).
                # Return the actual value rather than a boolean presence check so that
                # simple definitions like `Patient.birthDate`, `Patient.gender`, and
                # `AgeInYears()` surface their real values instead of TRUE/FALSE.
                join_def_names.add(def_name)
                col_name = meta.value_column if meta and meta.value_column else "value"
                expr = SQLQualifiedIdentifier(parts=[quoted, col_name])

            if self._context.audit_mode and cql_type == "Boolean":
                # Removed compact_audit wrapper: the engine will now return the flat
                # evidence array to Python, where the AuditEngine handles compaction,
                # to avoid DuckDB UNNEST correlation limits.
                pass

            columns.append(SQLAlias(expr=expr, alias=output_col))

        # Build LEFT JOINs only for defines that need them (scalars and unknowns)
        joins = []
        for def_name in output_definition_names:
            if def_name in join_def_names:
                joins.append(SQLJoin(
                    join_type="LEFT",
                    table=SQLIdentifier(name=def_name, quoted=True),
                    on_condition=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=[f'"{def_name}"', "patient_id"]),
                    ),
                ))

        return SQLSelect(
            columns=columns,
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="_patients"), alias="_pt", implicit_alias=True
            ),
            joins=joins,
            order_by=[(SQLQualifiedIdentifier(parts=["_pt", "patient_id"]), "ASC")],
        )

    def _collect_population_evidence(self, def_name: str) -> list:
        """Collect evidence SQL fragments for population-only audit.

        In population-only audit mode (audit_expressions=False), expression-level
        evidence is unavailable.  Instead, collect evidence from the retrieve CTEs
        that the definition transitively depends on.  Each evidence fragment is a
        SQL expression that produces a list of evidence structs.
        """
        from ..translator.context import RowShape

        meta = self._context.definition_meta.get(def_name)
        if meta is None:
            return []

        # Gather all resource CTEs this definition depends on
        src_ctes = set(getattr(meta, 'source_resource_ctes', []))
        if not src_ctes:
            # Walk output definition → included definitions transitively
            self._resolve_transitive_resource_ctes(def_name, src_ctes, set())

        retrieve_cte_names = getattr(self._context, '_audit_retrieve_cte_names', set())
        definition_cte_names = getattr(self._context, '_audit_definition_cte_names', set())
        all_audit_cte_names = retrieve_cte_names | definition_cte_names

        parts = []
        for cte_name in sorted(src_ctes):
            if cte_name in all_audit_cte_names:
                # CTE has _audit_item: correlated subquery to collect evidence
                quoted = f'"{cte_name}"'
                parts.append(
                    f"COALESCE((SELECT LIST({quoted}._audit_item) "
                    f"FROM {quoted} WHERE {quoted}.patient_id = _pt.patient_id "
                    f"AND {quoted}._audit_item IS NOT NULL), [])"
                )
            else:
                # RESOURCE_ROWS CTE without _audit_item: build evidence from resource
                sub_meta = self._context.definition_meta.get(cte_name)
                if sub_meta and getattr(sub_meta, 'has_resource', False):
                    quoted = f'"{cte_name}"'
                    parts.append(
                        f"COALESCE((SELECT LIST(struct_pack("
                        f"target := json_extract_string({quoted}.resource, '$.resourceType') || '/' || "
                        f"json_extract_string({quoted}.resource, '$.id'), "
                        f"attribute := CAST(NULL AS VARCHAR), value := CAST(NULL AS VARCHAR), "
                        f"operator := 'exists', threshold := '{cte_name}', "
                        f"trace := CAST([] AS VARCHAR[]))) "
                        f"FROM {quoted} WHERE {quoted}.patient_id = _pt.patient_id "
                        f"AND {quoted}.resource IS NOT NULL), [])"
                    )
        return parts

    def _resolve_transitive_resource_ctes(
        self, def_name: str, result: set, visited: set,
    ) -> None:
        """Walk definition dependencies to find all transitive resource CTEs."""
        if def_name in visited:
            return
        visited.add(def_name)
        meta = self._context.definition_meta.get(def_name)
        if meta is None:
            return
        src = getattr(meta, 'source_resource_ctes', [])
        if src:
            result.update(src)
            return
        # Check the AST for CTE references
        ast_expr = self._context.get_definition(def_name)
        if ast_expr is not None:
            from ..translator.ast_utils import collect_cte_references
            try:
                refs = collect_cte_references(ast_expr)
                for ref in refs:
                    sub_meta = self._context.definition_meta.get(ref)
                    if sub_meta:
                        self._resolve_transitive_resource_ctes(ref, result, visited)
            except (AttributeError, KeyError, TypeError) as e:
                _logger.warning(
                    "Failed to resolve transitive CTEs for '%s': %s (%s). "
                    "CTE dependencies may be incomplete.",
                    def_name, e, type(ast_expr).__name__,
                )

    def translate_definition(self, definition: Definition) -> SQLExpression:
        """
        Translate a single CQL definition to SQL.

        Args:
            definition: The definition to translate.

        Returns:
            SQLExpression containing the translated SQL.
        """
        from ..translator.context import DefinitionMeta

        # Set context if specified
        original_context = self._context.context_type
        if definition.context:
            self._context.set_context_type(definition.context)

        # Cycle detection: guard against circular definition references
        def_name = definition.name
        if def_name in self._context._resolving_definitions:
            cycle_path = " → ".join(self._context._resolving_definitions) + f" → {def_name}"
            raise TranslationError(
                f"Circular definition reference detected: {cycle_path}"
            )
        self._context._resolving_definitions.add(def_name)
        self._context._current_definition = def_name

        try:
            # Create a fresh query builder for this definition to track JOIN dependencies
            # This enables JOIN optimization during CTE building phase
            query_builder = SQLQueryBuilder(context=self._context)
            old_builder = self._context.query_builder
            self._context.query_builder = query_builder

            # Push a barrier scope to isolate this definition's aliases from other
            # definitions' translations (prevents alias leakage between definitions)
            self._context.push_scope()
            self._context.scopes[-1].barrier = True

            try:
                # Reset demographics flag before translating
                self._context._needs_demographics = False

                # Translate the expression with query_builder active
                result = self.translate_expression(definition.expression, self._context)

                # Wrap in audit_breadcrumb to preserve definition name in the trace
                if self._context.audit_mode:
                    from ..translator.types import SQLAuditStruct
                    if isinstance(result, SQLAuditStruct):
                        escaped_name = definition.name.replace("'", "''")
                        result = SQLFunctionCall(
                            name="audit_breadcrumb",
                            args=[result, SQLLiteral(escaped_name)]
                        )

                # Capture whether this definition used demographics
                needs_demographics = getattr(self._context, '_needs_demographics', False)

                # Save tracked CTE references from query_builder for later use
                tracked_refs = {}
                if query_builder.has_references():
                    tracked_refs = dict(query_builder.cte_references)
            finally:
                # Pop barrier scope and restore previous builder
                self._context.pop_scope()
                self._context.query_builder = old_builder

            # Populate DefinitionMeta for this definition
            shape = self._infer_row_shape(definition.expression)
            cql_type = self._infer_cql_type(definition.expression)
            # has_resource should reflect whether the CTE OUTPUT has a resource column,
            # not whether the expression REFERENCES a resource column.
            # Only RESOURCE_ROWS shape produces CTEs with resource columns.
            # PATIENT_SCALAR produces CTEs with only patient_id (and optionally value).
            from ..translator.context import RowShape
            if shape == RowShape.UNKNOWN:
                _logger.debug(
                    "Could not determine row shape for definition '%s' — "
                    "defaulting to non-resource",
                    definition.name,
                )
            has_resource = shape == RowShape.RESOURCE_ROWS

            # For PATIENT_SCALAR definitions that store a FHIR resource
            # (not a primitive type), use "resource" as the value column
            # so that property access (alias.resource) works correctly.
            # "Any" is treated as a resource type since the expression translator
            # always generates .resource references and unknown types are typically
            # FHIR resources (from First/Last/singleton of retrieve queries).
            _CQL_PRIMITIVE_TYPES = frozenset({
                "Boolean", "Integer", "Decimal", "String", "DateTime", "Date",
                "Time", "Quantity", "Code", "Concept", "Ratio", "Tuple",
                "Interval", "Period",
            })
            value_column = "value"
            if shape in (RowShape.PATIENT_SCALAR, RowShape.UNKNOWN) and cql_type not in _CQL_PRIMITIVE_TYPES:
                if not cql_type.startswith("List<") and not cql_type.startswith("Interval<"):
                    value_column = "resource"
                    has_resource = True

            meta = DefinitionMeta(
                name=definition.name,
                shape=shape,
                cql_type=cql_type,
                has_resource=has_resource,
                value_column=value_column,
                tracked_refs=tracked_refs,
                uses_demographics=needs_demographics,
            )
            # Propagate SQL result type hint (e.g., "Quantity") from translated expression
            if hasattr(result, 'result_type') and result.result_type:
                meta.sql_result_type = result.result_type
            # Detect Quantity fields in Tuple return clauses so downstream
            # property accesses on this definition can be identified as Quantity.
            meta.quantity_fields = self._detect_quantity_fields(definition.expression)
            self._context.definition_meta[definition.name] = meta

            # In audit mode, preserve the _audit_target from First/Last so that
            # downstream comparisons referencing this CTE can populate `target`.
            if self._context.audit_mode and hasattr(result, '_audit_target'):
                meta.audit_target_expr = result._audit_target

            # Build final SQL with any accumulated CTEs
            if self._context.get_ctes():
                cte_sql = self._build_sql({definition.name: result})
                return SQLExpression(
                    sql=cte_sql,
                    sql_type=result.sql_type,
                    nullable=result.nullable,
                    cte_refs=[cte.name for cte in self._context.get_ctes()],
                )

            return result
        finally:
            # Clean up cycle detection state
            self._context._resolving_definitions.discard(def_name)
            self._context._current_definition = None
            # Restore original context
            self._context.set_context_type(original_context)

    def translate_expression(
        self, expr: Expression, context: SQLTranslationContext
    ) -> SQLExpression:
        """
        Translate a CQL expression to SQL.

        This is the main dispatch method for expression translation.
        It delegates to specialized handlers based on expression type.

        Args:
            expr: The expression to translate.
            context: The translation context.

        Returns:
            SQLExpression containing the translated SQL.

        Raises:
            TranslationError: If the expression type is not supported.
        """
        # Import here to avoid circular imports
        from ..translator.expressions import ExpressionTranslator

        expr_translator = ExpressionTranslator(context)
        return expr_translator.translate(expr)

    def _scan_for_promoted_definitions(self, library: Library) -> None:
        """
        Scan the library to identify definitions eligible for global CTE promotion.
        
        This builds a reference graph to find definitions used in multiple contexts.
        """
        # 1. Initialize reference counts
        ref_counts = {name: 0 for name in self._context._definition_names}
        
        # 2. Walk the AST of every definition
        for stmt in library.statements:
            if isinstance(stmt, Definition) and not isinstance(stmt, FunctionDefinition):
                # Count references to other definitions
                self._collect_ref_counts(stmt.expression, ref_counts)
        
        # 3. Store in context
        self._context.definition_ref_counts = ref_counts
        
        # 4. Identify promoted definitions
        for name, count in ref_counts.items():
            if count >= 1:
                self._context.promoted_definitions.add(name)
        
        if self._context.promoted_definitions:
            _logger.info("Promoting %d definitions to global CTEs for deduplication",
                         len(self._context.promoted_definitions))

    def _collect_ref_counts(self, node: Any, ref_counts: Dict[str, int]) -> None:
        """Recursively walk the AST and count definition references."""
        from ..parser.ast_nodes import Identifier
        
        if node is None:
            return
            
        if isinstance(node, Identifier):
            # Only count if it's not a retrieve identifier (e.g. [Condition])
            if not getattr(node, 'retrieve', None) and node.name in ref_counts:
                ref_counts[node.name] += 1
            return
            
        # Recursive traversal through dataclass fields
        if hasattr(node, '__dataclass_fields__'):
            for field_name in node.__dataclass_fields__:
                val = getattr(node, field_name)
                if isinstance(val, list):
                    for item in val:
                        self._collect_ref_counts(item, ref_counts)
                else:
                    self._collect_ref_counts(val, ref_counts)

    # -----------------------------------------------------------------
    # Function-body CTE promotion pre-scan (Phase 1 + Phase 2)
    # -----------------------------------------------------------------

    def _walk_ast(self, node: Any, visitor: Callable[[Any], None]) -> None:
        """Recursively walk the AST and call visitor on every node.

        Unlike _collect_ref_counts which only counts Identifier references,
        this is a general-purpose walker that visits every node in the tree
        so the visitor can inspect any node type (MethodInvocation, FunctionRef, etc.).
        """
        if node is None:
            return

        visitor(node)

        if hasattr(node, '__dataclass_fields__'):
            for field_name in node.__dataclass_fields__:
                val = getattr(node, field_name)
                if isinstance(val, list):
                    for item in val:
                        self._walk_ast(item, visitor)
                else:
                    self._walk_ast(val, visitor)

    def _scan_for_promoted_functions(self, library: Library) -> None:
        """Scan for functions called N+ times with params from same source CTE.

        Detects fluent-style method calls (source_alias.methodName(...)) and
        positional function calls where an argument is the source alias.
        Stores results in context.function_ref_counts.
        """
        func_calls: Dict[Tuple[str, str], int] = {}

        for stmt in library.statements:
            if not isinstance(stmt, Definition):
                continue
            expr = stmt.expression
            if not isinstance(expr, Query):
                continue
            src = expr.source
            if not isinstance(src, QuerySource):
                continue
            if not isinstance(src.expression, Identifier):
                continue

            source_alias = src.alias
            source_def = src.expression.name

            # Skip if source is not a known definition
            if source_def not in self._context._definition_names:
                continue

            def _visitor(node: Any) -> None:
                if isinstance(node, MethodInvocation):
                    # Case 1: receiver is the source alias  (alias.method())
                    if isinstance(node.source, Identifier) and node.source.name == source_alias:
                        key = (node.method, source_def)
                        func_calls[key] = func_calls.get(key, 0) + 1
                    # Case 2: any argument is the source alias  (func(..., alias, ...))
                    for arg in node.arguments:
                        if isinstance(arg, Identifier) and arg.name == source_alias:
                            key = (node.method, source_def)
                            func_calls[key] = func_calls.get(key, 0) + 1
                if isinstance(node, FunctionRef):
                    # Non-fluent function call: FunctionName(alias, ...)
                    for arg in node.arguments:
                        if isinstance(arg, Identifier) and arg.name == source_alias:
                            key = (node.name, source_def)
                            func_calls[key] = func_calls.get(key, 0) + 1

            self._walk_ast(expr, _visitor)

        self._context.function_ref_counts = func_calls

    def _build_function_call_graph(self, library: Library) -> None:
        """Build an adjacency list of which functions each function/definition calls.

        Walks FunctionDefinition bodies and Definition bodies to find
        MethodInvocation and FunctionRef nodes, resolving them against the
        function registry.
        """
        call_graph: Dict[str, Set[str]] = {}

        # Collect all known function names for resolution
        known_funcs: Set[str] = set()
        for stmt in library.statements:
            if isinstance(stmt, FunctionDefinition):
                known_funcs.add(stmt.name)
        # Also include functions from included libraries
        for lib_info in self._context.includes.values():
            known_funcs.update(lib_info.functions.keys())

        def _extract_calls(node: Any, caller: str) -> None:
            """Walk a node and record function calls made by caller."""
            def _visitor(n: Any) -> None:
                callee = None
                if isinstance(n, MethodInvocation):
                    callee = n.method
                elif isinstance(n, FunctionRef):
                    callee = n.name
                if callee and callee in known_funcs:
                    if caller not in call_graph:
                        call_graph[caller] = set()
                    call_graph[caller].add(callee)
            self._walk_ast(node, _visitor)

        # Walk FunctionDefinition bodies
        for stmt in library.statements:
            if isinstance(stmt, FunctionDefinition) and stmt.expression is not None:
                _extract_calls(stmt.expression, stmt.name)

        # Walk Definition bodies
        for stmt in library.statements:
            if isinstance(stmt, Definition) and not isinstance(stmt, FunctionDefinition):
                if stmt.expression is not None:
                    _extract_calls(stmt.expression, stmt.name)

        self._context.function_call_graph = call_graph

    def _propagate_transitive_counts(self) -> None:
        """Propagate direct function call counts through the call graph.

        For each (func_name, source_cte) -> count in function_ref_counts,
        follow the call graph edges from func_name via BFS and add the count
        to every transitively reachable function.
        """
        transitive: Dict[Tuple[str, str], int] = dict(self._context.function_ref_counts)

        for (func_name, source_cte), count in self._context.function_ref_counts.items():
            visited: Set[str] = set()
            queue = [func_name]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                callees = self._context.function_call_graph.get(current, set())
                for callee in callees:
                    key = (callee, source_cte)
                    transitive[key] = transitive.get(key, 0) + count
                    queue.append(callee)

        self._context.function_transitive_counts = transitive

    def _log_function_promotion_report(self) -> None:
        """Log a diagnostic report of direct and transitive function call counts."""
        direct = self._context.function_ref_counts
        transitive = self._context.function_transitive_counts

        if not direct and not transitive:
            return

        # Gather all keys
        all_keys = set(direct.keys()) | set(transitive.keys())
        # Sort by transitive count descending
        sorted_keys = sorted(all_keys, key=lambda k: transitive.get(k, 0), reverse=True)

        _logger.info("Function promotion pre-scan report (%d unique calls):", len(sorted_keys))
        for (func_name, source_cte) in sorted_keys:
            d = direct.get((func_name, source_cte), 0)
            t = transitive.get((func_name, source_cte), 0)
            _logger.info("  %-55s  source=%-40s  direct=%d  transitive=%d",
                         func_name, source_cte, d, t)

    _FUNCTION_CTE_PROMOTION_THRESHOLD = 3

    def _select_promoted_functions(self) -> None:
        """Select functions meeting the transitive count threshold for CTE promotion."""
        for key, count in self._context.function_transitive_counts.items():
            if count >= self._FUNCTION_CTE_PROMOTION_THRESHOLD:
                self._context.promoted_functions[key] = count
        _logger.info("Selected %d functions for CTE promotion (threshold=%d)",
                     len(self._context.promoted_functions), self._FUNCTION_CTE_PROMOTION_THRESHOLD)

    # -----------------------------------------------------------------
    # Function-body CTE generation (Phase 3)
    # -----------------------------------------------------------------

    def _build_all_function_promotion_ctes(self, library: Library) -> None:
        """Build a CTE for each promoted (func_name, source_cte) pair."""
        for (func_name, source_cte_name) in list(self._context.promoted_functions.keys()):
            self._build_function_promotion_cte(func_name, source_cte_name)

    def _build_function_promotion_cte(self, func_name: str, source_cte_name: str) -> None:
        """Build a pre-computed CTE for one function + source pair.

        The CTE computes the function result for every row of the source CTE
        at once, so call sites can use lightweight correlated subquery lookups.
        """
        from ..translator.expressions import ExpressionTranslator

        inliner = self._context.function_inliner
        if not inliner:
            return

        # 1. Find the FunctionDef in the inliner's registry
        func_def = None
        for k, fd in inliner._functions.items():
            if k == func_name or k.endswith(f".{func_name}"):
                func_def = fd
                break
        if func_def is None or func_def.body is None:
            _logger.debug("Function %s not found in inliner registry, skipping", func_name)
            return

        # 2. Verify single-parameter (fluent) function
        if len(func_def.parameters) != 1:
            _logger.debug("Function %s has %d params, need 1 for promotion, skipping",
                          func_name, len(func_def.parameters))
            return

        # 3. Substitute parameter with synthetic alias
        param_name = func_def.parameters[0][0]
        synthetic_alias = "_fns"
        param_map = {param_name: Identifier(name=synthetic_alias)}
        substituted = inliner._substitute_parameters_cql(func_def.body, param_map)
        expanded = inliner._inline_nested_calls_cql(substituted, func_def.library_name)

        # 4. Set up isolated translation scope
        saved_scope_stack = list(self._context.scopes)
        saved_scope_level = self._context.current_scope_level
        saved_resource_alias = self._context.resource_alias
        saved_resource_type = self._context.resource_type
        saved_current_def = self._context._current_definition
        saved_alias_resource_types = dict(self._context._alias_resource_types)

        try:
            # Push barrier scope — isolate from caller context
            self._context.push_scope()
            self._context.scopes[-1].barrier = True

            # Register synthetic alias pointing to source CTE
            self._context.add_alias(
                synthetic_alias,
                table_alias=synthetic_alias,
                cte_name=source_cte_name,
            )
            self._context.resource_alias = synthetic_alias
            self._context._alias_resource_types[synthetic_alias] = ""
            self._context._current_definition = f"_fn_{func_name}"

            # 5. Translate expanded body to SQL
            expr_translator = ExpressionTranslator(self._context)
            result_sql = expr_translator.translate(expanded)

            # 5.5 Rewrite outer-scope references (_pt -> _fns)
            from ..translator.expressions import ExpressionTranslator as _ET
            _et_temp = _ET(self._context)
            fixed_result, _resolved = _et_temp._rewrite_outer_aliases(result_sql, synthetic_alias)
            if fixed_result is not None:
                result_sql = fixed_result

        finally:
            # 6. Restore all state
            self._context.scopes.clear()
            self._context.scopes.extend(saved_scope_stack)
            self._context.current_scope_level = saved_scope_level
            self._context.resource_alias = saved_resource_alias
            self._context.resource_type = saved_resource_type
            self._context._current_definition = saved_current_def
            self._context._alias_resource_types = saved_alias_resource_types

        # 7. Build CTE SELECT body
        # Use fhirpath_text(resource, 'id') as _row_key to avoid comparing large JSON blobs
        fn_cte_name = f"_fn_{func_name}_{source_cte_name.replace(' ', '_').replace(':', '')[:40]}"
        cte_body = SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=[synthetic_alias, "patient_id"]),
                SQLAlias(
                    expr=SQLFunctionCall(
                        name="fhirpath_text",
                        args=[
                            SQLQualifiedIdentifier(parts=[synthetic_alias, "resource"]),
                            SQLLiteral(value="id"),
                        ],
                    ),
                    alias="_row_key",
                ),
                SQLAlias(expr=result_sql, alias="value"),
            ],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=source_cte_name, quoted=True),
                alias=synthetic_alias,
            ),
        )

        # 7.4 Skip if body contains retrieve placeholders — after Phase 3
        # resolution these may reference definition CTEs that haven't been
        # emitted yet, creating impossible CTE ordering constraints.
        from ..translator.placeholder import contains_placeholder
        if contains_placeholder(result_sql):
            _logger.info("Skipping function promotion CTE %s: body contains retrieve placeholders",
                          fn_cte_name)
            return

        # 7.5 Validate: check the CTE body doesn't reference definition CTEs
        # other than the source. If it does, we can't promote because the
        # _fn_ CTE would need to be emitted after those definitions but before
        # the definitions that use it — creating an impossible ordering.
        _all_def_names = self._context._definition_names or set()
        _referenced_defs = self._find_definition_references(cte_body, _all_def_names)
        _other_defs = _referenced_defs - {source_cte_name}
        if _other_defs:
            _logger.info("Skipping function promotion CTE %s: body references other definitions: %s",
                          fn_cte_name, _other_defs)
            return

        # 8. Store in context
        key = (func_name, source_cte_name)
        if key not in self._context._function_promotion_ctes:
            self._context._function_promotion_ctes[key] = {}
        self._context._function_promotion_ctes[key][fn_cte_name] = cte_body
        self._context._promoted_cte_keys.add(key)
        _logger.info("Built function promotion CTE: %s for (%s, %s)",
                      fn_cte_name, func_name, source_cte_name)

    def _find_definition_references(self, ast_node, definition_names: set) -> set:
        """Find all definition CTE names referenced in a SQL AST subtree.

        Scans for SQLIdentifier nodes whose name matches a definition name,
        indicating a CTE reference in the generated SQL.
        """
        if ast_node is None or not hasattr(ast_node, '__dataclass_fields__'):
            return set()
        refs = set()
        stack = [ast_node]
        while stack:
            n = stack.pop()
            if n is None or not hasattr(n, '__dataclass_fields__'):
                continue
            for f in n.__dataclass_fields__:
                v = getattr(n, f, None)
                if v is None:
                    continue
                if isinstance(v, SQLIdentifier) and v.name in definition_names:
                    refs.add(v.name)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, SQLIdentifier) and item.name in definition_names:
                            refs.add(item.name)
                        elif item is not None and hasattr(item, '__dataclass_fields__'):
                            stack.append(item)
                elif hasattr(v, '__dataclass_fields__'):
                    stack.append(v)
        return refs

    def _setup_context(self, library: Library) -> None:
        """
        Initialize translation context from library declarations.

        Args:
            library: The parsed CQL library.
        """
        # Set up value sets
        for vs in library.valuesets:
            url = vs.id
            if vs.version:
                url = f"{url}|{vs.version}"
            self._context.define_valueset(vs.name, url)

        # Set up code systems
        for cs in library.codesystems:
            self._context.add_codesystem(cs.name, cs.id)

        # Set up codes and concepts
        # Note: CodeDefinition and ConceptDefinition are stored in separate lists
        # (library.codes and library.concepts), NOT in library.statements
        from ..parser.ast_nodes import CodeDefinition, ConceptDefinition
        from ..translator.terminology import TerminologyTranslator
        terminology = TerminologyTranslator(self._context)

        # Register codes from library.codes list
        for code_def in library.codes:
            terminology.register_code(code_def)

        # Register concepts from library.concepts list
        for concept_def in library.concepts:
            terminology.register_concept(concept_def)

        # Set context from library
        if library.context:
            self._context.set_context_type(library.context.name)

    def _build_component_code_registry(self, library: Library) -> None:
        """Build dynamic component code to column mapping from library codes.
        
        Scans the library for code definitions with LOINC codes (particularly
        systolic/diastolic blood pressure codes) and maps them to precomputed
        SQL column names.
        
        This replaces the hardcoded COMPONENT_CODE_TO_COLUMN dict (Tier 7: E2).
        
        Args:
            library: The parsed CQL library with code definitions.
        """
        # Load standard LOINC code mappings from config
        from ..translator.component_codes import get_code_to_column_mapping
        standard_code_mappings = get_code_to_column_mapping()
        
        # Extract code definitions from library
        for code_def in library.codes:
            # Look for LOINC codes that map to precomputed columns
            if code_def.code in standard_code_mappings:
                # Use both the code value and the code name as keys
                self._component_code_to_column[code_def.code] = standard_code_mappings[code_def.code]
                self._component_code_to_column[code_def.name] = standard_code_mappings[code_def.code]
        
        # Also check included libraries for component codes
        for inc_alias, lib_info in self._context.includes.items():
            if hasattr(lib_info, 'library_ast') and lib_info.library_ast:
                for code_def in lib_info.library_ast.codes:
                    if code_def.code in standard_code_mappings:
                        self._component_code_to_column[code_def.code] = standard_code_mappings[code_def.code]
                        self._component_code_to_column[code_def.name] = standard_code_mappings[code_def.code]

    def _process_parameters(
        self, library: Library, context: SQLTranslationContext
    ) -> None:
        """
        Register parameters from library.

        Args:
            library: The parsed CQL library.
            context: The translation context.
        """
        for param in library.parameters:
            param_type = str(param.type) if param.type else "Any"
            default = None
            if param.default:
                # Try to extract default value
                try:
                    default = self._extract_default_value(param.default)
                except (AttributeError, TypeError, ValueError) as e:
                    _logger.warning("Failed to extract default value for parameter '%s': %s", param.name, e)
            context.add_parameter(param.name, param_type, default)

            # For interval-typed parameters with no explicit binding, register (None, None)
            # so the expression translator generates {mp_start}/{mp_end} template placeholders
            # (for "Measurement Period") or equivalent for other interval parameters.
            if "Interval" in param_type and param.name not in context._parameter_bindings:
                context.set_parameter_binding(param.name, (None, None))

            # Populate parameter bindings from default interval values
            if isinstance(default, dict) and ("low" in default or "high" in default):
                p_start = default.get("low")
                p_end = default.get("high")
                if p_start:
                    # Strip time/timezone suffix for DATE literal (e.g. "2026-01-01T00:00:00.000Z" -> "2026-01-01")
                    p_start = str(p_start)[:10]
                if p_end:
                    p_end = str(p_end)[:10]
                context.set_parameter_binding(param.name, (p_start, p_end))
                # No special-case for "Measurement Period" — set_parameter_binding is sufficient

    def _extract_default_value(self, expr: Expression) -> Any:
        """
        Extract a default value from an expression.

        Args:
            expr: The default value expression.

        Returns:
            The extracted value.
        """
        from ..parser.ast_nodes import Literal, DateTimeLiteral, Interval

        if isinstance(expr, Literal):
            return expr.value
        elif isinstance(expr, DateTimeLiteral):
            return expr.value
        elif isinstance(expr, Interval):
            # Return interval as dict for later serialization
            low = self._extract_default_value(expr.low) if expr.low else None
            high = self._extract_default_value(expr.high) if expr.high else None
            return {
                "low": low,
                "high": high,
                "lowClosed": expr.low_closed,
                "highClosed": expr.high_closed,
            }
        return None

    def _init_shared_function_inliner(self) -> None:
        """
        Initialize a shared FunctionInliner on the context.

        This loads fluent function libraries once and stores the inliner
        on the context so all expression translations share the same
        inliner with proper cycle detection.
        """
        from ..translator.function_inliner import FunctionInliner
        from ..translator.fluent_function_loader import FluentFunctionLoader

        inliner = FunctionInliner(self._context)
        loader = FluentFunctionLoader()
        loader.load_default_libraries(inliner, self._context)

        # Register functions from the CURRENT library (main library being translated)
        for func_name, func_info in self._context.get_all_functions().items():
            if func_info.expression is not None:
                from ..translator.function_inliner import FunctionDef
                params = []
                for p in func_info.parameters:
                    p_name = getattr(p, 'name', str(p)) if not isinstance(p, tuple) else p[0]
                    p_type = getattr(p, 'type', None) if not isinstance(p, tuple) else (p[1] if len(p) > 1 else None)
                    if p_type is not None:
                        p_type = getattr(p_type, 'name', str(p_type))
                    params.append((p_name, p_type))
                fd = FunctionDef(
                    name=func_name,
                    library_name=None,
                    parameters=params,
                    return_type=func_info.return_type,
                    body=func_info.expression,
                    fluent=func_info.is_fluent,
                )
                inliner.register_function(fd)

        # Register functions from ALL included libraries (including transitive)
        self._register_included_functions_in_inliner(inliner)
        self._context.function_inliner = inliner

    def _register_function(self, func_def: FunctionDefinition) -> None:
        """
        Register a function definition for later inlining.

        Args:
            func_def: The function definition.
        """
        func_info = FunctionInfo(
            name=func_def.name,
            parameters=func_def.parameters,
            return_type=str(func_def.return_type) if func_def.return_type else None,
            expression=func_def.expression,
            is_fluent=func_def.fluent,
        )
        self._context.define_function(func_info)

    def _build_sql(self, definitions: Dict[str, SQLExpression]) -> str:
        """
        Assemble final SQL with CTEs.

        Args:
            definitions: Dictionary of definition names to SQL expressions.

        Returns:
            Complete SQL string with CTEs.
        """
        ctes = self._context.get_ctes()
        if not ctes:
            # No CTEs, just return the expression
            if len(definitions) == 1:
                return list(definitions.values())[0].to_sql()
            return "\n\n".join(
                f"-- {name}\n{expr.to_sql()}" for name, expr in definitions.items()
            )

        # Build WITH clause
        cte_parts = [cte.to_sql() for cte in ctes]
        with_clause = f"WITH {', '.join(cte_parts)}"

        # Build final SELECT
        if len(definitions) == 1:
            name, expr = list(definitions.items())[0]
            # Quote alias to handle reserved words like NULL, TRUE, FALSE
            quoted_name = f'"{name}"' if name.upper() in (
                "NULL", "TRUE", "FALSE", "SELECT", "FROM", "WHERE",
                "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN",
                "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
                "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
                "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC",
                "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
                "DISTINCT", "ALL", "AS", "WITH", "RECURSIVE"
            ) else name
            return f"{with_clause}\nSELECT {expr.to_sql()} AS {quoted_name}"
        else:
            selects = []
            for name, expr in definitions.items():
                # Quote alias to handle reserved words like NULL, TRUE, FALSE
                quoted_name = f'"{name}"' if name.upper() in (
                    "NULL", "TRUE", "FALSE", "SELECT", "FROM", "WHERE",
                    "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN",
                    "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
                    "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
                    "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC",
                    "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
                    "DISTINCT", "ALL", "AS", "WITH", "RECURSIVE"
                ) else name
                selects.append(f"{expr.to_sql()} AS {quoted_name}")
            return f"{with_clause}\nSELECT {', '.join(selects)}"

    # -------------------------------------------------------------------------
    # CTE Extraction for Common Retrieves
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Type Inference Methods (Task 2.2)
    # -------------------------------------------------------------------------

__all__ = [
    "CQLToSQLTranslator",
    "SQLTranslationContext",
    "SymbolInfo",
    "FunctionInfo",
    "LibraryInfo",
    "PatientContext",
    "MeasurementPeriod",
    "ParameterBinding",
]

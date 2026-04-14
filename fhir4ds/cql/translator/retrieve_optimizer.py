"""
Main orchestrator for retrieve optimization.

This module coordinates the three phases:
1. Translate + Scan
2. Build CTEs
3. Resolve + Optimize
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from .types import (
    SQLExpression, SQLSelect, SQLFunctionCall, SQLLiteral,
    SQLQualifiedIdentifier, SQLIdentifier, SQLAlias, SQLJoin,
    SQLBinaryOp, SQLUnaryOp, SQLCase, SQLList, SQLArray,
    SQLUnion, SQLSubquery
)
from .column_registry import ColumnRegistry, ColumnInfo
from .placeholder import RetrievePlaceholder, resolve_placeholders, find_all_placeholders
from .property_scanner import scan_ast_for_properties, PropertyAccess
from .cte_builder import build_retrieve_cte

if TYPE_CHECKING:
    from ..parser.ast_nodes import Library, Definition
    from .context import SQLTranslationContext
    from .translator import CQLToSQLTranslator


@dataclass
class Phase1Result:
    """
    Result of Phase 1: Translation and scanning.

    Contains all information needed to build optimized CTEs:
    - Which properties are accessed on each retrieve
    - The translated AST (with placeholders)
    - All placeholder instances found

    Attributes:
        property_usage: Map of retrieve key → set of property paths accessed
                       Key is (resource_type, valueset, profile_url)
                       Value is set of FHIRPath property strings like "onsetDateTime"
        definition_asts: Map of definition name → translated SQL AST
                        AST contains placeholders that need resolution
        placeholders: List of all placeholder instances found during translation
                     Used to verify all are resolved later
        needs_patient_demographics: True if AgeInYearsAt/AgeInMonthsAt/AgeInDaysAt
                                   is used and requires patient birthDate lookup
    """
    property_usage: Dict[Tuple[str, Optional[str], Optional[str]], Set[str]] = field(default_factory=dict)
    definition_asts: Dict[str, SQLExpression] = field(default_factory=dict)
    placeholders: List[RetrievePlaceholder] = field(default_factory=list)
    needs_patient_demographics: bool = False

    def add_property_usage(self, resource_type: str, valueset: Optional[str],
                          property_path: str, profile_url: Optional[str] = None):
        """Helper to add a property usage entry."""
        key = (resource_type, valueset, profile_url)
        if key not in self.property_usage:
            self.property_usage[key] = set()
        self.property_usage[key].add(property_path)

    def get_properties_for_retrieve(self, resource_type: str, valueset: Optional[str],
                                    profile_url: Optional[str] = None) -> Set[str]:
        """Get all properties accessed on a specific retrieve."""
        key = (resource_type, valueset, profile_url)
        return self.property_usage.get(key, set())


@dataclass
class Phase2Result:
    """
    Result of Phase 2: CTE building.

    Contains the constructed CTEs and column registry for optimization.

    Attributes:
        ctes: Map of CTE name → CTE SQL AST
              Key is friendly name like "Condition: Essential Hypertension"
              Value is SQLSelect AST for the CTE
        column_registry: Registry mapping (CTE name, property path) → column name
                        Used to look up precomputed columns during optimization
        cte_name_map: Map of retrieve key → CTE name
                     Key is (resource_type, valueset, profile_url)
                     Used to resolve placeholders
        patient_demographics_cte: Optional patient demographics CTE AST
                                 Set when AgeInYearsAt/AgeInMonthsAt/AgeInDaysAt is used
        patient_demographics_column_info: Column info for patient demographics CTE
    """
    ctes: Dict[str, SQLSelect] = field(default_factory=dict)
    column_registry: ColumnRegistry = field(default_factory=ColumnRegistry)
    cte_name_map: Dict[Tuple[str, Optional[str], Optional[str]], str] = field(default_factory=dict)
    patient_demographics_cte: Optional[SQLSelect] = None
    patient_demographics_column_info: Dict[str, ColumnInfo] = field(default_factory=dict)

    def register_cte(self, resource_type: str, valueset: Optional[str],
                     cte_name: str, cte_ast: SQLSelect,
                     column_info: Dict[str, ColumnInfo],
                     profile_url: Optional[str] = None):
        """Register a CTE and its mapping."""
        key = (resource_type, valueset, profile_url)
        self.ctes[cte_name] = cte_ast
        self.cte_name_map[key] = cte_name
        self.column_registry.register_cte(cte_name, column_info)

    def register_patient_demographics_cte(
        self, cte_ast: SQLSelect, column_info: Dict[str, ColumnInfo]
    ):
        """Register the patient demographics CTE for age calculations."""
        self.patient_demographics_cte = cte_ast
        self.patient_demographics_column_info = column_info
        # Also register in column registry for lookup
        self.column_registry.register_cte("_patient_demographics", column_info)

    def get_cte_name(self, resource_type: str, valueset: Optional[str],
                     profile_url: Optional[str] = None) -> Optional[str]:
        """Look up CTE name for a retrieve."""
        key = (resource_type, valueset, profile_url)
        return self.cte_name_map.get(key)


@dataclass
class OptimizationStats:
    """
    Statistics about optimization results.

    Used for debugging and validation.
    """
    num_retrieves: int = 0
    num_ctes_created: int = 0
    num_properties_precomputed: int = 0
    num_placeholders_resolved: int = 0
    num_fhirpath_calls_optimized: int = 0

    def __repr__(self) -> str:
        return (
            f"OptimizationStats(\n"
            f"  Retrieves found: {self.num_retrieves}\n"
            f"  CTEs created: {self.num_ctes_created}\n"
            f"  Properties precomputed: {self.num_properties_precomputed}\n"
            f"  Placeholders resolved: {self.num_placeholders_resolved}\n"
            f"  FHIRPath calls optimized: {self.num_fhirpath_calls_optimized}\n"
            f")"
        )


def scan_definition_for_properties(
    ast: SQLExpression,
    placeholders: List[RetrievePlaceholder]
) -> Dict[Tuple[str, Optional[str], Optional[str]], Set[str]]:
    """
    Scan a definition's AST and map properties to retrieves.

    For each retrieve placeholder in the AST, we need to know what properties
    are accessed on it. This function returns that mapping.

    Args:
        ast: The definition's SQL AST (contains placeholders)
        placeholders: List of all placeholders found in this AST

    Returns:
        Dict mapping retrieve key → set of property paths
        Key is (resource_type, valueset, profile_url)

    Example:
        ast contains:
        - RetrievePlaceholder("Condition", "Diabetes", None)
        - fhirpath_date(resource, "onsetDateTime")
        - fhirpath_text(resource, "status")

        Returns:
        {
            ("Condition", "Diabetes", None): {"onsetDateTime", "status"}
        }
    """
    # Find all properties accessed in this definition
    all_properties = scan_ast_for_properties(ast)

    # Map properties to retrieves
    # For now, attribute all properties to all placeholders in this definition
    # (More sophisticated: track which properties are accessed on which placeholder)
    result: Dict[Tuple[str, Optional[str], Optional[str]], Set[str]] = {}
    property_paths = {p.property_path for p in all_properties}

    for placeholder in placeholders:
        result[placeholder.key] = property_paths.copy()

    return result


def optimize_property_access(
    ast: SQLExpression,
    registry: ColumnRegistry,
    alias_to_cte: Optional[Dict[str, str]] = None
) -> SQLExpression:
    """
    Replace fhirpath_*(resource, 'path') with precomputed column references.

    This optimization replaces expensive FHIRPath UDF calls with direct column
    references when the column has been precomputed in the retrieve CTE.

    Args:
        ast: The SQL AST to optimize
        registry: Column registry containing precomputed column mappings
        alias_to_cte: Optional mapping from SQL alias to CTE name
                     (e.g., {"t1": "Condition: Essential Hypertension"})
                     If not provided, will be extracted from the AST.

    Returns:
        Optimized AST with fhirpath calls replaced by column references where possible

    Example:
        Before:
            fhirpath_date(t1.resource, 'onsetDateTime')

        After (if onset_date is precomputed in the CTE):
            t1.onset_date
    """
    # Extract alias-to-CTE mapping from the AST if not provided
    if alias_to_cte is None:
        alias_to_cte = _extract_alias_to_cte_mapping(ast)

    # Walk the AST and optimize fhirpath calls
    return _optimize_fhirpath_calls(ast, registry, alias_to_cte)


def _extract_alias_to_cte_mapping(ast: SQLExpression) -> Dict[str, str]:
    """
    Extract mapping from SQL table aliases to CTE names from the AST.

    Looks for FROM clauses and JOINs to build the mapping.

    Args:
        ast: SQL AST to analyze

    Returns:
        Dict mapping alias -> CTE name (e.g., {"t1": "Condition: Essential Hypertension"})
    """
    alias_map: Dict[str, str] = {}

    def extract_from_node(node):
        """Extract alias mappings from a single node."""
        if node is None:
            return

        # Handle SELECT statements - check FROM clause and JOINs
        if isinstance(node, SQLSelect):
            # Extract from FROM clause
            if node.from_clause:
                _extract_alias_from_table_ref(node.from_clause, alias_map)

            # Extract from JOINs
            if node.joins:
                for join in node.joins:
                    if isinstance(join, SQLJoin):
                        _extract_alias_from_table_ref(join.table, alias_map, join.alias)

        # Recurse into children
        _walk_for_from_clauses(node, extract_from_node)

    extract_from_node(ast)
    return alias_map


def _extract_alias_from_table_ref(
    table_ref: SQLExpression,
    alias_map: Dict[str, str],
    explicit_alias: Optional[str] = None
) -> None:
    """
    Extract alias-to-CTE mapping from a table reference.

    Args:
        table_ref: The table reference (SQLIdentifier, SQLAlias, SQLQualifiedIdentifier)
        alias_map: Dict to update with mappings
        explicit_alias: Optional explicit alias from JOIN
    """
    if isinstance(table_ref, SQLAlias):
        # Pattern: SQLAlias(expr=SQLIdentifier("CTE Name"), alias="t1")
        cte_name = None
        if isinstance(table_ref.expr, SQLIdentifier):
            cte_name = table_ref.expr.name
        elif isinstance(table_ref.expr, SQLQualifiedIdentifier) and len(table_ref.expr.parts) == 1:
            cte_name = table_ref.expr.parts[0]

        if cte_name:
            alias_map[table_ref.alias] = cte_name

    elif isinstance(table_ref, SQLIdentifier):
        # Pattern: SQLIdentifier("CTE Name") without alias
        # Use the CTE name itself as the alias
        if explicit_alias:
            alias_map[explicit_alias] = table_ref.name
        else:
            # The identifier is both the CTE name and the implicit alias
            alias_map[table_ref.name] = table_ref.name

    elif isinstance(table_ref, SQLQualifiedIdentifier):
        # Pattern: schema.CTEName or just CTEName
        if len(table_ref.parts) >= 1:
            cte_name = table_ref.parts[-1]  # Last part is the table/CTE name
            if explicit_alias:
                alias_map[explicit_alias] = cte_name
            else:
                alias_map[cte_name] = cte_name


def _walk_for_from_clauses(node, visitor):
    """
    Walk AST looking for SELECT statements to extract FROM clause info.

    This is a shallow walk - we only need to find SQLSelect nodes.
    """
    if node is None:
        return

    if isinstance(node, SQLFunctionCall):
        for arg in node.args:
            visitor(arg)

    elif isinstance(node, SQLSelect):
        # Already handled by visitor, but recurse into columns/where
        for col in node.columns:
            if isinstance(col, tuple):
                visitor(col[0])
            else:
                visitor(col)
        if node.where:
            visitor(node.where)
        if node.group_by:
            for g in node.group_by:
                visitor(g)
        if node.having:
            visitor(node.having)

    elif isinstance(node, SQLBinaryOp):
        visitor(node.left)
        visitor(node.right)

    elif isinstance(node, SQLUnaryOp):
        visitor(node.operand)

    elif isinstance(node, SQLCase):
        for cond, result in node.when_clauses:
            visitor(cond)
            visitor(result)
        if node.else_clause:
            visitor(node.else_clause)

    elif isinstance(node, (SQLList, SQLArray)):
        for item in getattr(node, 'items', getattr(node, 'elements', [])):
            visitor(item)

    elif isinstance(node, SQLAlias):
        visitor(node.expr)

    elif isinstance(node, SQLJoin):
        visitor(node.table)
        if node.on_condition:
            visitor(node.on_condition)

    elif isinstance(node, SQLUnion):
        # Recurse into each operand of the UNION
        for operand in node.operands:
            visitor(operand)

    elif isinstance(node, SQLSubquery):
        # Recurse into the subquery
        visitor(node.query)


def _optimize_fhirpath_calls(
    ast: SQLExpression,
    registry: ColumnRegistry,
    alias_to_cte: Dict[str, str]
) -> SQLExpression:
    """
    Recursively walk AST and replace fhirpath calls with column references.

    Args:
        ast: Current AST node
        registry: Column registry for lookups
        alias_to_cte: Mapping from SQL alias to CTE name

    Returns:
        Optimized AST node
    """
    if ast is None:
        return ast

    # Check if this is a fhirpath function call we can optimize
    if isinstance(ast, SQLFunctionCall):
        if ast.name in ('fhirpath_text', 'fhirpath_date', 'fhirpath_number',
                        'fhirpath_bool', 'fhirpath_quantity', 'fhirpath_timestamp'):
            # Try to optimize this call
            optimized = _try_optimize_fhirpath_call(ast, registry, alias_to_cte)
            if optimized is not None:
                return optimized

            # If we couldn't optimize, still recurse into args
            return SQLFunctionCall(
                name=ast.name,
                args=[_optimize_fhirpath_calls(arg, registry, alias_to_cte) for arg in ast.args],
                distinct=ast.distinct
            )

        # For other function calls, recurse into args
        return SQLFunctionCall(
            name=ast.name,
            args=[_optimize_fhirpath_calls(arg, registry, alias_to_cte) for arg in ast.args],
            distinct=ast.distinct
        )

    # Recurse into other node types
    return _recurse_ast(ast, registry, alias_to_cte)


def _try_optimize_fhirpath_call(
    call: SQLFunctionCall,
    registry: ColumnRegistry,
    alias_to_cte: Dict[str, str]
) -> Optional[SQLExpression]:
    """
    Try to optimize a single fhirpath call to a column reference.

    Args:
        call: The fhirpath function call
        registry: Column registry
        alias_to_cte: Mapping from SQL alias to CTE name

    Returns:
        SQLQualifiedIdentifier if optimized, None if cannot optimize
    """
    if len(call.args) < 2:
        return None

    # First arg should be a resource reference like t1.resource
    resource_arg = call.args[0]
    path_arg = call.args[1]

    # Extract the alias from the resource reference
    alias = None
    if isinstance(resource_arg, SQLQualifiedIdentifier) and len(resource_arg.parts) >= 2:
        # Pattern: t1.resource -> alias = "t1"
        alias = resource_arg.parts[0]
    elif isinstance(resource_arg, SQLIdentifier):
        # Single identifier - could be the alias itself
        alias = resource_arg.name

    if not alias:
        return None

    # Look up the CTE name for this alias
    cte_name = alias_to_cte.get(alias)
    if not cte_name:
        # Fall back: maybe the alias IS the CTE name
        cte_name = alias

    # Extract the FHIRPath string
    path = None
    if isinstance(path_arg, SQLLiteral) and isinstance(path_arg.value, str):
        path = path_arg.value

    if not path:
        return None

    # Look up the column in the registry
    column_name = registry.lookup(cte_name, path)
    if column_name:
        # Found a precomputed column - return a reference to it
        return SQLQualifiedIdentifier(parts=[alias, column_name])

    return None


def _recurse_ast(
    ast: SQLExpression,
    registry: ColumnRegistry,
    alias_to_cte: Dict[str, str]
) -> SQLExpression:
    """
    Recursively process all node types.

    This mirrors the structure in placeholder.py's resolve_placeholders.
    """
    if isinstance(ast, SQLSelect):
        resolved_columns = []
        for col in ast.columns:
            if isinstance(col, tuple):
                resolved_columns.append((
                    _optimize_fhirpath_calls(col[0], registry, alias_to_cte),
                    col[1]
                ))
            else:
                resolved_columns.append(_optimize_fhirpath_calls(col, registry, alias_to_cte))

        resolved_joins = None
        if ast.joins:
            resolved_joins = []
            for join in ast.joins:
                if isinstance(join, SQLJoin):
                    resolved_joins.append(SQLJoin(
                        join_type=join.join_type,
                        table=_optimize_fhirpath_calls(join.table, registry, alias_to_cte),
                        alias=join.alias,
                        on_condition=_optimize_fhirpath_calls(join.on_condition, registry, alias_to_cte) if join.on_condition else None
                    ))
                else:
                    resolved_joins.append(join)

        return SQLSelect(
            columns=resolved_columns,
            from_clause=_optimize_fhirpath_calls(ast.from_clause, registry, alias_to_cte) if ast.from_clause else None,
            joins=resolved_joins,
            where=_optimize_fhirpath_calls(ast.where, registry, alias_to_cte) if ast.where else None,
            group_by=[_optimize_fhirpath_calls(g, registry, alias_to_cte) for g in ast.group_by] if ast.group_by else None,
            having=_optimize_fhirpath_calls(ast.having, registry, alias_to_cte) if ast.having else None,
            order_by=ast.order_by,
            distinct=ast.distinct,
            limit=ast.limit
        )

    elif isinstance(ast, SQLBinaryOp):
        return SQLBinaryOp(
            operator=ast.operator,
            left=_optimize_fhirpath_calls(ast.left, registry, alias_to_cte),
            right=_optimize_fhirpath_calls(ast.right, registry, alias_to_cte)
        )

    elif isinstance(ast, SQLUnaryOp):
        return SQLUnaryOp(
            operator=ast.operator,
            operand=_optimize_fhirpath_calls(ast.operand, registry, alias_to_cte),
            prefix=ast.prefix
        )

    elif isinstance(ast, SQLCase):
        resolved_when = [
            (_optimize_fhirpath_calls(cond, registry, alias_to_cte),
             _optimize_fhirpath_calls(result, registry, alias_to_cte))
            for cond, result in ast.when_clauses
        ]
        return SQLCase(
            when_clauses=resolved_when,
            else_clause=_optimize_fhirpath_calls(ast.else_clause, registry, alias_to_cte) if ast.else_clause else None,
            operand=_optimize_fhirpath_calls(ast.operand, registry, alias_to_cte) if ast.operand else None
        )

    elif isinstance(ast, SQLList):
        return SQLList(
            items=[_optimize_fhirpath_calls(item, registry, alias_to_cte) for item in ast.items]
        )

    elif isinstance(ast, SQLAlias):
        return SQLAlias(
            expr=_optimize_fhirpath_calls(ast.expr, registry, alias_to_cte),
            alias=ast.alias
        )

    elif isinstance(ast, SQLUnion):
        return SQLUnion(
            operands=[
                _optimize_fhirpath_calls(operand, registry, alias_to_cte)
                for operand in ast.operands
            ]
        )

    elif isinstance(ast, SQLSubquery):
        return SQLSubquery(
            query=_optimize_fhirpath_calls(ast.query, registry, alias_to_cte)
        )

    # For other types (literals, identifiers, etc.), return as-is
    return ast


def run_optimization_phases(
    library: Library,
    context: SQLTranslationContext,
    translator: CQLToSQLTranslator,
) -> Tuple[Dict[str, SQLExpression], Phase1Result, Phase2Result, OptimizationStats]:
    """
    Run all three optimization phases.

    This is the main entry point for retrieve optimization.

    Args:
        library: Parsed CQL library
        context: Translation context
        translator: Translator instance

    Returns:
        Tuple of (resolved_asts, phase1_result, phase2_result, stats)
        - resolved_asts: Map of definition name → resolved SQL AST
        - phase1_result: Result from translation and scanning
        - phase2_result: Result from CTE building
        - stats: OptimizationStats with metrics

    Phases:
        1. Translate + Scan: Translate to AST with placeholders, scan for properties
        2. Build CTEs: Create retrieve CTEs with precomputed columns
        3. Resolve + Optimize: Replace placeholders, optimize property access
    """
    from ..parser.ast_nodes import Definition, FunctionRef
    from .placeholder import RetrievePlaceholder
    from .cte_builder import build_patient_demographics_cte

    stats = OptimizationStats()
    phase1_result = Phase1Result()
    phase2_result = Phase2Result()

    # ========================================================================
    # PRE-SCAN: Check for AgeInYearsAt usage in CQL library
    # ========================================================================
    # This must happen BEFORE Phase 1 translation so the context flag is set
    # when the age functions are translated
    age_at_functions = {"AgeInYearsAt", "AgeInMonthsAt", "AgeInDaysAt"}

    def scan_cql_for_age_functions(node) -> bool:
        """Recursively scan CQL AST for age-at function calls."""
        if node is None:
            return False
        if isinstance(node, FunctionRef):
            if node.name in age_at_functions:
                return True
            # Check arguments
            for arg in node.arguments:
                if scan_cql_for_age_functions(arg):
                    return True
        # Check common attributes that may contain nested expressions
        for attr_name in ['expression', 'operand', 'left', 'right', 'source',
                          'where', 'return_clause', 'then', 'else_clause']:
            if hasattr(node, attr_name):
                attr = getattr(node, attr_name)
                if attr is not None:
                    if scan_cql_for_age_functions(attr):
                        return True
        # Check list attributes
        for attr_name in ['statements', 'elements', 'arguments', 'when_clauses']:
            if hasattr(node, attr_name):
                items = getattr(node, attr_name)
                if items:
                    for item in items:
                        if scan_cql_for_age_functions(item):
                            return True
        return False

    for statement in library.statements:
        if scan_cql_for_age_functions(statement):
            phase1_result.needs_patient_demographics = True
            # Set context flag immediately so Phase 1 translation can use it
            context.has_patient_demographics_cte = True
            break

    # ========================================================================
    # PHASE 1: Translate + Scan
    # ========================================================================
    # Pre-populate CQL ASTs so forward references can inspect return clauses
    context._definition_cql_asts = {}
    for statement in library.statements:
        if isinstance(statement, Definition) and hasattr(statement, 'name') and statement.name:
            context._definition_cql_asts[statement.name] = statement.expression

    for statement in library.statements:
        if not isinstance(statement, Definition):
            continue
        if not hasattr(statement, 'name') or not statement.name:
            continue

        # Translate to SQL AST (retrieves become placeholders)
        sql_ast = translator.translate_definition(statement)
        phase1_result.definition_asts[statement.name] = sql_ast

        # Find all AST-level placeholders in this definition
        placeholders = find_all_placeholders(sql_ast)
        phase1_result.placeholders.extend(placeholders)
        stats.num_retrieves += len(placeholders)

        # Scan for property accesses
        property_map = scan_definition_for_properties(sql_ast, placeholders)

        # Merge into phase1_result
        for key, props in property_map.items():
            if key not in phase1_result.property_usage:
                phase1_result.property_usage[key] = set()
            phase1_result.property_usage[key].update(props)

        # Scan for AgeInYearsAt/AgeInMonthsAt/AgeInDaysAt usage
        if _contains_age_at_function(sql_ast):
            phase1_result.needs_patient_demographics = True

    # ========================================================================
    # PHASE 2: Build CTEs
    # ========================================================================
    # Build CTEs for ALL placeholders, not just those with properties.
    # Multiple 3-tuple keys (resource_type, valueset, profile_url) may produce
    # the same CTE name (e.g., clinical-result vs cancelled profiles for the same
    # resource+valueset).  We must MERGE properties across all keys that map to
    # the same CTE before building, otherwise a key with empty properties will
    # overwrite an earlier build that had precomputed columns.
    all_retrieve_keys = set()
    code_property_map: Dict[Tuple, Optional[str]] = {}
    for placeholder in phase1_result.placeholders:
        all_retrieve_keys.add(placeholder.key)
        if placeholder.code_property:
            code_property_map[placeholder.key] = placeholder.code_property

    # First pass: group keys by (resource_type, valueset) and merge properties.
    # We build each CTE once with the union of all properties from every profile
    # key that shares the same resource_type + valueset.
    # Track which CTE names have already been built so we don't overwrite.
    _built_cte_names: Dict[str, Tuple[SQLSelect, Dict[str, "ColumnInfo"]]] = {}

    for key in all_retrieve_keys:
        resource_type, valueset, profile_url = key
        # Merge properties from ALL keys that will generate the same CTE name.
        # Keys that differ only by profile_url typically produce the same name
        # (unless it's a negation profile like "cancelled" which gets a suffix).
        # Since we don't know the final name until build_retrieve_cte, we merge
        # all properties for keys sharing (resource_type, valueset) as a pre-step.
        merged_properties = set()
        merged_code_property = code_property_map.get(key)
        merged_profile_urls = []
        for other_key in all_retrieve_keys:
            o_rt, o_vs, o_profile = other_key
            if o_rt == resource_type and o_vs == valueset:
                merged_properties.update(phase1_result.property_usage.get(other_key, set()))
                if o_profile:
                    merged_profile_urls.append(o_profile)
                if not merged_code_property and other_key in code_property_map:
                    merged_code_property = code_property_map[other_key]

        # Build CTE (may produce a name that was already built by another key)
        cte_name, cte_ast, column_info = build_retrieve_cte(
            resource_type=resource_type,
            valueset=valueset,
            properties=merged_properties,
            context=context,
            profile_url=profile_url,
            code_property=merged_code_property,
        )

        # Only register the FIRST (richest) build for each CTE name.
        # If a CTE was already built with more or equal columns, keep it.
        if cte_name in _built_cte_names:
            existing_cols = _built_cte_names[cte_name][1]
            if len(column_info) <= len(existing_cols):
                # Just register the key → name mapping without overwriting the CTE
                phase2_result.cte_name_map[(resource_type, valueset, profile_url)] = cte_name
                continue

        _built_cte_names[cte_name] = (cte_ast, column_info)
        phase2_result.register_cte(resource_type, valueset, cte_name, cte_ast, column_info, profile_url=profile_url)

        # Register retrieve CTE name for audit evidence collection.
        # _collect_audit_evidence_exprs reads this set to find CTEs that have _audit_item columns.
        if context.audit_mode:
            if not hasattr(context, '_audit_retrieve_cte_names'):
                context._audit_retrieve_cte_names = set()
            context._audit_retrieve_cte_names.add(cte_name)

        stats.num_ctes_created += 1
        stats.num_properties_precomputed += len(merged_properties)

    # Build patient demographics CTE if needed for age calculations
    if phase1_result.needs_patient_demographics:
        cte_name, cte_ast, column_info = build_patient_demographics_cte()
        phase2_result.register_patient_demographics_cte(cte_ast, column_info)
        stats.num_ctes_created += 1

    # ========================================================================
    # PHASE 3: Resolve + Optimize
    # ========================================================================
    resolved_asts: Dict[str, SQLExpression] = {}

    for def_name, ast in phase1_result.definition_asts.items():
        # Resolve placeholders at AST level (pure AST manipulation)
        resolved_ast = resolve_placeholders(ast, phase2_result.cte_name_map)

        # Apply property access optimization
        # Replace fhirpath calls with precomputed column references
        optimized_ast = optimize_property_access(
            resolved_ast,
            phase2_result.column_registry
        )

        resolved_asts[def_name] = optimized_ast

        # Count resolved placeholders
        placeholders_in_def = find_all_placeholders(ast)
        stats.num_placeholders_resolved += len(placeholders_in_def)

        # Count optimized fhirpath calls (compare before/after)
        # This is a simple heuristic - count fhirpath calls in original
        stats.num_fhirpath_calls_optimized += _count_optimized_fhirpath_calls(
            resolved_ast, optimized_ast
        )

    return resolved_asts, phase1_result, phase2_result, stats


def _count_optimized_fhirpath_calls(
    original_ast: SQLExpression,
    optimized_ast: SQLExpression
) -> int:
    """
    Count how many fhirpath calls were optimized by comparing ASTs.

    This counts the reduction in fhirpath function calls between
    the original and optimized ASTs.

    Args:
        original_ast: The AST before optimization
        optimized_ast: The AST after optimization

    Returns:
        Number of fhirpath calls that were replaced
    """
    original_count = _count_fhirpath_calls(original_ast)
    optimized_count = _count_fhirpath_calls(optimized_ast)
    return max(0, original_count - optimized_count)


def _count_fhirpath_calls(ast: SQLExpression) -> int:
    """
    Count all fhirpath function calls in an AST.

    Args:
        ast: SQL AST to count calls in

    Returns:
        Total count of fhirpath_* function calls
    """
    count = 0

    def walk(node):
        nonlocal count
        if node is None:
            return

        if isinstance(node, SQLFunctionCall):
            if node.name.startswith('fhirpath_'):
                count += 1
            for arg in node.args:
                walk(arg)

        elif isinstance(node, SQLSelect):
            for col in node.columns:
                if isinstance(col, tuple):
                    walk(col[0])
                else:
                    walk(col)
            if node.from_clause:
                walk(node.from_clause)
            if node.joins:
                for join in node.joins:
                    if isinstance(join, SQLJoin):
                        walk(join.table)
                        if join.on_condition:
                            walk(join.on_condition)
            if node.where:
                walk(node.where)
            if node.group_by:
                for g in node.group_by:
                    walk(g)
            if node.having:
                walk(node.having)

        elif isinstance(node, SQLBinaryOp):
            walk(node.left)
            walk(node.right)

        elif isinstance(node, SQLUnaryOp):
            walk(node.operand)

        elif isinstance(node, SQLCase):
            for cond, result in node.when_clauses:
                walk(cond)
                walk(result)
            if node.else_clause:
                walk(node.else_clause)
            if node.operand:
                walk(node.operand)

        elif isinstance(node, (SQLList, SQLArray)):
            for item in getattr(node, 'items', getattr(node, 'elements', [])):
                walk(item)

        elif isinstance(node, SQLAlias):
            walk(node.expr)

    walk(ast)
    return count


def _contains_age_at_function(ast: SQLExpression) -> bool:
    """
    Check if an AST contains AgeInYearsAt, AgeInMonthsAt, or AgeInDaysAt function calls.

    These functions require patient demographics (birthDate) for efficient
    age calculation in population mode.

    Args:
        ast: SQL AST to scan

    Returns:
        True if any age-at function is found, False otherwise
    """
    age_at_functions = {"AgeInYearsAt", "AgeInMonthsAt", "AgeInDaysAt"}
    found = False

    def walk(node):
        nonlocal found
        if node is None or found:
            return

        if isinstance(node, SQLFunctionCall):
            if node.name in age_at_functions:
                found = True
                return
            for arg in node.args:
                walk(arg)

        elif isinstance(node, SQLSelect):
            for col in node.columns:
                if isinstance(col, tuple):
                    walk(col[0])
                else:
                    walk(col)
            if node.from_clause:
                walk(node.from_clause)
            if node.joins:
                for join in node.joins:
                    if isinstance(join, SQLJoin):
                        walk(join.table)
                        if join.on_condition:
                            walk(join.on_condition)
            if node.where:
                walk(node.where)
            if node.group_by:
                for g in node.group_by:
                    walk(g)
            if node.having:
                walk(node.having)

        elif isinstance(node, SQLBinaryOp):
            walk(node.left)
            walk(node.right)

        elif isinstance(node, SQLUnaryOp):
            walk(node.operand)

        elif isinstance(node, SQLCase):
            for cond, result in node.when_clauses:
                walk(cond)
                walk(result)
            if node.else_clause:
                walk(node.else_clause)
            if node.operand:
                walk(node.operand)

        elif isinstance(node, (SQLList, SQLArray)):
            for item in getattr(node, 'items', getattr(node, 'elements', [])):
                walk(item)

        elif isinstance(node, SQLAlias):
            walk(node.expr)

    walk(ast)
    return found


__all__ = [
    "Phase1Result",
    "Phase2Result",
    "OptimizationStats",
    "scan_definition_for_properties",
    "optimize_property_access",
    "run_optimization_phases",
]

"""
Main orchestrator for retrieve optimization.

This module coordinates the three phases:
1. Translate + Scan
2. Build CTEs
3. Resolve + Optimize
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from .types import (
    SQLExpression, SQLSelect, SQLFunctionCall, SQLLiteral, SQLNamedArg,
    SQLQualifiedIdentifier, SQLIdentifier, SQLAlias, SQLJoin,
    SQLBinaryOp, SQLUnaryOp, SQLCase, SQLList, SQLArray, SQLLambda,
    SQLLambda2, SQLStructFieldAccess, SQLInterval, SQLCast, SQLExtract,
    SQLUnion, SQLIntersect, SQLExcept, SQLSubquery, SQLRaw, SQLExists,
    SQLRecursiveCTEFold, SQLWindowFunction, SQLEvidenceItem, SQLAuditStruct,
    CTEDefinition,
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


def propagate_resource_column_lineage(
    ctes: List[CTEDefinition],
    registry: ColumnRegistry,
) -> List[CTEDefinition]:
    """
    Carry precomputed-column metadata through resource-preserving derived CTEs.

    A derived CTE is safe to register when it selects the same ``resource`` rows
    from one already-registered CTE. For explicit ``patient_id, resource``
    projections, the inherited columns are also appended to the projection so
    downstream references can use them physically. This is generic lineage
    propagation over CTE shape, not measure/library/profile-specific logic.
    """
    propagated: List[CTEDefinition] = []

    for cte in ctes:
        query = cte.query
        if cte.columns is not None:
            propagated.append(cte)
            continue
        cte_name = _normalize_cte_name(cte.name)
        if isinstance(query, SQLSelect):
            updated_query, inherited = _propagate_select_resource_columns(query, registry)
        elif isinstance(query, SQLUnion):
            updated_query, inherited = _propagate_union_resource_columns(query, registry)
        else:
            propagated.append(cte)
            continue

        if inherited:
            existing = dict(registry.get_columns(cte_name))
            merged = dict(inherited)
            merged.update(existing)
            registry.register_cte(cte_name, merged)
            propagated.append(CTEDefinition(name=cte.name, query=updated_query, columns=cte.columns))
        else:
            propagated.append(cte)

    return propagated


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


def _extend_alias_mapping_for_select(
    select: SQLSelect,
    alias_to_cte: Dict[str, str],
) -> Dict[str, str]:
    """Return alias mappings with aliases scoped to one SELECT added."""
    local_aliases = dict(alias_to_cte)
    if select.from_clause:
        _extract_alias_from_table_ref(select.from_clause, local_aliases)
    if select.joins:
        for join in select.joins:
            if isinstance(join, SQLJoin):
                _extract_alias_from_table_ref(join.table, local_aliases, join.alias)
    return local_aliases


def _normalize_cte_name(name: str) -> str:
    """Return an unquoted CTE identifier suitable for ColumnRegistry lookups."""
    if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
        return name[1:-1].replace('""', '"')
    return name


def _table_ref_cte_and_alias(table_ref: SQLExpression) -> Tuple[Optional[str], Optional[str]]:
    """Extract ``(cte_name, alias)`` from a simple FROM/JOIN table reference."""
    if isinstance(table_ref, SQLAlias):
        cte_name, _alias = _table_ref_cte_and_alias(table_ref.expr)
        return cte_name, table_ref.alias

    if isinstance(table_ref, SQLIdentifier):
        cte_name = _normalize_cte_name(table_ref.name)
        return cte_name, cte_name

    if isinstance(table_ref, SQLQualifiedIdentifier) and table_ref.parts:
        cte_name = _normalize_cte_name(table_ref.parts[-1])
        return cte_name, cte_name

    if isinstance(table_ref, SQLRaw):
        raw = table_ref.raw_sql.strip()
        if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
            cte_name = _normalize_cte_name(raw)
            return cte_name, cte_name
        if raw.replace("_", "").replace(".", "").isalnum():
            cte_name = raw.split(".")[-1]
            return cte_name, cte_name

    return None, None


def _selected_column_name(col: Any) -> Optional[str]:
    """Return the output column name for a simple SELECT projection."""
    if isinstance(col, tuple):
        _expr, alias = col
        return alias
    if isinstance(col, SQLAlias):
        return col.alias
    if isinstance(col, SQLIdentifier):
        return col.name
    if isinstance(col, SQLQualifiedIdentifier) and col.parts:
        return col.parts[-1]
    return None


def _select_has_star_for_alias(select: SQLSelect, source_alias: str) -> bool:
    """Check for SELECT * or SELECT source_alias.*."""
    if not select.columns:
        return False
    for col in select.columns:
        expr = col[0] if isinstance(col, tuple) else col.expr if isinstance(col, SQLAlias) else col
        if isinstance(expr, SQLIdentifier) and expr.name == "*":
            return True
        if (
            isinstance(expr, SQLQualifiedIdentifier)
            and len(expr.parts) == 2
            and expr.parts[0] == source_alias
            and expr.parts[1] == "*"
        ):
            return True
    return False


def _selects_direct_column(select: SQLSelect, source_alias: str, column_name: str) -> bool:
    """Return true when SELECT projects source_alias.column_name unchanged."""
    for col in select.columns:
        expr = col[0] if isinstance(col, tuple) else col.expr if isinstance(col, SQLAlias) else col
        output_name = _selected_column_name(col)
        if output_name != column_name:
            continue
        if isinstance(expr, SQLQualifiedIdentifier):
            if len(expr.parts) == 2 and expr.parts == [source_alias, column_name]:
                return True
        elif isinstance(expr, SQLIdentifier):
            if expr.name == column_name and not select.joins:
                return True
    return False


def _select_resource_lineage(
    select: SQLSelect,
    registry: ColumnRegistry,
    allow_missing_patient_id: bool = False,
) -> Tuple[Optional[str], Dict[str, ColumnInfo]]:
    """Return source alias and inherited columns for a resource-preserving SELECT."""
    if select.from_clause is None or select.group_by or select.having:
        return None, {}

    source_cte, source_alias = _table_ref_cte_and_alias(select.from_clause)
    if not source_cte or not source_alias:
        return None, {}

    inherited = registry.get_columns(source_cte)
    if not inherited:
        return None, {}

    has_single_source = not select.joins
    has_star = has_single_source and _select_has_star_for_alias(select, source_alias)
    has_resource = has_star or _selects_direct_column(select, source_alias, "resource")
    has_patient_id = has_star or _selects_direct_column(select, source_alias, "patient_id")
    if not has_resource or not (has_patient_id or allow_missing_patient_id):
        return None, {}

    return source_alias, dict(inherited)


def _materialize_select_inherited_columns(
    select: SQLSelect,
    source_alias: str,
    inherited: Dict[str, ColumnInfo],
    force_explicit: bool = False,
) -> Tuple[SQLSelect, Dict[str, ColumnInfo]]:
    """Add inherited columns to a resource-preserving SELECT projection."""
    if force_explicit:
        columns: List[SQLExpression] = [
            SQLQualifiedIdentifier(parts=[source_alias, "patient_id"]),
            SQLQualifiedIdentifier(parts=[source_alias, "resource"]),
        ]
        columns.extend(
            SQLQualifiedIdentifier(parts=[source_alias, column_name])
            for column_name in inherited
        )
        return (
            SQLSelect(
                columns=columns,
                from_clause=select.from_clause,
                joins=select.joins,
                where=select.where,
                group_by=select.group_by,
                having=select.having,
                order_by=select.order_by,
                limit=select.limit,
                distinct=select.distinct,
            ),
            dict(inherited),
        )

    has_star = _select_has_star_for_alias(select, source_alias)
    if has_star:
        return select, dict(inherited)

    if not inherited:
        return select, {}

    projected_names = {
        name
        for name in (_selected_column_name(col) for col in select.columns)
        if name is not None
    }
    additions: List[SQLExpression] = []
    inherited_available: Dict[str, ColumnInfo] = {}
    for column_name, info in inherited.items():
        if column_name in projected_names:
            inherited_available[column_name] = info
            continue
        additions.append(SQLQualifiedIdentifier(parts=[source_alias, column_name]))
        inherited_available[column_name] = info

    if not additions:
        return select, inherited_available

    return (
        SQLSelect(
            columns=[*select.columns, *additions],
            from_clause=select.from_clause,
            joins=select.joins,
            where=select.where,
            group_by=select.group_by,
            having=select.having,
            order_by=select.order_by,
            limit=select.limit,
            distinct=select.distinct,
        ),
        inherited_available,
    )


def _propagate_select_resource_columns(
    select: SQLSelect,
    registry: ColumnRegistry,
) -> Tuple[SQLSelect, Dict[str, ColumnInfo]]:
    """Infer and materialize inherited precomputed columns for one SQLSelect."""
    source_alias, inherited = _select_resource_lineage(select, registry)
    if not source_alias:
        return select, {}
    return _materialize_select_inherited_columns(select, source_alias, inherited)


def _union_operand_inherited_columns(
    operand: SQLExpression,
    registry: ColumnRegistry,
) -> Dict[str, ColumnInfo]:
    """Return inherited columns available to one resource-shaped UNION operand."""
    if isinstance(operand, SQLIdentifier):
        return dict(registry.get_columns(_normalize_cte_name(operand.name)))

    if isinstance(operand, SQLSubquery):
        query = operand.query
        if isinstance(query, SQLIdentifier):
            return dict(registry.get_columns(_normalize_cte_name(query.name)))
        if isinstance(query, SQLSelect):
            _alias, inherited = _select_resource_lineage(
                query, registry, allow_missing_patient_id=True
            )
            return inherited
        return {}

    if isinstance(operand, SQLSelect):
        _alias, inherited = _select_resource_lineage(
            operand, registry, allow_missing_patient_id=True
        )
        return inherited

    return {}


def _common_union_columns(
    branch_columns: List[Dict[str, ColumnInfo]],
) -> Dict[str, ColumnInfo]:
    """Return column metadata common to every UNION branch."""
    if not branch_columns:
        return {}

    common_names = set(branch_columns[0])
    for columns in branch_columns[1:]:
        common_names &= set(columns)

    common: Dict[str, ColumnInfo] = {}
    for column_name, first_info in branch_columns[0].items():
        if column_name not in common_names:
            continue
        if all(
            columns[column_name].fhirpath == first_info.fhirpath
            and columns[column_name].sql_type == first_info.sql_type
            for columns in branch_columns[1:]
        ):
            common[column_name] = first_info
    return common


def _materialize_union_operand_columns(
    operand: SQLExpression,
    inherited: Dict[str, ColumnInfo],
) -> SQLExpression:
    """Rewrite a UNION operand to project patient_id, resource, and common columns."""
    if isinstance(operand, SQLIdentifier):
        select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_id"),
                SQLIdentifier(name="resource"),
                *[SQLIdentifier(name=column_name) for column_name in inherited],
            ],
            from_clause=operand,
        )
        return SQLSubquery(query=select)

    if isinstance(operand, SQLSubquery):
        query = operand.query
        if isinstance(query, SQLIdentifier):
            select = SQLSelect(
                columns=[
                    SQLIdentifier(name="patient_id"),
                    SQLIdentifier(name="resource"),
                    *[SQLIdentifier(name=column_name) for column_name in inherited],
                ],
                from_clause=query,
            )
            return SQLSubquery(query=select)
        if isinstance(query, SQLSelect):
            source_cte, source_alias = _table_ref_cte_and_alias(query.from_clause) if query.from_clause else (None, None)
            if source_alias:
                updated, _cols = _materialize_select_inherited_columns(
                    query, source_alias, inherited, force_explicit=True
                )
                return SQLSubquery(query=updated)
        return operand

    if isinstance(operand, SQLSelect):
        _source_cte, source_alias = _table_ref_cte_and_alias(operand.from_clause) if operand.from_clause else (None, None)
        if source_alias:
            updated, _cols = _materialize_select_inherited_columns(
                operand, source_alias, inherited, force_explicit=True
            )
            return updated

    return operand


def _propagate_union_resource_columns(
    union: SQLUnion,
    registry: ColumnRegistry,
) -> Tuple[SQLUnion, Dict[str, ColumnInfo]]:
    """Propagate common precomputed columns through resource-shaped UNIONs."""
    branch_columns = [
        _union_operand_inherited_columns(operand, registry)
        for operand in union.operands
    ]
    if not branch_columns or any(not columns for columns in branch_columns):
        return union, {}

    common = _common_union_columns(branch_columns)
    if not common:
        return union, {}

    return (
        SQLUnion(
            operands=[
                _materialize_union_operand_columns(operand, common)
                for operand in union.operands
            ],
            distinct=union.distinct,
        ),
        common,
    )


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
        if node.order_by:
            for expr, _direction in node.order_by:
                visitor(expr)

    elif isinstance(node, SQLNamedArg):
        visitor(node.value)

    elif isinstance(node, SQLStructFieldAccess):
        visitor(node.expr)

    elif isinstance(node, (SQLLambda, SQLLambda2)):
        visitor(node.body)

    elif isinstance(node, SQLInterval):
        visitor(node.low)
        visitor(node.high)

    elif isinstance(node, SQLCast):
        visitor(node.expression)

    elif isinstance(node, SQLExtract):
        visitor(node.source)

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
        if node.joins:
            for join in node.joins:
                visitor(join)
        if node.order_by:
            for expr, _direction in node.order_by:
                visitor(expr)

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

    elif isinstance(node, (SQLUnion, SQLIntersect, SQLExcept)):
        # Recurse into each operand of the set operation
        for operand in node.operands:
            visitor(operand)

    elif isinstance(node, SQLSubquery):
        # Recurse into the subquery
        visitor(node.query)

    elif isinstance(node, SQLExists):
        visitor(node.subquery)

    elif isinstance(node, SQLRecursiveCTEFold):
        visitor(node.source_expr)
        visitor(node.anchor)
        visitor(node.body)

    elif isinstance(node, SQLWindowFunction):
        for arg in node.function_args:
            visitor(arg)
        for expr in node.partition_by:
            visitor(expr)
        for expr, _direction in node.order_by:
            visitor(expr)

    elif isinstance(node, SQLEvidenceItem):
        visitor(node.target)
        visitor(node.attribute)
        visitor(node.value)
        visitor(node.threshold)

    elif isinstance(node, SQLAuditStruct):
        visitor(node.result_expr)
        visitor(node.evidence_expr)


_RAW_CTE_ALIAS_RE = re.compile(
    r'\b(?:FROM|JOIN)\s+"((?:[^"]|"")*)"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)',
    re.IGNORECASE,
)
_RAW_UNQUOTED_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?!\")([A-Za-z_][A-Za-z0-9_.]*)"
    r"(?:\s+AS)?\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_RAW_FHIRPATH_RESOURCE_RE = re.compile(
    r"\b(fhirpath_(?:text|date|number|bool|quantity|timestamp))"
    r"\(([A-Za-z_][A-Za-z0-9_]*)\.resource,\s*'((?:''|[^'])+)'\)"
)
_RAW_ALIAS_STOPWORDS = {
    "AS", "ON", "WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "JOIN",
    "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS", "UNION",
}


def _merge_raw_alias_mapping(
    raw_sql: str,
    alias_to_cte: Dict[str, str],
    registry: Optional[ColumnRegistry] = None,
) -> Dict[str, str]:
    """
    Extract additional alias mappings from trusted translator-generated SQL text.

    SQLRaw is used for residual template paths that can contain complete
    subqueries. The normal AST alias scanner cannot see inside those strings,
    so this recognizes quoted CTE references emitted by this translator. If an
    alias maps to multiple CTEs in the same raw fragment, it is dropped rather
    than guessed.
    """
    merged = dict(alias_to_cte)
    conflicts: Set[str] = set()

    for raw_cte_name, alias in _RAW_CTE_ALIAS_RE.findall(raw_sql):
        cte_name = raw_cte_name.replace('""', '"')
        existing = merged.get(alias)
        if existing is not None and existing != cte_name:
            conflicts.add(alias)
        else:
            merged[alias] = cte_name

    for raw_table_name, alias in _RAW_UNQUOTED_ALIAS_RE.findall(raw_sql):
        if alias.upper() in _RAW_ALIAS_STOPWORDS:
            continue
        cte_name = raw_table_name.split(".")[-1]
        if registry is not None and registry.get_columns(cte_name):
            existing = merged.get(alias)
            if existing is not None and existing != cte_name:
                conflicts.add(alias)
            else:
                merged[alias] = cte_name
        else:
            conflicts.add(alias)

    for alias in conflicts:
        merged.pop(alias, None)

    return merged


def _optimize_raw_fhirpath_resource_calls(
    raw_sql: str,
    registry: ColumnRegistry,
    alias_to_cte: Dict[str, str],
) -> str:
    """
    Replace direct fhirpath_*(alias.resource, 'path') calls inside SQLRaw.

    This mirrors the AST optimizer for trusted SQLRaw generated by translator
    templates. It remains conservative: only direct resource extraction is rewritten
    and only when the column registry has an exact path match for the alias' CTE.
    """
    raw_alias_to_cte = _merge_raw_alias_mapping(raw_sql, alias_to_cte, registry)

    def replace(match: re.Match[str]) -> str:
        alias = match.group(2)
        path = match.group(3).replace("''", "'")
        cte_name = raw_alias_to_cte.get(alias, alias)
        column_name = registry.lookup(cte_name, path)
        if not column_name:
            return match.group(0)
        return f"{alias}.{column_name}"

    return _RAW_FHIRPATH_RESOURCE_RE.sub(replace, raw_sql)


def optimize_rendered_property_access(
    sql_text: str,
    registry: ColumnRegistry,
    alias_to_cte: Optional[Dict[str, str]] = None,
) -> str:
    """
    Apply registry-driven property-column optimization to rendered SQL text.

    This is the final boundary for translator constructs that only materialize
    as SQL text during serialization. It uses the same conservative replacement
    rules as SQLRaw optimization and is not tied to a measure, library, or FHIR
    profile.
    """
    return _optimize_raw_fhirpath_resource_calls(sql_text, registry, alias_to_cte or {})


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

    if isinstance(ast, SQLRaw):
        optimized_sql = _optimize_raw_fhirpath_resource_calls(
            ast.raw_sql, registry, alias_to_cte
        )
        if optimized_sql == ast.raw_sql:
            return ast
        return SQLRaw(optimized_sql)

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
                distinct=ast.distinct,
                order_by=[
                    (_optimize_fhirpath_calls(expr, registry, alias_to_cte), direction)
                    for expr, direction in ast.order_by
                ] if ast.order_by else None,
            )

        # For other function calls, recurse into args
        return SQLFunctionCall(
            name=ast.name,
            args=[_optimize_fhirpath_calls(arg, registry, alias_to_cte) for arg in ast.args],
            distinct=ast.distinct,
            order_by=[
                (_optimize_fhirpath_calls(expr, registry, alias_to_cte), direction)
                for expr, direction in ast.order_by
            ] if ast.order_by else None,
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
        select_alias_to_cte = _extend_alias_mapping_for_select(ast, alias_to_cte)
        resolved_columns = []
        for col in ast.columns:
            if isinstance(col, tuple):
                resolved_columns.append((
                    _optimize_fhirpath_calls(col[0], registry, select_alias_to_cte),
                    col[1]
                ))
            else:
                resolved_columns.append(_optimize_fhirpath_calls(col, registry, select_alias_to_cte))

        resolved_joins = None
        if ast.joins:
            resolved_joins = []
            for join in ast.joins:
                if isinstance(join, SQLJoin):
                    resolved_joins.append(SQLJoin(
                        join_type=join.join_type,
                        table=_optimize_fhirpath_calls(join.table, registry, select_alias_to_cte),
                        alias=join.alias,
                        on_condition=_optimize_fhirpath_calls(join.on_condition, registry, select_alias_to_cte) if join.on_condition else None
                    ))
                else:
                    resolved_joins.append(join)

        return SQLSelect(
            columns=resolved_columns,
            from_clause=_optimize_fhirpath_calls(ast.from_clause, registry, select_alias_to_cte) if ast.from_clause else None,
            joins=resolved_joins,
            where=_optimize_fhirpath_calls(ast.where, registry, select_alias_to_cte) if ast.where else None,
            group_by=[_optimize_fhirpath_calls(g, registry, select_alias_to_cte) for g in ast.group_by] if ast.group_by else None,
            having=_optimize_fhirpath_calls(ast.having, registry, select_alias_to_cte) if ast.having else None,
            order_by=[
                (_optimize_fhirpath_calls(expr, registry, select_alias_to_cte), direction)
                for expr, direction in ast.order_by
            ] if ast.order_by else None,
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

    elif isinstance(ast, SQLArray):
        return SQLArray(
            elements=[_optimize_fhirpath_calls(item, registry, alias_to_cte) for item in ast.elements]
        )

    elif isinstance(ast, SQLNamedArg):
        return SQLNamedArg(
            name=ast.name,
            value=_optimize_fhirpath_calls(ast.value, registry, alias_to_cte),
        )

    elif isinstance(ast, SQLStructFieldAccess):
        return SQLStructFieldAccess(
            expr=_optimize_fhirpath_calls(ast.expr, registry, alias_to_cte),
            field_name=ast.field_name,
        )

    elif isinstance(ast, SQLLambda):
        return SQLLambda(
            param=ast.param,
            body=_optimize_fhirpath_calls(ast.body, registry, alias_to_cte),
        )

    elif isinstance(ast, SQLLambda2):
        return SQLLambda2(
            params=ast.params,
            body=_optimize_fhirpath_calls(ast.body, registry, alias_to_cte),
        )

    elif isinstance(ast, SQLInterval):
        return SQLInterval(
            low=_optimize_fhirpath_calls(ast.low, registry, alias_to_cte) if ast.low else None,
            high=_optimize_fhirpath_calls(ast.high, registry, alias_to_cte) if ast.high else None,
            low_closed=ast.low_closed,
            high_closed=ast.high_closed,
        )

    elif isinstance(ast, SQLCast):
        return SQLCast(
            expression=_optimize_fhirpath_calls(ast.expression, registry, alias_to_cte),
            target_type=ast.target_type,
            try_cast=ast.try_cast,
        )

    elif isinstance(ast, SQLExtract):
        return SQLExtract(
            extract_field=ast.extract_field,
            source=_optimize_fhirpath_calls(ast.source, registry, alias_to_cte),
        )

    elif isinstance(ast, SQLAlias):
        return SQLAlias(
            expr=_optimize_fhirpath_calls(ast.expr, registry, alias_to_cte),
            alias=ast.alias,
            implicit_alias=ast.implicit_alias,
        )

    elif isinstance(ast, SQLUnion):
        return SQLUnion(
            operands=[
                _optimize_fhirpath_calls(operand, registry, alias_to_cte)
                for operand in ast.operands
            ],
            distinct=ast.distinct,
        )

    elif isinstance(ast, SQLIntersect):
        return SQLIntersect(
            operands=[
                _optimize_fhirpath_calls(operand, registry, alias_to_cte)
                for operand in ast.operands
            ]
        )

    elif isinstance(ast, SQLExcept):
        return SQLExcept(
            operands=[
                _optimize_fhirpath_calls(operand, registry, alias_to_cte)
                for operand in ast.operands
            ]
        )

    elif isinstance(ast, SQLSubquery):
        return SQLSubquery(
            query=_optimize_fhirpath_calls(ast.query, registry, alias_to_cte)
        )

    elif isinstance(ast, SQLExists):
        return SQLExists(
            subquery=_optimize_fhirpath_calls(ast.subquery, registry, alias_to_cte)
        )

    elif isinstance(ast, SQLRecursiveCTEFold):
        return SQLRecursiveCTEFold(
            source_expr=_optimize_fhirpath_calls(ast.source_expr, registry, alias_to_cte),
            source_alias=ast.source_alias,
            anchor=_optimize_fhirpath_calls(ast.anchor, registry, alias_to_cte),
            body=_optimize_fhirpath_calls(ast.body, registry, alias_to_cte),
            distinct=ast.distinct,
            accum_alias=ast.accum_alias,
        )

    elif isinstance(ast, SQLWindowFunction):
        return SQLWindowFunction(
            function=ast.function,
            function_args=[
                _optimize_fhirpath_calls(arg, registry, alias_to_cte)
                for arg in ast.function_args
            ],
            partition_by=[
                _optimize_fhirpath_calls(expr, registry, alias_to_cte)
                for expr in ast.partition_by
            ],
            order_by=[
                (_optimize_fhirpath_calls(expr, registry, alias_to_cte), direction)
                for expr, direction in ast.order_by
            ],
            frame_clause=ast.frame_clause,
        )

    elif isinstance(ast, SQLEvidenceItem):
        return SQLEvidenceItem(
            target=_optimize_fhirpath_calls(ast.target, registry, alias_to_cte),
            attribute=_optimize_fhirpath_calls(ast.attribute, registry, alias_to_cte),
            value=_optimize_fhirpath_calls(ast.value, registry, alias_to_cte),
            operator_str=ast.operator_str,
            threshold=_optimize_fhirpath_calls(ast.threshold, registry, alias_to_cte),
            trace=ast.trace,
        )

    elif isinstance(ast, SQLAuditStruct):
        return SQLAuditStruct(
            result_expr=_optimize_fhirpath_calls(ast.result_expr, registry, alias_to_cte),
            evidence_expr=_optimize_fhirpath_calls(ast.evidence_expr, registry, alias_to_cte),
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

        # Also scan let-variable CTE bodies produced by this definition
        for let_cte_body in context._let_variable_ctes.get(statement.name, {}).values():
            let_placeholders = find_all_placeholders(let_cte_body)
            phase1_result.placeholders.extend(let_placeholders)
            stats.num_retrieves += len(let_placeholders)

        # Also scan let-variable CTE bodies produced by this definition
        for let_cte_body in context._let_variable_ctes.get(statement.name, {}).values():
            let_placeholders = find_all_placeholders(let_cte_body)
            phase1_result.placeholders.extend(let_placeholders)
            stats.num_retrieves += len(let_placeholders)

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

    # Scan function promotion CTE bodies for placeholders (done once, not per-definition)
    for fn_ctes in context._function_promotion_ctes.values():
        for fn_cte_body in fn_ctes.values():
            fn_placeholders = find_all_placeholders(fn_cte_body)
            phase1_result.placeholders.extend(fn_placeholders)
            stats.num_retrieves += len(fn_placeholders)

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

        # Also resolve placeholders in let-variable CTE bodies for this definition
        let_ctes = context._let_variable_ctes.get(def_name, {})
        for let_cte_name, let_cte_body in list(let_ctes.items()):
            resolved_body = resolve_placeholders(let_cte_body, phase2_result.cte_name_map)
            optimized_body = optimize_property_access(
                resolved_body,
                phase2_result.column_registry
            )
            context._let_variable_ctes[def_name][let_cte_name] = optimized_body

        # Count resolved placeholders (definition + let-variable CTEs)
        placeholders_in_def = find_all_placeholders(ast)
        stats.num_placeholders_resolved += len(placeholders_in_def)

        # Count optimized fhirpath calls (compare before/after)
        # This is a simple heuristic - count fhirpath calls in original
        stats.num_fhirpath_calls_optimized += _count_optimized_fhirpath_calls(
            resolved_ast, optimized_ast
        )

    # Resolve placeholders in function promotion CTE bodies
    for fn_key, fn_ctes in context._function_promotion_ctes.items():
        for fn_cte_name, fn_cte_body in list(fn_ctes.items()):
            resolved_body = resolve_placeholders(fn_cte_body, phase2_result.cte_name_map)
            optimized_body = optimize_property_access(
                resolved_body,
                phase2_result.column_registry
            )
            context._function_promotion_ctes[fn_key][fn_cte_name] = optimized_body

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

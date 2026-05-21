"""
UNION ALL generation for SQL-on-FHIR v2.

Handles unionAll structures in ViewDefinitions, generating SQL UNION ALL queries
that combine results from multiple select branches.
"""

import logging
import re
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .parser import Select

from .parser import Column

_logger = logging.getLogger(__name__)
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


class UnionGeneratorError(Exception):
    """Raised when UNION ALL generation fails."""
    pass


def _quote_identifier(name: str) -> str:
    if not isinstance(name, str) or not name or not _SAFE_IDENTIFIER_RE.fullmatch(name):
        raise UnionGeneratorError(
            f"Invalid SQL identifier in unionAll base query: {name!r}"
        )
    return f'"{name}"'


def _quote_table_reference(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise UnionGeneratorError("unionAll base query table must be a non-empty string")
    parts = name.split(".")
    if any(part == "" for part in parts):
        raise UnionGeneratorError(f"Invalid SQL table reference in unionAll base query: {name!r}")
    return ".".join(_quote_identifier(part) for part in parts)


def _normalize_base_query(base_query: str) -> str:
    """Return a quoted table reference plus optional safe alias.

    The legacy helper historically accepted a raw ``FROM`` fragment such as
    ``"patients t"``. Keep that compatibility shape, but treat it as structured
    ``table [AS] alias`` input instead of executable SQL.
    """
    if not isinstance(base_query, str) or not base_query.strip():
        raise UnionGeneratorError("unionAll base query must be a non-empty string")

    tokens = base_query.strip().split()
    if len(tokens) == 1:
        table_name = tokens[0]
        alias = None
        use_as = False
    elif len(tokens) == 2:
        table_name, alias = tokens
        use_as = False
    elif len(tokens) == 3 and tokens[1].lower() == "as":
        table_name, alias = tokens[0], tokens[2]
        use_as = True
    else:
        raise UnionGeneratorError(
            "unionAll base query must be a table reference with an optional alias"
        )

    quoted_table = _quote_table_reference(table_name)
    if alias is None:
        return quoted_table
    if not _SAFE_IDENTIFIER_RE.fullmatch(alias):
        raise UnionGeneratorError(
            f"Invalid SQL alias in unionAll base query: {alias!r}"
        )
    return f"{quoted_table} AS {alias}" if use_as else f"{quoted_table} {alias}"


def generate_union_all(
    union_selects: List['Select'],
    base_query: str,
    generator: 'SQLGenerator',
    resource_var: str = "t.resource"
) -> str:
    """Generate UNION ALL SQL from a list of Select structures.

    Each Select in union_selects becomes a branch of the UNION ALL.
    All branches must produce the same column names.

    Args:
        union_selects: List of Select structures to union
        base_query: Base table reference (e.g., "patients t")
        generator: SQLGenerator instance for generating column expressions
        resource_var: Variable name for the resource in FHIRPath expressions

    Returns:
        SQL string with UNION ALL combining all branches

    Raises:
        UnionGeneratorError: If union_selects is empty or column names don't match
    """
    if not union_selects:
        raise UnionGeneratorError("unionAll requires at least one select branch")

    safe_base_query = _normalize_base_query(base_query)
    branch_sqls = []
    reference_schema = None

    for i, select in enumerate(union_selects):
        branch_sql, branch_schema = _generate_union_branch(
            select, safe_base_query, generator, resource_var
        )
        branch_sqls.append(branch_sql)

        if reference_schema is None:
            reference_schema = branch_schema
        elif reference_schema != branch_schema:
            raise UnionGeneratorError(
                f"UNION ALL branch {i} has mismatched column schema. "
                f"Expected: {reference_schema}, Got: {branch_schema}"
            )

    return "\nUNION ALL\n".join(branch_sqls)


def _build_select_query(
    selects: List['Select'],
    base_query: str,
    generator: 'SQLGenerator',
    resource_var: str,
) -> str:
    """Build a SELECT query for one expanded union branch."""
    column_exprs, join_clauses, where_conditions = generator._process_selects(
        selects,
        resource_var,
        root_resource_var=resource_var,
    )

    if not column_exprs:
        return "SELECT NULL WHERE FALSE"

    sql = "SELECT\n    " + ",\n    ".join(column_exprs) + f"\nFROM {base_query}"
    if join_clauses:
        sql += "\n" + "\n".join(join_clauses)
    if where_conditions:
        sql += "\nWHERE " + "\n  AND ".join(where_conditions)
    return sql


def _generate_union_branch(
    select: 'Select',
    base_query: str,
    generator: 'SQLGenerator',
    resource_var: str
) -> tuple[str, List[Tuple[str, str | None, bool]]]:
    """Generate SQL for a single UNION branch.

    Handles both simple column selects and nested unionAll structures.

    Args:
        select: Select structure for this branch
        base_query: Base table reference
        generator: SQLGenerator instance
        resource_var: Variable name for the resource

    Returns:
        Tuple of (SQL string, effective output schema)
    """
    schema = _extract_column_schema(select, generator)
    branch_sqls = [
        _build_select_query(expanded, base_query, generator, resource_var)
        for expanded in generator._expand_select_unions(select)
    ]
    return "\nUNION ALL\n".join(branch_sqls), schema


def _extract_column_schema(
    select: 'Select',
    generator: 'SQLGenerator',
) -> List[Tuple[str, str | None, bool]]:
    """Extract the effective output schema from a Select structure."""
    return generator._collect_branch_column_schema(select)


def _extract_column_names(select: 'Select') -> List[str]:
    """Extract column names from a Select structure.

    Handles nested unionAll by recursively extracting from the first branch.

    Args:
        select: Select structure to extract names from

    Returns:
        List of column names
    """
    names = [col.name for col in select.column]
    for nested in select.select:
        names.extend(_extract_column_names(nested))
    if select.unionAll:
        names.extend(_extract_column_names(select.unionAll[0]))
    return names


class UnionGenerator:
    """Manages UNION ALL SQL generation for complex nested structures.

    .. deprecated::
        This class is not used by the main ``SQLGenerator``, which implements
        union handling inline.  Prefer the module-level ``generate_union_all()``
        function for new code.  Will be removed in a future release.
    """

    def __init__(self, generator: 'SQLGenerator'):
        """Initialize the UnionGenerator.

        Args:
            generator: SQLGenerator instance for column expression generation
        """
        self.generator = generator

    def generate(
        self,
        union_selects: List['Select'],
        base_query: str,
        resource_var: str = "t.resource"
    ) -> str:
        """Generate UNION ALL SQL from select branches.

        Args:
            union_selects: List of Select structures to union
            base_query: Base table reference
            resource_var: Variable name for the resource

        Returns:
            Complete UNION ALL SQL string
        """
        return generate_union_all(
            union_selects, base_query, self.generator, resource_var
        )

    def validate_union_columns(self, union_selects: List['Select']) -> List[str]:
        """Validate that all union branches have matching output schemas.

        Args:
            union_selects: List of Select structures to validate

        Returns:
            List of warning messages (empty if valid)
        """
        warnings = []

        if not union_selects:
            warnings.append("unionAll requires at least one select branch")
            return warnings

        first_schema = _extract_column_schema(union_selects[0], self.generator)

        for i, select in enumerate(union_selects[1:], start=1):
            branch_schema = _extract_column_schema(select, self.generator)

            if branch_schema != first_schema:
                warnings.append(
                    f"UNION ALL branch {i} has mismatched column schema. "
                    f"Expected: {first_schema}, Got: {branch_schema}"
                )

        return warnings

    def get_union_column_count(self, union_selects: List['Select']) -> int:
        """Get the number of columns in the UNION result.

        Args:
            union_selects: List of Select structures

        Returns:
            Number of columns in the result
        """
        if not union_selects:
            return 0
        return len(_extract_column_names(union_selects[0]))

    def get_union_column_names(self, union_selects: List['Select']) -> List[str]:
        """Get the column names for the UNION result.

        Args:
            union_selects: List of Select structures

        Returns:
            List of column names
        """
        if not union_selects:
            return []
        return _extract_column_names(union_selects[0])


def flatten_union_all(selects: List['Select']) -> List['Select']:
    """Flatten nested unionAll structures into a single-level list.

    This is useful when you want to process all union branches at once
    without dealing with nested unionAll structures.

    Args:
        selects: List of Select structures that may contain nested unionAll

    Returns:
        Flattened list of Select structures
    """
    result = []

    for select in selects:
        if select.unionAll:
            # Recursively flatten nested unionAll
            result.extend(flatten_union_all(select.unionAll))
        else:
            result.append(select)

    return result

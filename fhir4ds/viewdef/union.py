"""
UNION ALL generation for SQL-on-FHIR v2.

Handles unionAll structures in ViewDefinitions, generating SQL UNION ALL queries
that combine results from multiple select branches.
"""

import logging
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .parser import Select

from .parser import Column

_logger = logging.getLogger(__name__)


class UnionGeneratorError(Exception):
    """Raised when UNION ALL generation fails."""
    pass


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

    # Generate SQL for each branch
    branch_sqls = []
    column_names = None

    for i, select in enumerate(union_selects):
        branch_sql, branch_columns = _generate_union_branch(
            select, base_query, generator, resource_var
        )
        branch_sqls.append(branch_sql)

        # Verify column names match across branches
        if column_names is None:
            column_names = branch_columns
        elif column_names != branch_columns:
            raise UnionGeneratorError(
                f"UNION ALL branch {i} has mismatched column names. "
                f"Expected: {column_names}, Got: {branch_columns}"
            )

    return "\nUNION ALL\n".join(branch_sqls)


def _generate_union_branch(
    select: 'Select',
    base_query: str,
    generator: 'SQLGenerator',
    resource_var: str
) -> tuple[str, List[str]]:
    """Generate SQL for a single UNION branch.

    Handles both simple column selects and nested unionAll structures.

    Args:
        select: Select structure for this branch
        base_query: Base table reference
        generator: SQLGenerator instance
        resource_var: Variable name for the resource

    Returns:
        Tuple of (SQL string, list of column names)
    """
    # Check if this branch itself contains a nested unionAll
    if select.unionAll:
        # Recursively handle nested unionAll
        nested_sql = generate_union_all(
            select.unionAll, base_query, generator, resource_var
        )
        # Extract column names from the first nested branch
        column_names = _extract_column_names(select.unionAll[0])
        return nested_sql, column_names

    # Generate column expressions
    column_exprs = []
    column_names = []

    for col in select.column:
        expr = generator.generate_column_expr(col, resource_var)
        column_exprs.append(expr)
        column_names.append(col.name)

    # Build SELECT statement
    columns_sql = ",\n    ".join(column_exprs)

    sql = f"SELECT\n    {columns_sql}\nFROM {base_query}"

    return sql, column_names


def _extract_column_names(select: 'Select') -> List[str]:
    """Extract column names from a Select structure.

    Handles nested unionAll by recursively extracting from the first branch.

    Args:
        select: Select structure to extract names from

    Returns:
        List of column names
    """
    if select.unionAll:
        return _extract_column_names(select.unionAll[0])
    return [col.name for col in select.column]


class UnionGenerator:
    """Manages UNION ALL SQL generation for complex nested structures.

    This class provides a higher-level interface for generating UNION ALL
    queries, handling validation, column name consistency, and nested
    unionAll structures.
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
        """Validate that all union branches have matching column names.

        Args:
            union_selects: List of Select structures to validate

        Returns:
            List of warning messages (empty if valid)
        """
        warnings = []

        if not union_selects:
            warnings.append("unionAll requires at least one select branch")
            return warnings

        # Get column names from first branch
        first_columns = _extract_column_names(union_selects[0])

        # Compare with all other branches
        for i, select in enumerate(union_selects[1:], start=1):
            branch_columns = _extract_column_names(select)

            if branch_columns != first_columns:
                warnings.append(
                    f"UNION ALL branch {i} has mismatched column names. "
                    f"Expected: {first_columns}, Got: {branch_columns}"
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

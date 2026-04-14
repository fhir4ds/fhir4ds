"""
UNNEST generation for forEach/forEachOrNull in SQL-on-FHIR v2.

Generates CROSS JOIN LATERAL (forEach) or LEFT JOIN LATERAL (forEachOrNull)
with UNNEST to flatten FHIRPath array expressions into SQL rows.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

_logger = logging.getLogger(__name__)


def generate_foreach_unnest(path: str, resource_var: str, alias: str) -> str:
    """Generate CROSS JOIN LATERAL with UNNEST for forEach.

    Creates a SQL fragment that unnests a FHIRPath array expression
    using CROSS JOIN LATERAL, which means rows without matching
    elements are excluded from the result.

    Args:
        path: FHIRPath expression that returns an array
        resource_var: Variable/expression holding the FHIR resource
        alias: Alias name for the unnested element

    Returns:
        SQL fragment for CROSS JOIN LATERAL UNNEST

    Example:
        >>> generate_foreach_unnest('name', 't.resource', 'name_elem')
        "CROSS JOIN LATERAL (\\n    SELECT unnest(arr) as name_elem, unnest(range(len(arr))) as name_elem__row_index\\n    FROM (VALUES (fhirpath(t.resource, 'name'))) v(arr)\\n) as name_elem_table"
    """
    escaped_path = path.replace("'", "''")
    table_alias = f"{alias}_table"
    return (
        f"CROSS JOIN LATERAL (\n"
        f"    SELECT unnest(arr) as {alias}, "
        f"unnest(range(len(arr))) as {alias}__row_index\n"
        f"    FROM (VALUES (fhirpath({resource_var}, '{escaped_path}'))) v(arr)\n"
        f") as {table_alias}"
    )


def generate_foreachornull_unnest(path: str, resource_var: str, alias: str) -> str:
    """Generate LEFT JOIN LATERAL with UNNEST for forEachOrNull.

    Creates a SQL fragment that unnests a FHIRPath array expression
    using LEFT JOIN LATERAL, which preserves rows even when there
    are no matching elements (NULL values in the unnested column).

    Args:
        path: FHIRPath expression that returns an array
        resource_var: Variable/expression holding the FHIR resource
        alias: Alias name for the unnested element

    Returns:
        SQL fragment for LEFT JOIN LATERAL UNNEST

    Example:
        >>> generate_foreachornull_unnest('telecom', 't.resource', 'telecom_elem')
        "LEFT JOIN LATERAL (\\n    SELECT unnest(arr) as telecom_elem, unnest(range(len(arr))) as telecom_elem__row_index\\n    FROM (VALUES (fhirpath(t.resource, 'telecom'))) v(arr)\\n) as telecom_elem_table ON true"
    """
    escaped_path = path.replace("'", "''")
    table_alias = f"{alias}_table"
    return (
        f"LEFT JOIN LATERAL (\n"
        f"    SELECT unnest(arr) as {alias}, "
        f"unnest(range(len(arr))) as {alias}__row_index\n"
        f"    FROM (VALUES (fhirpath({resource_var}, '{escaped_path}'))) v(arr)\n"
        f") as {table_alias} ON true"
    )


@dataclass
class UnnestInfo:
    """Information about a generated UNNEST join.

    Attributes:
        sql: The generated SQL fragment for the join
        element_alias: The alias for the unnested element (becomes new resource_var)
        table_alias: The alias for the subquery table
        path: The original FHIRPath expression
        is_foreach: True if forEach, False if forEachOrNull
    """
    sql: str
    element_alias: str
    table_alias: str
    path: str
    is_foreach: bool


class UnnestGenerator:
    """Manages generation of UNNEST joins for forEach/forEachOrNull.

    This class tracks generated unnests and provides utilities for
    managing the resource variable context as nested forEach structures
    are processed.

    Attributes:
        base_resource_var: The initial resource variable (e.g., 't.resource')
        unnests: List of generated UnnestInfo objects
        _counter: Counter for generating unique aliases
    """

    def __init__(self, base_resource_var: str = "t.resource"):
        """Initialize the UnnestGenerator.

        Args:
            base_resource_var: The initial resource variable expression
        """
        self.base_resource_var = base_resource_var
        self.unnests: List[UnnestInfo] = []
        self._counter = 0

    def _generate_alias(self, path: str) -> str:
        """Generate a unique alias for an unnested element.

        Creates an alias based on the path, with a counter suffix
        to ensure uniqueness.

        Args:
            path: The FHIRPath expression

        Returns:
            A unique alias string
        """
        # Extract last component of path for a meaningful alias
        path_parts = path.replace('/', '.').split('.')
        base_name = path_parts[-1] if path_parts else 'elem'

        # Clean the name to be SQL-safe
        base_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in base_name)

        # Add counter for uniqueness
        alias = f"{base_name}_elem"
        if self._counter > 0:
            alias = f"{base_name}_elem_{self._counter}"

        self._counter += 1
        return alias

    def generate_foreach(
        self,
        path: str,
        resource_var: str,
        alias: Optional[str] = None
    ) -> UnnestInfo:
        """Generate a forEach UNNEST join.

        Args:
            path: FHIRPath expression that returns an array
            resource_var: Current resource variable context
            alias: Optional custom alias (generated if not provided)

        Returns:
            UnnestInfo with the generated join details
        """
        if alias is None:
            alias = self._generate_alias(path)

        sql = generate_foreach_unnest(path, resource_var, alias)
        table_alias = f"{alias}_table"

        info = UnnestInfo(
            sql=sql,
            element_alias=alias,
            table_alias=table_alias,
            path=path,
            is_foreach=True
        )
        self.unnests.append(info)
        return info

    def generate_foreachornull(
        self,
        path: str,
        resource_var: str,
        alias: Optional[str] = None
    ) -> UnnestInfo:
        """Generate a forEachOrNull UNNEST join.

        Args:
            path: FHIRPath expression that returns an array
            resource_var: Current resource variable context
            alias: Optional custom alias (generated if not provided)

        Returns:
            UnnestInfo with the generated join details
        """
        if alias is None:
            alias = self._generate_alias(path)

        sql = generate_foreachornull_unnest(path, resource_var, alias)
        table_alias = f"{alias}_table"

        info = UnnestInfo(
            sql=sql,
            element_alias=alias,
            table_alias=table_alias,
            path=path,
            is_foreach=False
        )
        self.unnests.append(info)
        return info

    def get_all_join_sql(self) -> str:
        """Get all generated UNNEST joins as a single SQL fragment.

        Returns:
            Combined SQL for all joins, separated by newlines
        """
        return '\n'.join(info.sql for info in self.unnests)

    def get_current_resource_var(self) -> str:
        """Get the current resource variable for column expressions.

        Returns the element_alias from the most recent unnest,
        or the base_resource_var if no unnests have been generated.

        Returns:
            The current resource variable expression
        """
        if self.unnests:
            return self.unnests[-1].element_alias
        return self.base_resource_var

    def clear(self) -> None:
        """Clear all generated unnests and reset counter."""
        self.unnests.clear()
        self._counter = 0

    def pop(self) -> Optional[UnnestInfo]:
        """Remove and return the most recent unnest.

        Returns:
            The most recent UnnestInfo, or None if empty
        """
        if self.unnests:
            self._counter = max(0, self._counter - 1)
            return self.unnests.pop()
        return None

    def __len__(self) -> int:
        """Return the number of generated unnests."""
        return len(self.unnests)

    def __bool__(self) -> bool:
        """Return True if any unnests have been generated."""
        return bool(self.unnests)

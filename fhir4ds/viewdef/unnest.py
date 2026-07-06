"""
UNNEST generation for forEach/forEachOrNull in SQL-on-FHIR v2.

Generates CROSS JOIN LATERAL (forEach) or LEFT JOIN LATERAL (forEachOrNull)
using FHIRPath list order while extracting each element from the corresponding
FHIRPath JSON array so primitive iterator focus keeps valid JSON shape.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

_logger = logging.getLogger(__name__)


def _fhirpath_path_argument(path: str, path_sql: str | None) -> str:
    if path_sql is not None:
        return path_sql
    escaped_path = path.replace("'", "''")
    return f"'{escaped_path}'"


def generate_foreach_unnest(
    path: str,
    resource_var: str,
    alias: str,
    path_sql: str | None = None,
    null_preserve_var: str | None = None,
) -> str:
    """Generate JOIN LATERAL with UNNEST for forEach.

    Creates a SQL fragment that unnests a FHIRPath array expression.

    By default (``null_preserve_var=None``) a CROSS JOIN LATERAL is
    emitted (inner join), so rows without matching elements are
    excluded from the result — the SQL-on-FHIR v2 ``forEach``
    inner-join semantics.

    When ``null_preserve_var`` is set to the alias of an enclosing
    ``forEachOrNull`` unnest, the JOIN is rewritten so it preserves
    that enclosing context's NULL row only when the enclosing
    forEachOrNull's foci is empty (``null_preserve_var IS NULL``).
    Per SQL-on-FHIR v2 Process(S, N) step 3, when the outer
    forEachOrNull's foci is empty the entire selection structure
    emits exactly ONE null row — including columns produced by nested
    forEach. When the outer foci is non-empty, the inner forEach
    keeps ordinary INNER JOIN semantics so child collections that are
    empty still drop their own focus row.

    Args:
        path: FHIRPath expression that returns an array
        resource_var: Variable/expression holding the FHIR resource
        alias: Alias name for the unnested element
        null_preserve_var: When set to the enclosing forEachOrNull
            unnest alias, preserve the parent's NULL row only when
            that alias is NULL (spec Process(S, N) step 3).

    Returns:
        SQL fragment for the JOIN LATERAL UNNEST.
    """
    table_alias = f"{alias}_table"
    path_arg = _fhirpath_path_argument(path, path_sql)
    if null_preserve_var is None:
        return (
            f"CROSS JOIN LATERAL (\n"
            f"    SELECT json_extract(jarr, '$[' || CAST(idx AS VARCHAR) || ']') as {alias}, "
            f"idx as {alias}__row_index\n"
            f"    FROM (VALUES (fhirpath({resource_var}, {path_arg}), "
            f"fhirpath_json({resource_var}, {path_arg}))) v(arr, jarr)\n"
            f"    CROSS JOIN UNNEST(range(len(arr))) AS u(idx)\n"
            f"    ORDER BY idx\n"
            f") as {table_alias}"
        )
    # null-preserving mode: when the enclosing forEachOrNull preserves a
    # parent NULL row (its unnest alias is NULL), this forEach must NOT
    # eliminate that NULL row. Per SQL-on-FHIR v2 Process(S, N) step 3,
    # when the outer forEachOrNull's foci is empty the entire selection
    # structure emits exactly ONE null row — including columns produced
    # by nested forEach.
    #
    # When the enclosing alias is non-NULL (a real focus element),
    # ordinary INNER JOIN semantics apply and an empty child collection
    # drops the focus row per Process(S, N) step 2.
    #
    # Implementation: emit CROSS JOIN LATERAL against a subquery that
    # uses the enclosing unnest alias as its resource. The subquery
    # short-circuits the unnest when the enclosing alias is NULL by
    # gating the source VALUES row on ``{null_preserve_var} IS NOT
    # NULL``, then UNION ALLs a single synthetic NULL row produced only
    # when the enclosing alias is NULL. The result:
    #   * enclosing alias NULL  → 1 synthetic NULL row (preserves parent).
    #   * enclosing alias non-NULL, child non-empty → N unnested rows.
    #   * enclosing alias non-NULL, child empty → 0 rows (parent dropped,
    #     INNER JOIN semantics).
    return (
        f"CROSS JOIN LATERAL (\n"
        f"    SELECT json_extract(jarr, '$[' || CAST(idx AS VARCHAR) || ']') as {alias}, "
        f"idx as {alias}__row_index\n"
        f"    FROM (\n"
        f"        SELECT * FROM (VALUES (fhirpath({resource_var}, {path_arg}), "
        f"fhirpath_json({resource_var}, {path_arg}))) v(arr, jarr)\n"
        f"        WHERE {null_preserve_var} IS NOT NULL\n"
        f"    ) v\n"
        f"    CROSS JOIN UNNEST(range(len(arr))) AS u(idx)\n"
        f"    UNION ALL\n"
        f"    SELECT NULL, NULL WHERE {null_preserve_var} IS NULL\n"
        f"    ORDER BY {alias}__row_index\n"
        f") as {table_alias}"
    )


def generate_repeat_unnest(
    paths: list,
    resource_var: str,
    alias: str,
    null_preserve_var: str | None = None,
) -> str:
    """Generate CROSS JOIN LATERAL with UNNEST for repeat traversal.

    Creates a SQL fragment using the ``fhirpath_repeat`` UDF for recursive
    traversal per SQL-on-FHIR v2 §Select.repeat.  Like forEach, rows without
    matching elements are excluded from the result.

    By default (``null_preserve_var=None``) a CROSS JOIN LATERAL is
    emitted (inner join), so rows without matching elements are
    excluded from the result — the SQL-on-FHIR v2 ``repeat``
    inner-join semantics, mirroring ``generate_foreach_unnest``.

    When ``null_preserve_var`` is set to the alias of an enclosing
    ``forEachOrNull`` unnest, the JOIN is rewritten so it preserves
    that enclosing context's NULL row only when the enclosing
    forEachOrNull's foci is empty (``null_preserve_var IS NULL``).
    Per SQL-on-FHIR v2 Process(S, N) step 3, when the outer
    forEachOrNull's foci is empty the entire selection structure
    emits exactly ONE null row — including columns produced by nested
    ``repeat``. This mirrors the QA-005 fix for nested ``forEach``.

    Args:
        paths: List of FHIRPath path strings for repeat traversal.
        resource_var: Variable/expression holding the FHIR resource.
        alias: Alias name for the unnested element.
        null_preserve_var: When set to the enclosing forEachOrNull
            unnest alias, preserve the parent's NULL row only when
            that alias is NULL (spec Process(S, N) step 3).

    Returns:
        SQL fragment for CROSS JOIN LATERAL UNNEST of repeat results.
    """
    import json
    paths_literal = json.dumps(paths).replace("'", "''")
    table_alias = f"{alias}_table"
    if null_preserve_var is None:
        return (
            f"CROSS JOIN LATERAL (\n"
            f"    SELECT unnest(arr) as {alias}, "
            f"unnest(range(len(arr))) as {alias}__row_index\n"
            f"    FROM (VALUES (fhirpath_repeat({resource_var}, '{paths_literal}'))) v(arr)\n"
            f") as {table_alias}"
        )
    # null-preserving mode (mirrors generate_foreach_unnest). When the
    # enclosing forEachOrNull preserves a parent NULL row (its unnest
    # alias is NULL), this repeat must NOT eliminate that NULL row. Per
    # SQL-on-FHIR v2 Process(S, N) step 3, when the outer forEachOrNull's
    # foci is empty the entire selection structure emits exactly ONE null
    # row — including columns produced by nested ``repeat``.
    #
    # When the enclosing alias is non-NULL (a real focus element),
    # ordinary INNER JOIN semantics apply and an empty child collection
    # drops the focus row per Process(S, N) step 2.
    #
    # Implementation: gate the source VALUES row on
    # ``{null_preserve_var} IS NOT NULL``, then UNION ALL a single
    # synthetic NULL row produced only when the enclosing alias is NULL.
    return (
        f"CROSS JOIN LATERAL (\n"
        f"    SELECT unnest(arr) as {alias}, "
        f"unnest(range(len(arr))) as {alias}__row_index\n"
        f"    FROM (\n"
        f"        SELECT * FROM (VALUES (fhirpath_repeat({resource_var}, '{paths_literal}'))) v(arr)\n"
        f"        WHERE {null_preserve_var} IS NOT NULL\n"
        f"    ) v\n"
        f"    UNION ALL\n"
        f"    SELECT NULL, NULL WHERE {null_preserve_var} IS NULL\n"
        f") as {table_alias}"
    )


def generate_foreachornull_unnest(
    path: str,
    resource_var: str,
    alias: str,
    path_sql: str | None = None,
) -> str:
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
        "LEFT JOIN LATERAL (\\n    SELECT json_extract(jarr, '$[' || CAST(idx AS VARCHAR) || ']') as telecom_elem, idx as telecom_elem__row_index\\n    FROM (VALUES (fhirpath(t.resource, 'telecom'), fhirpath_json(t.resource, 'telecom'))) v(arr, jarr)\\n    CROSS JOIN UNNEST(range(len(arr))) AS u(idx)\\n    ORDER BY idx\\n) as telecom_elem_table ON true"
    """
    table_alias = f"{alias}_table"
    path_arg = _fhirpath_path_argument(path, path_sql)
    return (
        f"LEFT JOIN LATERAL (\n"
        f"    SELECT json_extract(jarr, '$[' || CAST(idx AS VARCHAR) || ']') as {alias}, "
        f"idx as {alias}__row_index\n"
        f"    FROM (VALUES (fhirpath({resource_var}, {path_arg}), "
        f"fhirpath_json({resource_var}, {path_arg}))) v(arr, jarr)\n"
        f"    CROSS JOIN UNNEST(range(len(arr))) AS u(idx)\n"
        f"    ORDER BY idx\n"
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
